'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'

const API_BASE = 'http://localhost:19000'
const AUTH = { 'Authorization': 'Bearer modelmesh_local_dev_key', 'Content-Type': 'application/json' }

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

  const loadData = useCallback(async () => {
    const [personasRes] = await Promise.all([
      fetch(`${API_BASE}/v1/personas`, { headers: AUTH }).then(r => r.json()).catch(() => ({ data: [] }))
    ])
    setPersonas(personasRes.data || [])

    if (agentId !== 'new') {
      const agentData = await fetch(`${API_BASE}/v1/agents/${agentId}`, { headers: AUTH })
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
          method: 'POST', headers: AUTH, body: JSON.stringify(body)
        }).then(r => r.json())
        router.push(`/agents/${res.id}`)
      } else {
        const res = await fetch(`${API_BASE}/v1/agents/${agentId}`, {
          method: 'PATCH', headers: AUTH, body: JSON.stringify(body)
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

      {/* View mode */}
      {!editing && agent && (
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
