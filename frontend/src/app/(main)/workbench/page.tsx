'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { useState, useEffect, useCallback } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'


const AGENT_ICONS: Record<string, string> = {
  coder: '💻', researcher: '🔍', designer: '🎨',
  reviewer: '🔎', planner: '📋', executor: '⚡', writer: '✍️',
}

interface Session { id: string; task: string; agent_type: string; model: string; status: string; created_at: string }
interface Model { id: string; model_id: string; display_name?: string; provider_name?: string }
interface PipelineSummary { id: string; method_id: string; initial_task: string; status: string; current_phase_index: number; phases: any[]; auto_approve: boolean; created_at: string }

const METHOD_ICONS: Record<string, string> = { bmad: '🧠', gsd: '⚡', superpowers: '🦸' }

export default function WorkbenchListPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [sessions, setSessions] = useState<Session[]>([])
  const [pipelines, setPipelines] = useState<PipelineSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [task, setTask] = useState('')
  const [agentType, setAgentType] = useState('coder')
  const [model, setModel] = useState('ollama/glm4:latest')
  const [creating, setCreating] = useState(false)
  const [projectId, setProjectId] = useState<string | null>(null)
  const [models, setModels] = useState<Model[]>([])
  const [loadingModels, setLoadingModels] = useState(false)
  // Pipeline mode
  const [asPipeline, setAsPipeline] = useState(false)
  const [pipelineMethod, setPipelineMethod] = useState<'bmad' | 'gsd' | 'superpowers'>('bmad')
  const [autoApprove, setAutoApprove] = useState(false)
  const [phasePreview, setPhasePreview] = useState<Array<{name: string; role: string; default_model: string; artifact_type: string}>>([])
  const [modelOverrides, setModelOverrides] = useState<Record<string, string>>({})
  const [customizeModels, setCustomizeModels] = useState(false)

  const fetchSessions = useCallback(async () => {
    const [sessRes, pipeRes] = await Promise.all([
      fetch(`${API_BASE}/v1/workbench/sessions`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ data: [] })),
      fetch(`${API_BASE}/v1/workbench/pipelines`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ data: [] })),
    ])
    setSessions(sessRes.data || [])
    setPipelines(pipeRes.data || [])
    setLoading(false)
  }, [])

  useEffect(() => { fetchSessions() }, [fetchSessions])

  // Auto-open new session modal if coming from a project or agent
  // Also check window.location as fallback (searchParams can be null on first render)
  useEffect(() => {
    const params = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '')
    const pid = searchParams?.get('project') || params.get('project')
    const agentType = searchParams?.get('agent_type') || params.get('agent_type')
    if (pid) setProjectId(pid)
    if (agentType) setAgentType(agentType)
    if (pid || agentType) setShowNew(true)
  }, [searchParams])

  // Fetch phase preview when pipeline method changes
  useEffect(() => {
    if (!asPipeline) { setPhasePreview([]); return }
    fetch(`${API_BASE}/v1/workbench/pipelines/methods/${pipelineMethod}/phases`, { headers: AUTH_HEADERS })
      .then(r => r.json())
      .then(d => {
        setPhasePreview(d.phases || [])
        setModelOverrides({})  // reset overrides when method changes
      })
      .catch(() => setPhasePreview([]))
  }, [asPipeline, pipelineMethod])

  // Fetch available models for the dropdown
  useEffect(() => {
    if (!showNew || models.length > 0) return
    setLoadingModels(true)
    fetch(`${API_BASE}/v1/models?limit=100`, { headers: AUTH_HEADERS })
      .then(r => r.json())
      .then(d => {
        const list: Model[] = (d.data || []).filter((m: any) =>
          m.capabilities?.chat !== false && !m.capabilities?.image_generation
        )
        setModels(list)
        // Default to first chat-capable model
        if (list.length > 0 && !model) setModel(list[0].model_id)
      })
      .catch(() => {})
      .finally(() => setLoadingModels(false))
  }, [showNew])

  const createSession = async () => {
    if (!task.trim() || creating) return
    setCreating(true)
    try {
      const body: any = { task: task.trim(), agent_type: agentType, model }
      if (projectId) body.project_id = projectId
      const sessRes = await fetch(`${API_BASE}/v1/workbench/sessions`, {
        method: 'POST', headers: AUTH_HEADERS,
        body: JSON.stringify(body),
      })
      const session = await sessRes.json()
      if (!sessRes.ok || !session?.id) {
        throw new Error(`Session creation failed: ${session?.detail || sessRes.status}`)
      }

      if (asPipeline) {
        // Build model_overrides: apply the main Model selection to every phase
        // unless the user has set a per-phase override via "customize models".
        // This makes "pick GLM-5 as my Coder" actually work: the main Model
        // dropdown overrides all phases, then per-phase overrides win over that.
        const effectiveOverrides: Record<string, string> = {}
        if (model) {
          for (const ph of phasePreview) {
            effectiveOverrides[ph.name] = modelOverrides[ph.name] || model
          }
        }
        // Also preserve any explicit per-phase overrides for phases that
        // weren't in phasePreview (shouldn't happen, but defensive)
        for (const [k, v] of Object.entries(modelOverrides)) {
          effectiveOverrides[k] = v
        }

        const pipeRes = await fetch(`${API_BASE}/v1/workbench/pipelines`, {
          method: 'POST', headers: AUTH_HEADERS,
          body: JSON.stringify({
            session_id: session.id,
            method_id: pipelineMethod,
            task: task.trim(),
            auto_approve: autoApprove,
            model_overrides: Object.keys(effectiveOverrides).length > 0 ? effectiveOverrides : undefined,
          }),
        })
        const pipeline = await pipeRes.json()
        if (!pipeRes.ok || !pipeline?.id) {
          throw new Error(`Pipeline creation failed: ${pipeline?.detail || pipeRes.status}`)
        }
        router.push(`/workbench/pipelines/${pipeline.id}`)
        return
      }
      router.push(`/workbench/${session.id}`)
    } catch (e: any) {
      console.error('Launch failed:', e)
      alert(`Launch failed: ${e.message || 'Unknown error'}`)
      setCreating(false)
    }
  }

  const STATUS_COLOR: Record<string, string> = {
    pending: 'text-yellow-600 bg-yellow-50',
    running: 'text-blue-600 bg-blue-50',
    completed: 'text-green-600 bg-green-50',
    failed: 'text-red-600 bg-red-50',
    cancelled: 'text-gray-500 bg-gray-50',
    waiting: 'text-amber-600 bg-amber-50',  // turn done, waiting for your follow-up
    awaiting_approval: 'text-amber-700 bg-amber-100',  // pipelines
  }
  const STATUS_LABEL: Record<string, string> = {
    waiting: 'waiting for you',
    awaiting_approval: 'awaiting approval',
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Workbench</h1>
          <p className="mt-1 text-sm text-gray-500">Watch agents build in real-time — and step in when needed</p>
        </div>
        <div className="flex items-center gap-2">
          {(sessions.length > 0 || pipelines.length > 0) && (
            <button
              onClick={async () => {
                const total = sessions.length + pipelines.length
                if (!confirm(`Delete ALL ${total} session(s) + pipeline(s)? Running items are kept. This cannot be undone.`)) return
                try {
                  const res = await fetch(`${API_BASE}/v1/workbench/sessions`, {
                    method: 'DELETE', headers: AUTH_HEADERS,
                  })
                  const data = await res.json()
                  if (!res.ok) throw new Error(data.detail || 'Delete failed')
                  await fetchSessions()
                } catch (e: any) {
                  alert(`Cleanup failed: ${e.message}`)
                }
              }}
              className="px-3 py-2 text-sm font-medium rounded-lg border border-red-300 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              title="Delete all sessions + attached pipelines (keeps running items)"
            >
              Clear All
            </button>
          )}
          <button onClick={() => setShowNew(true)}
            className="flex items-center gap-2 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium rounded-lg transition-colors">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Session
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="flex gap-1.5">{[0,1,2].map(i => <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />)}</div>
        </div>
      ) : sessions.length === 0 && pipelines.length === 0 ? (
        <div className="text-center py-20">
          <div className="text-5xl mb-4">🔨</div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">No sessions yet</h3>
          <p className="text-sm text-gray-500 mb-6">Start a workbench session to watch an agent build something in real-time.</p>
          <button onClick={() => setShowNew(true)}
            className="px-5 py-2.5 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium rounded-lg transition-colors">
            Start First Session
          </button>
        </div>
      ) : (
        <div className="space-y-6">
        {pipelines.length > 0 && (
          <div>
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
              🎭 Multi-Agent Pipelines
              <span className="text-xs font-normal text-gray-400">({pipelines.length})</span>
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {pipelines.map(p => (
                <button key={p.id} onClick={() => router.push(`/workbench/pipelines/${p.id}`)}
                  className="text-left bg-white dark:bg-gray-800 rounded-xl border border-indigo-200 dark:border-indigo-800 p-4 hover:border-indigo-400 hover:shadow-md transition-all">
                  <div className="flex items-start justify-between mb-3">
                    <span className="text-2xl">{METHOD_ICONS[p.method_id] || '🎭'}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLOR[p.status] || 'bg-gray-100 text-gray-600'}`}>{STATUS_LABEL[p.status] || p.status}</span>
                  </div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white line-clamp-2 mb-2">{p.initial_task}</p>
                  <p className="text-xs text-gray-400">
                    {p.method_id.toUpperCase()} · phase {Math.min(p.current_phase_index + 1, p.phases?.length || 0)}/{p.phases?.length || 0}
                    {p.auto_approve && ' · auto'}
                  </p>
                </button>
              ))}
            </div>
          </div>
        )}
        {sessions.length > 0 && (
          <div>
            {pipelines.length > 0 && (
              <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                🔨 Single-Agent Sessions
                <span className="text-xs font-normal text-gray-400">({sessions.length})</span>
              </h2>
            )}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {sessions.map(s => (
                <button key={s.id} onClick={() => router.push(`/workbench/${s.id}`)}
                  className="text-left bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 hover:border-orange-300 hover:shadow-md transition-all">
                  <div className="flex items-start justify-between mb-3">
                    <span className="text-2xl">{AGENT_ICONS[s.agent_type] || '🤖'}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLOR[s.status] || 'bg-gray-100 text-gray-600'}`}>{STATUS_LABEL[s.status] || s.status}</span>
                  </div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white line-clamp-2 mb-2">{s.task}</p>
                  <p className="text-xs text-gray-400">{s.agent_type} · {s.model}</p>
                </button>
              ))}
            </div>
          </div>
        )}
        </div>
      )}

      {showNew && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">New Workbench Session</h2>
              <button onClick={() => setShowNew(false)} className="text-gray-400 hover:text-gray-600">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              {projectId && (
                <div className="flex items-center gap-2 px-3 py-2 bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-700 rounded-lg text-xs text-orange-700 dark:text-orange-300">
                  <span>📁</span>
                  <span>Project linked — files will be written to disk</span>
                  <code className="ml-auto font-mono opacity-60">{projectId.slice(0,8)}…</code>
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Task</label>
                <textarea value={task} onChange={e => setTask(e.target.value)} rows={4}
                  placeholder="Describe what you want to build or accomplish..."
                  className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none" />
              </div>
              {/* Multi-agent pipeline toggle */}
              <div className="rounded-lg border border-indigo-200 dark:border-indigo-800 bg-indigo-50 dark:bg-indigo-900/20 p-3 space-y-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={asPipeline} onChange={e => setAsPipeline(e.target.checked)}
                    className="rounded text-indigo-600 focus:ring-indigo-400" />
                  <span className="text-sm font-medium text-indigo-900 dark:text-indigo-200">
                    🎭 Run as multi-agent pipeline
                  </span>
                </label>
                {asPipeline && (
                  <div className="pl-6 space-y-2">
                    <div className="text-xs text-indigo-700 dark:text-indigo-300">
                      Specialist agents hand off to each other through approval gates. <b>All phases use the Model you selected below</b> — customize per-phase if needed.
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <select value={pipelineMethod} onChange={e => setPipelineMethod(e.target.value as any)}
                        className="rounded-lg border border-indigo-300 dark:border-indigo-700 dark:bg-gray-800 dark:text-white px-2 py-1.5 text-xs">
                        <option value="bmad">BMAD — 6 phases (full lifecycle)</option>
                        <option value="gsd">GSD — 3 phases (ship fast)</option>
                        <option value="superpowers">SuperPowers — 4 phases (deep work)</option>
                      </select>
                      <label className="flex items-center gap-2 text-xs text-indigo-900 dark:text-indigo-200">
                        <input type="checkbox" checked={autoApprove} onChange={e => setAutoApprove(e.target.checked)}
                          className="rounded text-indigo-600 focus:ring-indigo-400" />
                        Auto-approve each phase
                      </label>
                    </div>
                    {phasePreview.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-indigo-200 dark:border-indigo-800">
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-[10px] uppercase tracking-wider font-semibold text-indigo-700 dark:text-indigo-300">
                            {phasePreview.length} phases
                          </span>
                          <button type="button" onClick={() => setCustomizeModels(v => !v)}
                            className="text-[10px] text-indigo-600 dark:text-indigo-400 hover:underline">
                            {customizeModels ? '← default models' : 'customize models →'}
                          </button>
                        </div>
                        <div className="space-y-1">
                          {phasePreview.map((ph, i) => (
                            <div key={i} className="flex items-center gap-2 text-[11px]">
                              <span className="text-gray-400 w-4 text-right">{i + 1}.</span>
                              <span className="font-medium text-indigo-900 dark:text-indigo-200 w-20 truncate">{ph.name}</span>
                              <span className="text-gray-500 truncate flex-1">{ph.role}</span>
                              {customizeModels ? (
                                <select
                                  value={modelOverrides[ph.name] || model || ph.default_model}
                                  onChange={e => setModelOverrides(prev => ({ ...prev, [ph.name]: e.target.value }))}
                                  className="rounded border border-indigo-200 dark:border-indigo-700 dark:bg-gray-800 dark:text-white px-1 py-0.5 text-[10px] max-w-[150px]">
                                  {model && <option value={model}>{model} (session default)</option>}
                                  <option value={ph.default_model}>{ph.default_model} (phase default)</option>
                                  {models.filter(m => m.model_id !== model && m.model_id !== ph.default_model).map(m => (
                                    <option key={m.id} value={m.model_id}>{m.display_name || m.model_id}</option>
                                  ))}
                                </select>
                              ) : (
                                <span className="font-mono text-[10px] text-gray-400 truncate max-w-[120px]">
                                  {modelOverrides[ph.name] || model || ph.default_model}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Agent</label>
                  <select value={agentType} onChange={e => setAgentType(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400">
                    {Object.entries(AGENT_ICONS).map(([k, icon]) => <option key={k} value={k}>{icon} {k}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Model</label>
                  {loadingModels ? (
                    <div className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm text-gray-400">Loading models…</div>
                  ) : models.length > 0 ? (
                    <select value={model} onChange={e => setModel(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400">
                      {Object.entries(
                        models.reduce((acc, m) => {
                          const p = m.provider_name || 'other'
                          if (!acc[p]) acc[p] = []
                          acc[p].push(m)
                          return acc
                        }, {} as Record<string, Model[]>)
                      ).map(([provider, pModels]) => (
                        <optgroup key={provider} label={provider.charAt(0).toUpperCase() + provider.slice(1)}>
                          {pModels.map(m => (
                            <option key={m.id} value={m.model_id}>
                              {m.display_name || m.model_id}
                            </option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  ) : (
                    <input value={model} onChange={e => setModel(e.target.value)}
                      placeholder="e.g. llama3.1:8b"
                      className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
                  )}
                </div>
              </div>
            </div>
            <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-800 flex gap-3 justify-end">
              <button onClick={() => setShowNew(false)}
                className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50">Cancel</button>
              <button onClick={createSession} disabled={!task.trim() || creating}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-orange-500 hover:bg-orange-600 disabled:bg-gray-200 text-white disabled:text-gray-400 transition-colors">
                {creating ? 'Launching...' : '🚀 Launch'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
