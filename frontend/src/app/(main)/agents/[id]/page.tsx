'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'


const AGENT_TYPE_ICONS: Record<string, string> = {
  coder: '💻', researcher: '🔍', designer: '🎨',
  reviewer: '🔎', planner: '📋', executor: '⚡', writer: '✍️'
}

const TOOL_DESCRIPTIONS: Record<string, string> = {
  read_file: 'Read file contents', write_file: 'Create or modify files',
  run_tests: 'Execute test suites', git_commit: 'Commit changes to git',
  shell_execute: 'Run shell commands', http_request: 'Make HTTP requests',
  web_search: 'Search the web', generate_image: 'Generate images',
  image_variation: 'Create image variations'
}

const ALL_TOOLS = Object.keys(TOOL_DESCRIPTIONS)

interface Persona { id: string; name: string; description?: string; is_default?: boolean }

interface AgentData {
  id: string; name: string; agent_type: string; description?: string
  system_prompt: string; model_id?: string; persona_id?: string
  persona_name?: string; persona_system_prompt?: string
  effective_system_prompt?: string
  resolved_model_name?: string; resolved_via?: string
  tools: string[]; memory_enabled: boolean; max_iterations: number
  timeout_seconds: number; is_active: boolean
}

interface RunEvent {
  event: string
  data?: string
  run_id?: string
  iteration?: number
  command?: string
  exit_code?: number
  stdout?: string
  stderr?: string
  success?: boolean
  output?: string
  message?: string
  iteration_count?: number
  input_tokens?: number
  output_tokens?: number
  duration_ms?: number
  elapsed_ms?: number
}

interface ToolCall {
  command: string
  exit_code?: number
  stdout?: string
  stderr?: string
  success?: boolean
  iteration: number
}

interface HistoryRun {
  id: string
  task: string
  status: string
  output: string
  tool_log: any[]
  input_tokens: number
  output_tokens: number
  duration_ms: number
  created_at: string
}

