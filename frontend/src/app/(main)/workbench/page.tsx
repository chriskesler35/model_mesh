'use client'

import { getApiBase, getAuthHeaders } from '@/lib/config'

import { useState, useEffect, useCallback } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'


const AGENT_ICONS: Record<string, string> = {
  coder: '💻', researcher: '🔍', designer: '🎨',
  reviewer: '🔎', planner: '📋', executor: '⚡', writer: '✍️',
}

interface Session { id: string; task: string; agent_type: string; model: string; status: string; created_at: string }
interface Model { id: string; model_id: string; display_name?: string; provider_name?: string }
interface PipelineSummary { id: string; method_id: string; initial_task: string; status: string; current_phase_index: number; phases: any[]; auto_approve: boolean; created_at: string }
interface ProjectSummary {
  id: string
  name: string
  path?: string
  source?: {
    type: string
    conversation_id?: string
    conversation_title?: string
    message_count?: number
    intake_file?: string | null
  }
}

async function readApiPayload(res: Response) {
  const text = await res.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

function getApiErrorMessage(payload: any, fallbackStatus: number) {
  if (typeof payload === 'string' && payload.trim()) return payload.trim()
  if (payload?.detail?.error?.message) return payload.detail.error.message
  if (payload?.detail && typeof payload.detail === 'string') return payload.detail
  if (payload?.message && typeof payload.message === 'string') return payload.message
  return String(fallbackStatus)
}

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
  const [projectName, setProjectName] = useState<string>('')
  const [models, setModels] = useState<Model[]>([])
  const [loadingModels, setLoadingModels] = useState(false)
  // Pipeline mode
  const [asPipeline, setAsPipeline] = useState(false)
  const [pipelineMethod, setPipelineMethod] = useState<string>('bmad')
  const [autoApprove, setAutoApprove] = useState(false)
  const [interactionMode, setInteractionMode] = useState<'interactive' | 'autonomous'>('interactive')
  const [delegateQaToAgent, setDelegateQaToAgent] = useState(true)
  // Active method stack from Methods page
  const [activeStack, setActiveStack] = useState<string[]>([])
  const [activeStackName, setActiveStackName] = useState<string>('')
  const [phasePreview, setPhasePreview] = useState<Array<{name: string; role: string; default_model: string; artifact_type: string; has_agent?: boolean; agent_name?: string | null; has_persona?: boolean; persona_name?: string | null; resolved_model?: string | null; resolved_via?: string | null}>>([])
  const [modelOverrides, setModelOverrides] = useState<Record<string, string>>({})
  const [customizeModels, setCustomizeModels] = useState(false)
  const [isPromotedProject, setIsPromotedProject] = useState(false)
  const [taskAutoFilled, setTaskAutoFilled] = useState(false)

  const fetchSessions = useCallback(async () => {
    const apiBase = getApiBase()
    const authHeaders = getAuthHeaders()
    const [sessRes, pipeRes] = await Promise.all([
      fetch(`${apiBase}/v1/workbench/sessions`, { headers: authHeaders }).then(r => r.json()).catch(() => ({ data: [] })),
      fetch(`${apiBase}/v1/workbench/pipelines`, { headers: authHeaders }).then(r => r.json()).catch(() => ({ data: [] })),
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
    const qAgentType = searchParams?.get('agent_type') || params.get('agent_type')
    if (pid) setProjectId(pid)
    if (qAgentType) setAgentType(qAgentType)
    if (pid || qAgentType) setShowNew(true)
  }, [searchParams])

  useEffect(() => {
    if (!projectId) {
      setProjectName('')
      setIsPromotedProject(false)
      setTaskAutoFilled(false)
      return
    }

    const apiBase = getApiBase()
    const authHeaders = getAuthHeaders()

    fetch(`${apiBase}/v1/projects/${projectId}`, { headers: authHeaders })
      .then(r => r.ok ? r.json() : null)
      .then(async (project: ProjectSummary | null) => {
        setProjectName(project?.name || '')
        const src = project?.source
        if (src?.type === 'conversation') {
          setIsPromotedProject(true)
          setAgentType('planner')
          // Attempt to read the intake file for richer task context
          let taskText = ''
          if (src.intake_file) {
            try {
              const fr = await fetch(
                `${apiBase}/v1/projects/${projectId}/files/read?file_path=${encodeURIComponent(src.intake_file)}`,
                { headers: authHeaders },
              )
              if (fr.ok) {
                const fd = await fr.json()
                const content: string = fd.content || ''
                const goalMatch = content.match(/- Initial User Goal:\s*(.+)/i)
                const dirMatch = content.match(/- Latest Assistant Direction:\s*(.+)/i)
                const goal = goalMatch?.[1]?.trim() || ''
                const direction = dirMatch?.[1]?.trim() || ''
                const parts = [
                  `Review CHAT-INTAKE.md and create a detailed project plan.\n`,
                  goal ? `**Initial Goal:** ${goal}\n` : '',
                  direction && direction !== 'N/A' ? `**Latest Direction:** ${direction}\n` : '',
                  `\nSource: Promoted from "${src.conversation_title || 'chat'}" (${src.message_count ?? 0} messages)`,
                  `Full context: See CHAT-INTAKE.md in project root.`,
                ]
                taskText = parts.filter(Boolean).join('\n')
              }
            } catch { /* fall through to metadata-only task */ }
          }
          if (!taskText) {
            taskText = [
              `Review CHAT-INTAKE.md and create a detailed project plan.\n`,
              `Source: Promoted from "${src.conversation_title || 'chat'}" (${src.message_count ?? 0} messages)`,
              `Full context: See CHAT-INTAKE.md in project root.`,
            ].join('\n')
          }
          setTask(taskText)
          setTaskAutoFilled(true)
        } else {
          setIsPromotedProject(false)
        }
      })
      .catch(() => setProjectName(''))
  }, [projectId])

  // Fetch active method stack + phase preview when pipeline mode changes
  useEffect(() => {
    if (!asPipeline) { setPhasePreview([]); setActiveStack([]); return }
    const apiBase = getApiBase()
    const authHeaders = getAuthHeaders()
    // Check if user has a method stack active
    fetch(`${apiBase}/v1/methods/active`, { headers: authHeaders })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d && d.stack && d.stack.length > 0) {
          setActiveStack(d.stack)
          setActiveStackName(d.name || d.stack.join(' + '))
          // Use the primary method from the stack for phase structure
          setPipelineMethod(d.stack[0])
        } else if (d && d.id && d.id !== 'standard') {
          setActiveStack([d.id])
          setActiveStackName(d.name || d.id)
          setPipelineMethod(d.id)
        } else {
          setActiveStack([])
          setActiveStackName('')
        }
      })
      .catch(() => {})
  }, [asPipeline])

  // Fetch phase preview when pipeline method changes
  useEffect(() => {
    if (!asPipeline || !pipelineMethod) { setPhasePreview([]); return }
    const apiBase = getApiBase()
    const authHeaders = getAuthHeaders()
    fetch(`${apiBase}/v1/workbench/pipelines/methods/${pipelineMethod}/phases`, { headers: authHeaders })
      .then(r => r.ok ? r.json() : { phases: [] })
      .then(d => {
        setPhasePreview(d.phases || [])
        setModelOverrides({})
      })
      .catch(() => setPhasePreview([]))
  }, [asPipeline, pipelineMethod])

  // Fetch available models for the dropdown.
  // Always refresh when opening the modal and paginate to avoid missing newer entries.
  useEffect(() => {
    if (!showNew) return
    const apiBase = getApiBase()
    const authHeaders = getAuthHeaders()
    let cancelled = false

    const fetchModels = async () => {
      setLoadingModels(true)
      try {
        const all: Model[] = []
        const limit = 250
        let offset = 0

        while (true) {
          const res = await fetch(
            `${apiBase}/v1/models?limit=${limit}&offset=${offset}&active_only=true&usable_only=true&chat_only=true`,
            { headers: authHeaders },
          )
          const d = await res.json().catch(() => ({ data: [] }))
          const page: Model[] = (d.data || []).filter((m: any) =>
            m.capabilities?.chat !== false && !m.capabilities?.image_generation,
          )
          all.push(...page)

          const got = (d.data || []).length
          if (got < limit) break
          offset += limit
        }

        if (cancelled) return

        const unique = Array.from(new Map(all.map(m => [m.model_id, m])).values())
        setModels(unique)

        // Preserve selected model if still present; otherwise pick first available.
        if (unique.length > 0 && !unique.some(m => m.model_id === model)) {
          setModel(unique[0].model_id)
        }
      } catch {
        if (!cancelled) setModels([])
      } finally {
        if (!cancelled) setLoadingModels(false)
      }
    }

    fetchModels()
    return () => { cancelled = true }
  }, [showNew])

  const createSession = async () => {
    if (!task.trim() || creating) return
    setCreating(true)
    try {
      const apiBase = getApiBase()
      const authHeaders = getAuthHeaders()
      const body: any = { task: task.trim(), agent_type: agentType, model }
      if (projectId) body.project_id = projectId
      const sessRes = await fetch(`${apiBase}/v1/workbench/sessions`, {
        method: 'POST', headers: authHeaders,
        body: JSON.stringify(body),
      })
      const session = await readApiPayload(sessRes)
      if (!sessRes.ok || !session?.id) {
        throw new Error(`Session creation failed: ${getApiErrorMessage(session, sessRes.status)}`)
      }

      if (asPipeline) {
        // Build model_overrides with priority:
        //   1. Per-phase explicit override (customize models)
        //   2. Session-level Model dropdown (applies to all phases)
        //   3. Persona model (backend resolves this automatically when nothing is sent)
        //   4. Template default (backend fallback)
        // We only send overrides when the user has set something explicitly —
        // absence of a key lets the backend do persona lookup per-phase.
        const effectiveOverrides: Record<string, string> = {}
        for (const ph of phasePreview) {
          if (modelOverrides[ph.name]) {
            effectiveOverrides[ph.name] = modelOverrides[ph.name]
          } else if (model) {
            // Session-level model applies when no per-phase override
            effectiveOverrides[ph.name] = model
          }
          // Otherwise: let backend use persona or template default
        }
        // Preserve any per-phase overrides for phases not in phasePreview (defensive)
        for (const [k, v] of Object.entries(modelOverrides)) {
          effectiveOverrides[k] = v
        }

        const pipeRes = await fetch(`${apiBase}/v1/workbench/pipelines`, {
          method: 'POST', headers: authHeaders,
          body: JSON.stringify({
            session_id: session.id,
            method_id: activeStack.length > 1 ? 'stack' : pipelineMethod,
            task: task.trim(),
            auto_approve: interactionMode === 'interactive' ? false : autoApprove,
            interaction_mode: interactionMode,
            delegate_qa_to_agent: interactionMode === 'autonomous' ? delegateQaToAgent : false,
            model_overrides: Object.keys(effectiveOverrides).length > 0 ? effectiveOverrides : undefined,
          }),
        })
        const pipeline = await readApiPayload(pipeRes)
        if (!pipeRes.ok || !pipeline?.id) {
          throw new Error(`Pipeline creation failed: ${getApiErrorMessage(pipeline, pipeRes.status)}`)
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
    waiting: 'idle',             // turn done, session open for follow-ups
    awaiting_approval: 'needs approval',
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
                  const apiBase = getApiBase()
                  const authHeaders = getAuthHeaders()
                  const res = await fetch(`${apiBase}/v1/workbench/sessions`, {
                    method: 'DELETE', headers: authHeaders,
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
          <a href="/workbench/builder"
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
            {'\u{1F527}'} Workflow Builder
          </a>
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
          <div className="w-full max-w-lg bg-white dark:bg-gray-900 rounded-2xl shadow-2xl flex flex-col max-h-[90vh]">
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between flex-shrink-0">
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">New Workbench Session</h2>
              <button onClick={() => { setShowNew(false); setIsPromotedProject(false); setTaskAutoFilled(false) }} className="text-gray-400 hover:text-gray-600">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="px-6 py-5 space-y-4 overflow-y-auto flex-1">
              {projectId && (
                <div className="rounded-lg border border-orange-200 dark:border-orange-700 bg-orange-50 dark:bg-orange-900/20 px-3 py-2 text-xs text-orange-700 dark:text-orange-300">
                  <div className="flex items-center gap-2">
                    <span>📁</span>
                    <span className="font-medium">
                      Project linked{projectName ? `: ${projectName}` : ''} — files will be written to disk
                    </span>
                    <code className="ml-auto font-mono opacity-60">{projectId.slice(0,8)}…</code>
                  </div>
                  {projectName && (
                    <div className="mt-1 pl-6 text-[11px] text-orange-600/90 dark:text-orange-300/90">
                      Launch context: {projectName}
                    </div>
                  )}
                </div>
              )}
              {isPromotedProject && taskAutoFilled && (
                <div className="rounded-lg border border-purple-200 dark:border-purple-700 bg-purple-50 dark:bg-purple-900/20 px-3 py-2 text-xs text-purple-700 dark:text-purple-300">
                  <div className="flex items-center gap-2">
                    <span>💬</span>
                    <span className="font-medium">Task pre-filled from promoted chat context — edit freely</span>
                  </div>
                  <div className="mt-1 pl-6 text-[11px] text-purple-600/90 dark:text-purple-300/90">
                    Agent defaulted to <strong>Planner</strong> · CHAT-INTAKE.md has the full transcript
                  </div>
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Task</label>
                <textarea value={task} onChange={e => setTask(e.target.value)} rows={isPromotedProject ? 6 : 4}
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
                    <div className="rounded-lg border border-indigo-200 dark:border-indigo-800 bg-white/80 dark:bg-gray-900/30 px-3 py-2 space-y-2">
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-indigo-700 dark:text-indigo-300">Engagement mode</div>
                      <label className="flex items-center gap-2 text-xs text-indigo-900 dark:text-indigo-200">
                        <input
                          type="radio"
                          name="interactionMode"
                          checked={interactionMode === 'interactive'}
                          onChange={() => setInteractionMode('interactive')}
                          className="text-indigo-600 focus:ring-indigo-400"
                        />
                        Interactive user Q&A (recommended)
                      </label>
                      <label className="flex items-center gap-2 text-xs text-indigo-900 dark:text-indigo-200">
                        <input
                          type="radio"
                          name="interactionMode"
                          checked={interactionMode === 'autonomous'}
                          onChange={() => setInteractionMode('autonomous')}
                          className="text-indigo-600 focus:ring-indigo-400"
                        />
                        Autonomous surrogate Q&A
                      </label>
                      {interactionMode === 'autonomous' && (
                        <label className="flex items-center gap-2 text-[11px] text-indigo-800 dark:text-indigo-200 pl-5">
                          <input
                            type="checkbox"
                            checked={delegateQaToAgent}
                            onChange={e => setDelegateQaToAgent(e.target.checked)}
                            className="rounded text-indigo-600 focus:ring-indigo-400"
                          />
                          Let the agent answer methodology questions as a surrogate user (visible in artifacts)
                        </label>
                      )}
                    </div>
                    <div className="text-[11px] text-indigo-800 dark:text-indigo-200 bg-white/70 dark:bg-gray-900/30 border border-indigo-200 dark:border-indigo-800 rounded-lg px-3 py-2">
                      This opens the supervisor-style pipeline view, not the standard chat thread. You will watch a live activity feed, send guidance between phases, and approve or reject artifacts as work moves forward.
                    </div>
                    {!projectId && (
                      <div className="p-2 rounded bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700 text-[11px] text-amber-800 dark:text-amber-200">
                        <div className="font-semibold">⚠ No project attached</div>
                        <div>Code phases will generate files but they won't be saved to disk. Go back and launch this session from a project to enable file writes + command execution.</div>
                      </div>
                    )}
                    {activeStack.length > 1 ? (
                      <div className="p-2 rounded bg-purple-50 dark:bg-purple-900/20 border border-purple-300 dark:border-purple-700 text-xs text-purple-900 dark:text-purple-200">
                        <div className="font-semibold flex items-center gap-1.5 mb-1">
                          <span>🔀</span> Using your active method stack: <span className="font-bold">{activeStackName}</span>
                        </div>
                        <div className="text-[11px] text-purple-700 dark:text-purple-300">
                          Phase structure from <b>{activeStack[0].toUpperCase()}</b>. Prompts from{' '}
                          {activeStack.slice(1).map(m => m.toUpperCase()).join(' + ')} applied to every phase.
                          Change your stack on the <a href="/methods" className="underline">Methods page</a>.
                        </div>
                      </div>
                    ) : (
                      <select value={pipelineMethod} onChange={e => setPipelineMethod(e.target.value)}
                        className="rounded-lg border border-indigo-300 dark:border-indigo-700 dark:bg-gray-800 dark:text-white px-2 py-1.5 text-xs">
                        <option value="bmad">BMAD — 6 phases (full lifecycle)</option>
                        <option value="gsd">GSD — 3 phases (ship fast)</option>
                        <option value="superpowers">SuperPowers — 4 phases (deep work)</option>
                      </select>
                    )}
                    <label className="flex items-center gap-2 text-xs text-indigo-900 dark:text-indigo-200">
                      <input type="checkbox" checked={autoApprove} onChange={e => setAutoApprove(e.target.checked)}
                        disabled={interactionMode === 'interactive'}
                        className="rounded text-indigo-600 focus:ring-indigo-400" />
                      Auto-approve each phase {interactionMode === 'interactive' ? '(disabled in interactive mode)' : ''}
                    </label>
                    {phasePreview.length > 0 && (() => {
                      const unresolved = phasePreview.filter(ph => !ph.resolved_model)
                      return (
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
                        {unresolved.length > 0 && !model && (
                          <div className="mb-2 p-2 rounded bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700 text-[10px] text-amber-800 dark:text-amber-200">
                            <div className="font-semibold mb-0.5">⚠ {unresolved.length} phase(s) using template defaults</div>
                            <div>
                              Go to the <strong>Agents page</strong> and bind an agent (with a persona) to these phases:{' '}
                              <span className="font-mono">{unresolved.map(p => p.name).join(', ')}</span>
                            </div>
                          </div>
                        )}
                        <div className="space-y-1">
                          {phasePreview.map((ph, i) => {
                            const effectiveModel = modelOverrides[ph.name] || model || ph.resolved_model || ph.default_model
                            const source = modelOverrides[ph.name] ? 'override' :
                              model ? 'session' :
                              ph.resolved_model ? 'persona' : 'default'
                            return (
                            <div key={i} className="flex items-center gap-1.5 text-[11px]">
                              <span className="text-gray-400 w-4 text-right">{i + 1}.</span>
                              <span className="font-medium text-indigo-900 dark:text-indigo-200 w-16 truncate">{ph.name}</span>
                              {ph.has_agent ? (
                                <span className="text-[9px] px-1 py-0.5 rounded bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300 font-medium" title={`Agent: ${ph.agent_name}`}>👤 {ph.agent_name}</span>
                              ) : (
                                <span className="text-[9px] px-1 py-0.5 rounded bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300 font-medium" title="No agent bound">no agent</span>
                              )}
                              {ph.has_persona && (
                                <span className="text-[9px] px-1 py-0.5 rounded bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300 font-medium" title={`Persona: ${ph.persona_name}`}>🎭 {ph.persona_name}</span>
                              )}
                              <span className="text-gray-400 truncate flex-1"></span>
                              {customizeModels ? (
                                <select
                                  value={modelOverrides[ph.name] || model || ph.resolved_model || ph.default_model}
                                  onChange={e => setModelOverrides(prev => ({ ...prev, [ph.name]: e.target.value }))}
                                  className="rounded border border-indigo-200 dark:border-indigo-700 dark:bg-gray-800 dark:text-white px-1 py-0.5 text-[10px] max-w-[150px]">
                                  {model && <option value={model}>{model} (session)</option>}
                                  {ph.resolved_model && ph.resolved_model !== model && <option value={ph.resolved_model}>{ph.resolved_model} ({ph.resolved_via || 'agent'})</option>}
                                  <option value={ph.default_model}>{ph.default_model} (template)</option>
                                  {models.filter(m => m.model_id !== model && m.model_id !== ph.resolved_model && m.model_id !== ph.default_model).map(m => (
                                    <option key={m.id} value={m.model_id}>{m.display_name || m.model_id}</option>
                                  ))}
                                </select>
                              ) : (
                                <span className={`font-mono text-[10px] truncate max-w-[110px] ${
                                  source === 'persona' ? 'text-green-600 dark:text-green-400' :
                                  source === 'override' ? 'text-indigo-600 dark:text-indigo-400' :
                                  source === 'session' ? 'text-indigo-600 dark:text-indigo-400' :
                                  'text-gray-400'
                                }`} title={`from ${source}`}>
                                  {effectiveModel}
                                </span>
                              )}
                            </div>
                            )
                          })}
                        </div>
                      </div>
                      )
                    })()}
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
            <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-800 flex gap-3 justify-end flex-shrink-0">
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