export default function AgentDetailPage() {
  const params = useParams()
  const router = useRouter()
  const agentId = params.id as string

  const [agent, setAgent] = useState<AgentData | null>(null)
  const [personas, setPersonas] = useState<Persona[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({
    name: '', description: '', system_prompt: '', agent_type: 'coder',
    persona_id: '', model_id: '', tools: [] as string[],
    memory_enabled: true, max_iterations: 10, timeout_seconds: 300
  })

  // Run modal state
  const [showRunModal, setShowRunModal] = useState(false)
  const [runTask, setRunTask] = useState('')
  const [runStatus, setRunStatus] = useState<'idle' | 'running' | 'completed' | 'failed'>('idle')
  const [runOutput, setRunOutput] = useState('')
  const [runToolCalls, setRunToolCalls] = useState<ToolCall[]>([])
  const [runTokens, setRunTokens] = useState({ input: 0, output: 0 })
  const [runDuration, setRunDuration] = useState(0)
  const [runError, setRunError] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const outputEndRef = useRef<HTMLDivElement>(null)

  // Tab state: 'details' | 'history'
  const [activeTab, setActiveTab] = useState<'details' | 'history'>('details')
  const [history, setHistory] = useState<HistoryRun[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [expandedToolCalls, setExpandedToolCalls] = useState<Set<number>>(new Set())

  const loadData = useCallback(async () => {
    const [personasRes] = await Promise.all([
      fetch(`${API_BASE}/v1/personas`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ data: [] }))
    ])
    setPersonas(personasRes.data || [])

    if (agentId !== 'new') {
      const agentData = await fetch(`${API_BASE}/v1/agents/${agentId}`, { headers: AUTH_HEADERS })
        .then(r => r.json()).catch(() => null)
      if (agentData && !agentData.detail) {
        setAgent(agentData)
        setForm({
          name: agentData.name, description: agentData.description || '',
          system_prompt: agentData.system_prompt, agent_type: agentData.agent_type,
          persona_id: agentData.persona_id || '', model_id: agentData.model_id || '',
          tools: agentData.tools || [], memory_enabled: agentData.memory_enabled,
          max_iterations: agentData.max_iterations, timeout_seconds: agentData.timeout_seconds
        })
      }
    } else {
      setEditing(true)
    }
    setLoading(false)
  }, [agentId])

  useEffect(() => { loadData() }, [loadData])

  // Auto-scroll output
  useEffect(() => {
    if (runStatus === 'running') outputEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [runOutput, runToolCalls, runStatus])

  // Load run history
  const loadHistory = useCallback(async () => {
    if (agentId === 'new') return
    setHistoryLoading(true)
    try {
      const res = await fetch(`${API_BASE}/v1/agents/${agentId}/runs`, { headers: AUTH_HEADERS })
      if (res.ok) {
        const data = await res.json()
        setHistory(data.data || [])
      }
    } catch { /* ignore */ }
    setHistoryLoading(false)
  }, [agentId])

  useEffect(() => {
    if (activeTab === 'history') loadHistory()
  }, [activeTab, loadHistory])

  // Run agent with streaming
  const startRun = async () => {
    if (!runTask.trim()) return
    setRunStatus('running')
    setRunOutput('')
    setRunToolCalls([])
    setRunTokens({ input: 0, output: 0 })
    setRunDuration(0)
    setRunError('')
    setExpandedToolCalls(new Set())

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const res = await fetch(`${API_BASE}/v1/agents/${agentId}/run`, {
        method: 'POST',
        headers: AUTH_HEADERS,
        body: JSON.stringify({ task: runTask, stream: true }),
        signal: controller.signal,
      })

      if (!res.ok) {
        const errBody = await res.text()
        setRunError(errBody || `HTTP ${res.status}`)
        setRunStatus('failed')
        return
      }

      const reader = res.body?.getReader()
      if (!reader) { setRunError('No response stream'); setRunStatus('failed'); return }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt: RunEvent = JSON.parse(line.slice(6))
            switch (evt.event) {
              case 'chunk':
                setRunOutput(prev => prev + (evt.data || ''))
                break
              case 'tool_call':
                setRunToolCalls(prev => [...prev, {
                  command: evt.command || '',
                  iteration: evt.iteration || 0,
                }])
                break
              case 'tool_result':
                setRunToolCalls(prev => {
                  const updated = [...prev]
                  const idx = updated.findLastIndex(t => t.command === evt.command && t.exit_code === undefined)
                  if (idx >= 0) {
                    updated[idx] = { ...updated[idx], exit_code: evt.exit_code, stdout: evt.stdout, stderr: evt.stderr, success: evt.success }
                  }
                  return updated
                })
                break
              case 'done':
                if (evt.output && !runOutput) setRunOutput(prev => prev || evt.output || '')
                setRunTokens({ input: evt.input_tokens || 0, output: evt.output_tokens || 0 })
                setRunDuration(evt.duration_ms || 0)
                setRunStatus('completed')
                break
              case 'error':
                setRunError(evt.message || 'Unknown error')
                setRunStatus('failed')
                break
              case 'timeout':
                setRunError(`Agent timed out after ${((evt.elapsed_ms || 0) / 1000).toFixed(1)}s`)
                setRunStatus('failed')
                break
              case 'max_iterations':
                setRunError('Maximum iterations reached')
                setRunStatus('failed')
                break
            }
          } catch { /* skip unparseable lines */ }
        }
      }

      // If stream ended without done/error, mark completed
      setRunStatus(prev => prev === 'running' ? 'completed' : prev)
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        setRunError(e.message || 'Connection failed')
        setRunStatus('failed')
      }
    }
  }

  const cancelRun = () => {
    abortRef.current?.abort()
    setRunStatus('failed')
    setRunError('Run cancelled by user')
  }

  const resetRunModal = () => {
    setShowRunModal(false)
    setRunStatus('idle')
    setRunOutput('')
    setRunToolCalls([])
    setRunTokens({ input: 0, output: 0 })
    setRunDuration(0)
    setRunError('')
    setRunTask('')
    abortRef.current?.abort()
  }

  const saveAgent = async () => {
    setSaving(true)
    const body = {
      ...form,
      persona_id: form.persona_id || null,
      model_id: form.model_id || null,
    }
    try {
      if (agentId === 'new') {
        const res = await fetch(`${API_BASE}/v1/agents`, {
          method: 'POST', headers: AUTH_HEADERS, body: JSON.stringify(body)
        }).then(r => r.json())
        router.push(`/agents/${res.id}`)
      } else {
        const res = await fetch(`${API_BASE}/v1/agents/${agentId}`, {
          method: 'PATCH', headers: AUTH_HEADERS, body: JSON.stringify(body)
        }).then(r => r.json())
        // If a default-* agent was promoted to a real DB record, update the URL
        if (res.id && res.id !== agentId) {
          router.replace(`/agents/${res.id}`)
        }
        setAgent(res)
        setEditing(false)
      }
    } catch (e) {
      alert('Failed to save agent')
    } finally {
      setSaving(false)
    }
  }

  const toggleTool = (tool: string) => {
    setForm(prev => ({
      ...prev,
      tools: prev.tools.includes(tool)
        ? prev.tools.filter(t => t !== tool)
        : [...prev.tools, tool]
    }))
  }

  if (loading) return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div className="flex gap-1.5">{[0,1,2].map(i => <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />)}</div>
    </div>
  )

  const selectedPersona = personas.find(p => p.id === form.persona_id)

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/agents" className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </Link>
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">
            {agentId === 'new' ? 'New Agent' : (agent?.name || 'Agent')}
          </h1>
          {agent && !editing && (
            <span className={`text-xs px-2 py-0.5 rounded-full ${agent.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
              {agent.is_active ? 'Active' : 'Inactive'}
            </span>
          )}
        </div>
        <div className="flex gap-2">
          {agent && !editing && (
            <button onClick={() => setShowRunModal(true)}
              className="px-4 py-2 text-sm font-medium rounded-lg bg-green-600 hover:bg-green-700 text-white flex items-center gap-1.5">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              Run Agent
            </button>
          )}
          {agent && !editing && (
            <button onClick={() => setEditing(true)}
              className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
              Edit
            </button>
          )}
          {editing && (
            <>
              <button onClick={() => agentId === 'new' ? router.push('/agents') : setEditing(false)}
                className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50">
                Cancel
              </button>
              <button onClick={saveAgent} disabled={saving}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-50">
                {saving ? 'Saving...' : 'Save Agent'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Tabs — only show when not editing and we have an agent */}
      {!editing && agent && (
        <div className="flex border-b border-gray-200 dark:border-gray-700">
          <button onClick={() => setActiveTab('details')}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${activeTab === 'details' ? 'border-orange-500 text-orange-600 dark:text-orange-400' : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}`}>
            Details
          </button>
          <button onClick={() => setActiveTab('history')}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${activeTab === 'history' ? 'border-orange-500 text-orange-600 dark:text-orange-400' : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}`}>
            Run History
          </button>
        </div>
      )}

      {/* View mode — Details tab */}
      {!editing && agent && activeTab === 'details' && (
        <div className="space-y-4">
          {/* Identity card */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-xl bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center text-2xl flex-shrink-0">
                {AGENT_TYPE_ICONS[agent.agent_type] || '🤖'}
              </div>
              <div className="flex-1 min-w-0">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{agent.name}</h2>
                <p className="text-sm text-gray-500 capitalize">{agent.agent_type}</p>
                {agent.description && <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">{agent.description}</p>}
              </div>
            </div>
          </div>

          {/* Persona / Model card */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Model Assignment</h3>
            {agent.persona_id ? (
              <div className="flex items-center gap-3 p-3 bg-orange-50 dark:bg-orange-900/20 rounded-lg border border-orange-200 dark:border-orange-700">
                <span className="text-xl">🎭</span>
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    Persona: <span className="text-orange-600 dark:text-orange-400">{agent.persona_name || agent.persona_id}</span>
                  </p>
                  {agent.resolved_model_name && (
                    <p className="text-xs text-gray-500 mt-0.5">
                      Resolves to: <span className="font-mono">{agent.resolved_model_name}</span>
                      <span className="ml-1 text-gray-400">(via persona)</span>
                    </p>
                  )}
                </div>
              </div>
            ) : agent.resolved_model_name ? (
              <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
                <span className="text-xl">🔧</span>
                <div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">Direct model</p>
                  <p className="text-xs font-mono text-gray-500">{agent.resolved_model_name}</p>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm text-amber-600 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 rounded-lg border border-amber-200 dark:border-amber-700">
                <span>⚠️</span> No model assigned — click Edit to assign a persona
              </div>
            )}
          </div>

          {/* Tools */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Tools ({agent.tools.length})</h3>
            {agent.tools.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {agent.tools.map(t => (
                  <span key={t} className="px-2.5 py-1 text-xs bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded-full border border-blue-200 dark:border-blue-700 font-mono">
                    {t}
                  </span>
                ))}
              </div>
            ) : <p className="text-sm text-gray-400">No tools assigned</p>}
          </div>

          {/* Config */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Configuration</h3>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-xs text-gray-400">Max Iterations</p>
                <p className="font-semibold text-gray-900 dark:text-white">{agent.max_iterations}</p>
              </div>
              <div>
                <p className="text-xs text-gray-400">Timeout</p>
                <p className="font-semibold text-gray-900 dark:text-white">{agent.timeout_seconds}s</p>
              </div>
              <div>
                <p className="text-xs text-gray-400">Memory</p>
                <p className={`font-semibold ${agent.memory_enabled ? 'text-green-600' : 'text-gray-400'}`}>
                  {agent.memory_enabled ? 'Enabled' : 'Disabled'}
                </p>
              </div>
            </div>
          </div>

          {/* System prompt */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">System Prompt</h3>
              {agent.persona_id && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400">
                  merged from persona + agent
                </span>
              )}
            </div>

            {agent.persona_id && agent.persona_system_prompt ? (
              <div className="space-y-3">
                <div>
                  <p className="text-xs text-gray-400 mb-1">🎭 From persona <span className="font-medium text-orange-500">{agent.persona_name}</span></p>
                  <pre className="text-xs text-gray-500 dark:text-gray-400 whitespace-pre-wrap font-mono bg-gray-50 dark:bg-gray-900 rounded-lg p-3 max-h-32 overflow-y-auto border border-gray-100 dark:border-gray-700">
                    {agent.persona_system_prompt}
                  </pre>
                </div>
                {agent.system_prompt && (
                  <div>
                    <p className="text-xs text-gray-400 mb-1">🤖 Agent-specific additions</p>
                    <pre className="text-xs text-gray-600 dark:text-gray-300 whitespace-pre-wrap font-mono bg-blue-50 dark:bg-blue-900/10 rounded-lg p-3 max-h-32 overflow-y-auto border border-blue-100 dark:border-blue-800">
                      {agent.system_prompt}
                    </pre>
                  </div>
                )}
                {!agent.system_prompt && (
                  <p className="text-xs text-gray-400 italic">No agent-specific additions — persona prompt used as-is.</p>
                )}
              </div>
            ) : (
              <pre className="text-xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap font-mono bg-gray-50 dark:bg-gray-900 rounded-lg p-3 max-h-48 overflow-y-auto">
                {agent.system_prompt}
              </pre>
            )}
          </div>
        </div>
      )}

      {/* History tab */}
      {!editing && agent && activeTab === 'history' && (
        <div className="space-y-3">
          {historyLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="flex gap-1.5">{[0,1,2].map(i => <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />)}</div>
            </div>
          ) : history.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <p className="text-lg mb-1">No runs yet</p>
              <p className="text-sm">Click &quot;Run Agent&quot; to test this agent</p>
            </div>
          ) : (
            history.map(run => (
              <div key={run.id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{run.task}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{new Date(run.created_at).toLocaleString()}</p>
                  </div>
                  <span className={`ml-3 text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${
                    run.status === 'completed' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                    run.status === 'failed' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                    run.status === 'running' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' :
                    'bg-gray-100 text-gray-600'
                  }`}>
                    {run.status}
                  </span>
                </div>
                {run.output && (
                  <pre className="text-xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap font-mono bg-gray-50 dark:bg-gray-900 rounded-lg p-3 max-h-32 overflow-y-auto mt-2">
                    {run.output}
                  </pre>
                )}
                <div className="flex gap-4 mt-2 text-xs text-gray-400">
                  {run.duration_ms > 0 && <span>⏱ {(run.duration_ms / 1000).toFixed(1)}s</span>}
                  {(run.input_tokens > 0 || run.output_tokens > 0) && (
                    <span>🔤 {run.input_tokens + run.output_tokens} tokens</span>
                  )}
                  {run.tool_log && run.tool_log.length > 0 && (
                    <span>🔧 {run.tool_log.length} iteration{run.tool_log.length !== 1 ? 's' : ''}</span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Run Agent Modal */}
      {showRunModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={(e) => { if (e.target === e.currentTarget && runStatus !== 'running') resetRunModal() }}>
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 w-full max-w-2xl max-h-[85vh] flex flex-col mx-4">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-2">
                <span className="text-lg">{AGENT_TYPE_ICONS[agent?.agent_type || ''] || '🤖'}</span>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Run {agent?.name}</h2>
                {runStatus !== 'idle' && (
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    runStatus === 'running' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 animate-pulse' :
                    runStatus === 'completed' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                    'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                  }`}>
                    {runStatus}
                  </span>
                )}
              </div>
              <button onClick={() => runStatus !== 'running' ? resetRunModal() : undefined}
                className={`text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 ${runStatus === 'running' ? 'opacity-50 cursor-not-allowed' : ''}`}>
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            {/* Modal body */}
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
              {/* Task input */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Task</label>
                <textarea
                  value={runTask}
                  onChange={e => setRunTask(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey && runStatus === 'idle') startRun() }}
                  placeholder="Describe the task for this agent..."
                  rows={3}
                  disabled={runStatus === 'running'}
                  className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none disabled:opacity-50"
                />
                <p className="text-xs text-gray-400 mt-1">Press Ctrl+Enter to run</p>
              </div>

              {/* Output section — shown once a run starts */}
              {runStatus !== 'idle' && (
                <>
                  {/* Streaming output */}
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Output</h3>
                    <pre className="text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap font-mono bg-gray-50 dark:bg-gray-900 rounded-lg p-4 max-h-64 overflow-y-auto border border-gray-200 dark:border-gray-700">
                      {runOutput || (runStatus === 'running' ? 'Waiting for response...' : 'No output')}
                      {runStatus === 'running' && <span className="inline-block w-1.5 h-4 bg-orange-400 animate-pulse ml-0.5 align-text-bottom" />}
                      <div ref={outputEndRef} />
                    </pre>
                  </div>

                  {/* Error display */}
                  {runError && (
                    <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 text-sm text-red-700 dark:text-red-400">
                      <svg className="w-4 h-4 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" /></svg>
                      <span>{runError}</span>
                    </div>
                  )}

                  {/* Tool calls */}
                  {runToolCalls.length > 0 && (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                        Tool Calls ({runToolCalls.length})
                      </h3>
                      <div className="space-y-1.5">
                        {runToolCalls.map((tc, i) => (
                          <div key={i} className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                            <button
                              onClick={() => setExpandedToolCalls(prev => {
                                const next = new Set(prev)
                                next.has(i) ? next.delete(i) : next.add(i)
                                return next
                              })}
                              className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                            >
                              <svg className={`w-3.5 h-3.5 text-gray-400 transition-transform ${expandedToolCalls.has(i) ? 'rotate-90' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg>
                              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${tc.success === undefined ? 'bg-blue-400 animate-pulse' : tc.success ? 'bg-green-400' : 'bg-red-400'}`} />
                              <code className="text-xs font-mono text-gray-700 dark:text-gray-300 truncate flex-1">{tc.command}</code>
                              {tc.exit_code !== undefined && (
                                <span className={`text-xs ${tc.exit_code === 0 ? 'text-green-500' : 'text-red-500'}`}>exit {tc.exit_code}</span>
                              )}
                            </button>
                            {expandedToolCalls.has(i) && (tc.stdout || tc.stderr) && (
                              <div className="px-3 pb-2 border-t border-gray-100 dark:border-gray-700">
                                {tc.stdout && (
                                  <pre className="text-xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap font-mono mt-2 max-h-24 overflow-y-auto">{tc.stdout}</pre>
                                )}
                                {tc.stderr && (
                                  <pre className="text-xs text-red-500 whitespace-pre-wrap font-mono mt-1 max-h-24 overflow-y-auto">{tc.stderr}</pre>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Metrics — shown when done */}
                  {runStatus !== 'running' && (runDuration > 0 || runTokens.input > 0 || runTokens.output > 0) && (
                    <div className="flex gap-6 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 text-sm">
                      {runDuration > 0 && (
                        <div>
                          <p className="text-xs text-gray-400">Duration</p>
                          <p className="font-semibold text-gray-900 dark:text-white">{(runDuration / 1000).toFixed(1)}s</p>
                        </div>
                      )}
                      {runTokens.input > 0 && (
                        <div>
                          <p className="text-xs text-gray-400">Input tokens</p>
                          <p className="font-semibold text-gray-900 dark:text-white">{runTokens.input.toLocaleString()}</p>
                        </div>
                      )}
                      {runTokens.output > 0 && (
                        <div>
                          <p className="text-xs text-gray-400">Output tokens</p>
                          <p className="font-semibold text-gray-900 dark:text-white">{runTokens.output.toLocaleString()}</p>
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Modal footer */}
            <div className="flex justify-end gap-2 px-6 py-4 border-t border-gray-200 dark:border-gray-700">
              {runStatus === 'running' ? (
                <button onClick={cancelRun}
                  className="px-4 py-2 text-sm font-medium rounded-lg bg-red-500 hover:bg-red-600 text-white">
                  Cancel
                </button>
              ) : (
                <>
                  <button onClick={resetRunModal}
                    className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700">
                    Close
                  </button>
                  <button onClick={() => { setRunStatus('idle'); setRunOutput(''); setRunToolCalls([]); setRunError(''); startRun() }}
                    disabled={!runTask.trim()}
                    className="px-4 py-2 text-sm font-medium rounded-lg bg-green-600 hover:bg-green-700 text-white disabled:opacity-50 flex items-center gap-1.5">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /></svg>
                    {runStatus === 'idle' ? 'Run' : 'Run Again'}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Edit mode */}
      {editing && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 space-y-6">

          {/* Basic info */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
              <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="Coder Agent"
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Type</label>
              <select value={form.agent_type} onChange={e => setForm(f => ({ ...f, agent_type: e.target.value }))}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400">
                {Object.entries(AGENT_TYPE_ICONS).map(([k, icon]) => (
                  <option key={k} value={k}>{icon} {k}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
            <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              placeholder="What does this agent do?"
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
          </div>

          {/* ── Persona assignment (primary) ── */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Persona <span className="text-orange-500 font-normal">(recommended)</span>
            </label>
            <select value={form.persona_id} onChange={e => setForm(f => ({ ...f, persona_id: e.target.value, model_id: '' }))}
              className="w-full rounded-lg border border-orange-300 dark:border-orange-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400">
              <option value="">— No persona (use direct model below) —</option>
              {personas.map(p => (
                <option key={p.id} value={p.id}>
                  {p.name}{p.is_default ? ' (default)' : ''}
                </option>
              ))}
            </select>
            {selectedPersona && (
              <p className="text-xs text-orange-600 dark:text-orange-400 mt-1 flex items-center gap-1">
                ✓ Model, fallback, routing, and memory settings all come from this persona
              </p>
            )}
            <p className="text-xs text-gray-400 mt-1">
              Assign a persona to route model selection through it. Changing the persona's model updates all agents using it automatically.
            </p>
          </div>

          {/* Direct model fallback — only shown if no persona */}
          {!form.persona_id && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Direct Model ID <span className="text-gray-400 font-normal">(fallback if no persona)</span>
              </label>
              <input value={form.model_id} onChange={e => setForm(f => ({ ...f, model_id: e.target.value }))}
                placeholder="e.g. ollama/glm4:latest"
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-orange-400" />
            </div>
          )}

          {/* System prompt */}
          <div>
            {form.persona_id ? (
              <>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Additional Instructions <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <div className="mb-2 p-3 rounded-lg bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-700 text-xs text-orange-700 dark:text-orange-300">
                  🎭 The <span className="font-semibold">{selectedPersona?.name}</span> persona prompt is already applied. Add role-specific instructions here that will be appended to it — or leave blank to use the persona prompt alone.
                </div>
                <textarea value={form.system_prompt} onChange={e => setForm(f => ({ ...f, system_prompt: e.target.value }))}
                  rows={5} placeholder="e.g. Always write unit tests. Follow PEP8. Use type hints."
                  className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none" />
              </>
            ) : (
              <>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">System Prompt</label>
                <textarea value={form.system_prompt} onChange={e => setForm(f => ({ ...f, system_prompt: e.target.value }))}
                  rows={8} placeholder="You are an expert..."
                  className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none" />
              </>
            )}
          </div>

          {/* Tools */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Tools</label>
            <div className="grid grid-cols-3 gap-2">
              {ALL_TOOLS.map(tool => (
                <label key={tool} className={`flex items-center gap-2 p-2.5 rounded-lg border cursor-pointer transition-colors ${
                  form.tools.includes(tool)
                    ? 'border-orange-400 bg-orange-50 dark:bg-orange-900/20'
                    : 'border-gray-200 dark:border-gray-600 hover:border-gray-300'
                }`}>
                  <input type="checkbox" checked={form.tools.includes(tool)} onChange={() => toggleTool(tool)} className="sr-only" />
                  <span className={`w-3.5 h-3.5 rounded border flex items-center justify-center flex-shrink-0 ${form.tools.includes(tool) ? 'bg-orange-500 border-orange-500' : 'border-gray-400'}`}>
                    {form.tools.includes(tool) && <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
                  </span>
                  <div>
                    <p className="text-xs font-mono font-medium text-gray-700 dark:text-gray-300">{tool}</p>
                    <p className="text-xs text-gray-400">{TOOL_DESCRIPTIONS[tool]}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Config */}
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Max Iterations</label>
              <input type="number" value={form.max_iterations} onChange={e => setForm(f => ({ ...f, max_iterations: +e.target.value }))}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Timeout (seconds)</label>
              <input type="number" value={form.timeout_seconds} onChange={e => setForm(f => ({ ...f, timeout_seconds: +e.target.value }))}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Memory</label>
              <select value={form.memory_enabled ? 'true' : 'false'} onChange={e => setForm(f => ({ ...f, memory_enabled: e.target.value === 'true' }))}
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400">
                <option value="true">Enabled</option>
                <option value="false">Disabled</option>
              </select>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
