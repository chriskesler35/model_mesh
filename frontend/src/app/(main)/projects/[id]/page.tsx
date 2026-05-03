'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'
import { RunPanel } from '@/components/RunPanel'
import { renderMarkdown } from '@/lib/markdown'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'

// ─── Sandbox Panel ──────────────────────────────────────────────────────────
function SandboxPanel({ projectId }: { projectId: string }) {
  const [status, setStatus] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [packages, setPackages] = useState('')
  const [snapshotMsg, setSnapshotMsg] = useState('DevForgeAI snapshot')
  const [envKey, setEnvKey] = useState('')
  const [envVal, setEnvVal] = useState('')
  const [feedback, setFeedback] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  const fb = (type: 'ok' | 'err', text: string) => {
    setFeedback({ type, text })
    setTimeout(() => setFeedback(null), 4000)
  }

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/v1/sandbox/projects/${projectId}/status`, { headers: AUTH_HEADERS })
      if (res.ok) setStatus(await res.json())
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [projectId])

  useEffect(() => { refresh() }, [refresh])

  const act = async (label: string, url: string, method: string, body?: any) => {
    setBusy(label)
    try {
      const res = await fetch(`${API_BASE}${url}`, {
        method, headers: AUTH_HEADERS, body: body ? JSON.stringify(body) : undefined
      })
      const data = await res.json()
      if (res.ok) { fb('ok', data.message || `${label} succeeded`); await refresh() }
      else fb('err', data.detail || `${label} failed`)
    } catch (e: any) { fb('err', e.message) }
    finally { setBusy(null) }
  }

  if (loading) return <div className="text-sm text-gray-400 py-8 text-center">Loading sandbox status…</div>
  if (!status) return <div className="text-sm text-red-400 py-8 text-center">Failed to load sandbox status</div>

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      {feedback && (
        <div className={`px-4 py-2 rounded-lg text-sm border ${feedback.type === 'ok' ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 border-green-200 dark:border-green-700' : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border-red-200 dark:border-red-700'}`}>
          {feedback.type === 'ok' ? '✓ ' : '✗ '}{feedback.text}
        </div>
      )}

      {/* Status overview */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">📊 Sandbox Status</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
            <p className="text-gray-400 uppercase tracking-wider mb-1">Path</p>
            <p className={`font-mono ${status.path_exists ? 'text-green-600' : 'text-red-500'}`}>
              {status.path_exists ? '✓ exists' : '✗ missing'}
            </p>
          </div>
          <div className="p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
            <p className="text-gray-400 uppercase tracking-wider mb-1">Venv</p>
            <p className={`font-mono ${status.venv_exists ? 'text-green-600' : 'text-gray-500'}`}>
              {status.venv_exists ? '✓ active' : '—'}
            </p>
          </div>
          <div className="p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
            <p className="text-gray-400 uppercase tracking-wider mb-1">Git</p>
            <p className={`font-mono ${status.git_initialized ? 'text-green-600' : 'text-gray-500'}`}>
              {status.git_initialized ? '✓ initialized' : '—'}
            </p>
          </div>
          <div className="p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
            <p className="text-gray-400 uppercase tracking-wider mb-1">Packages</p>
            <p className="font-mono text-gray-700 dark:text-gray-300">
              {status.installed_packages?.length || 0}
            </p>
          </div>
        </div>
      </div>

      {/* Virtual Environment */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">🐍 Virtual Environment</h3>
        {status.venv_exists ? (
          <div className="space-y-3">
            <p className="text-xs text-gray-500 font-mono">{status.venv_path}</p>
            {status.installed_packages?.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {status.installed_packages.map((pkg: string) => (
                  <span key={pkg} className="text-xs px-2 py-0.5 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400 rounded-full border border-blue-200 dark:border-blue-700">{pkg}</span>
                ))}
              </div>
            )}
            <div className="flex items-center gap-2">
              <input value={packages} onChange={e => setPackages(e.target.value)}
                placeholder="flask requests numpy…"
                className="flex-1 text-sm px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-white" />
              <button onClick={() => { if (packages.trim()) act('Install', `/v1/sandbox/projects/${projectId}/install`, 'POST', { requirements: packages.trim() }) }}
                disabled={!!busy || !packages.trim()}
                className="px-3 py-1.5 text-xs font-medium bg-blue-500 hover:bg-blue-600 text-white rounded-lg disabled:opacity-50">
                {busy === 'Install' ? '…' : 'Install'}
              </button>
            </div>
            <button onClick={() => act('Delete venv', `/v1/sandbox/projects/${projectId}/venv`, 'DELETE')}
              disabled={!!busy}
              className="text-xs text-red-500 hover:text-red-700 font-medium disabled:opacity-50">
              Remove virtual environment
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-gray-500">No virtual environment. Create one to install packages in an isolated Python environment.</p>
            <div className="flex items-center gap-2">
              <input value={packages} onChange={e => setPackages(e.target.value)}
                placeholder="Initial packages (optional): flask requests…"
                className="flex-1 text-sm px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-white" />
              <button onClick={() => act('Create venv', `/v1/sandbox/projects/${projectId}/venv`, 'POST', { requirements: packages.trim() || null })}
                disabled={!!busy}
                className="px-3 py-1.5 text-xs font-medium bg-green-500 hover:bg-green-600 text-white rounded-lg disabled:opacity-50">
                {busy === 'Create venv' ? '…' : 'Create Venv'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Git Snapshots */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">📸 Git Snapshots</h3>
        {!status.git_initialized ? (
          <div className="space-y-3">
            <p className="text-xs text-gray-500">Git not initialized. Initialize to enable snapshots and rollbacks.</p>
            <button onClick={() => act('Git init', `/v1/sandbox/projects/${projectId}/git/init`, 'POST')}
              disabled={!!busy}
              className="px-3 py-1.5 text-xs font-medium bg-gray-700 hover:bg-gray-800 text-white rounded-lg disabled:opacity-50">
              {busy === 'Git init' ? '…' : 'Initialize Git'}
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Git status */}
            {status.git_status && (
              <pre className="text-xs font-mono text-gray-500 bg-gray-50 dark:bg-gray-900 p-2 rounded-lg overflow-x-auto max-h-24">{status.git_status || '(clean)'}</pre>
            )}
            {/* Create snapshot */}
            <div className="flex items-center gap-2">
              <input value={snapshotMsg} onChange={e => setSnapshotMsg(e.target.value)}
                placeholder="Snapshot message"
                className="flex-1 text-sm px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-white" />
              <button onClick={() => act('Snapshot', `/v1/sandbox/projects/${projectId}/snapshot`, 'POST', { message: snapshotMsg })}
                disabled={!!busy || !snapshotMsg.trim()}
                className="px-3 py-1.5 text-xs font-medium bg-orange-500 hover:bg-orange-600 text-white rounded-lg disabled:opacity-50">
                {busy === 'Snapshot' ? '…' : '📸 Snapshot'}
              </button>
            </div>
            {/* Snapshot history */}
            {status.snapshots?.length > 0 && (
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                <table className="w-full text-xs">
                  <thead><tr className="bg-gray-50 dark:bg-gray-900"><th className="px-3 py-1.5 text-left text-gray-500 font-medium">Hash</th><th className="px-3 py-1.5 text-left text-gray-500 font-medium">Message</th><th className="px-3 py-1.5 text-right text-gray-500 font-medium">Actions</th></tr></thead>
                  <tbody>
                    {status.snapshots.map((s: { hash: string; message: string }) => (
                      <tr key={s.hash} className="border-t border-gray-100 dark:border-gray-800">
                        <td className="px-3 py-1.5 font-mono text-orange-600">{s.hash}</td>
                        <td className="px-3 py-1.5 text-gray-700 dark:text-gray-300">{s.message}</td>
                        <td className="px-3 py-1.5 text-right">
                          <button onClick={() => { if (confirm(`Rollback to ${s.hash}? A safety snapshot will be created first.`)) act('Rollback', `/v1/sandbox/projects/${projectId}/rollback`, 'POST', { commit_hash: s.hash }) }}
                            disabled={!!busy}
                            className="text-orange-500 hover:text-orange-700 font-medium disabled:opacity-50">
                            ↩ Rollback
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {(!status.snapshots || status.snapshots.length === 0) && (
              <p className="text-xs text-gray-400">No snapshots yet. Create one to save the current state.</p>
            )}
          </div>
        )}
      </div>

      {/* Environment Variables */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">🔑 Environment Variables</h3>
        {status.env_vars && Object.keys(status.env_vars).length > 0 ? (
          <div className="space-y-2 mb-3">
            {Object.entries(status.env_vars).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2 text-xs">
                <span className="font-mono text-gray-700 dark:text-gray-300 font-semibold">{k}</span>
                <span className="text-gray-400">=</span>
                <span className="font-mono text-gray-500 truncate flex-1">{String(v)}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-400 mb-3">No environment variables set.</p>
        )}
        <div className="flex items-center gap-2">
          <input value={envKey} onChange={e => setEnvKey(e.target.value)}
            placeholder="KEY"
            className="w-32 text-xs px-2 py-1.5 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 font-mono text-gray-900 dark:text-white" />
          <span className="text-gray-400">=</span>
          <input value={envVal} onChange={e => setEnvVal(e.target.value)}
            placeholder="value"
            className="flex-1 text-xs px-2 py-1.5 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 font-mono text-gray-900 dark:text-white" />
          <button onClick={() => {
            if (!envKey.trim()) return
            const current = { ...(status.env_vars || {}), [envKey.trim()]: envVal }
            act('Set env', `/v1/sandbox/projects/${projectId}/env-vars`, 'POST', current)
            setEnvKey(''); setEnvVal('')
          }}
            disabled={!!busy || !envKey.trim()}
            className="px-3 py-1.5 text-xs font-medium bg-purple-500 hover:bg-purple-600 text-white rounded-lg disabled:opacity-50">
            {busy === 'Set env' ? '…' : 'Set'}
          </button>
        </div>
      </div>
    </div>
  )
}


interface FileNode { name: string; path: string; type: 'file' | 'dir'; size: number; children?: FileNode[] }
interface WorkbenchSessionLite {
  id: string
  project_id: string | null
  agent_type?: string
  status: string
}

interface PersonaLite {
  id: string
  name: string
  primary_model_id?: string | null
}

interface AgentLite {
  id: string
  name: string
  agent_type: string
  model_id?: string | null
  resolved_model_id?: string | null
  is_active?: boolean
}

interface ModelLite {
  id: string
  model_id: string
  display_name?: string
}

const WORKBENCH_SEED_TASK: Record<string, string> = {
  coder: 'Continue building this project. Focus on the next scoped improvement and summarize verification steps.',
  reviewer: 'Run a code review for this project and report the most important findings first.',
}

const FILE_ICONS: Record<string, string> = {
  py: '🐍', ts: '🔷', tsx: '🔷', js: '🟨', jsx: '🟨', json: '📋',
  md: '📝', txt: '📄', html: '🌐', css: '🎨', env: '🔒',
  gitignore: '🚫', toml: '⚙️', yaml: '⚙️', yml: '⚙️',
}

function fileIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() || ''
  return FILE_ICONS[ext] || '📄'
}

function FileTree({ nodes, onSelect, selected, depth = 0 }: {
  nodes: FileNode[]; onSelect: (n: FileNode) => void
  selected: string | null; depth?: number
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({})
  return (
    <div>
      {nodes.map(n => (
        <div key={n.path}>
          {n.type === 'dir' ? (
            <div>
              <button onClick={() => setOpen(o => ({ ...o, [n.path]: !o[n.path] }))}
                className="w-full flex items-center gap-1.5 px-2 py-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded text-left transition-colors"
                style={{ paddingLeft: `${8 + depth * 12}px` }}>
                <span className="text-gray-400 text-xs">{open[n.path] ? '▼' : '▶'}</span>
                <span className="text-sm">📁</span>
                <span className="text-sm text-gray-700 dark:text-gray-300">{n.name}</span>
              </button>
              {open[n.path] && n.children && (
                <FileTree nodes={n.children} onSelect={onSelect} selected={selected} depth={depth + 1} />
              )}
            </div>
          ) : (
            <button onClick={() => onSelect(n)}
              className={`w-full flex items-center gap-1.5 px-2 py-1 rounded text-left transition-colors ${
                selected === n.path
                  ? 'bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300'
                  : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400'
              }`}
              style={{ paddingLeft: `${8 + depth * 12}px` }}>
              <span className="text-sm">{fileIcon(n.name)}</span>
              <span className="text-sm truncate">{n.name}</span>
              <span className="ml-auto text-xs text-gray-300">{n.size > 1024 ? `${(n.size/1024).toFixed(1)}k` : `${n.size}b`}</span>
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

export default function ProjectDetailPage() {
  const { id } = useParams() as { id: string }
  const router = useRouter()

  const [project, setProject] = useState<any>(null)
  const [tree, setTree] = useState<FileNode[]>([])
  const [selectedFile, setSelectedFile] = useState<FileNode | null>(null)
  const [fileContent, setFileContent] = useState<string | null>(null)
  const [loadingFile, setLoadingFile] = useState(false)
  const [activeTab, setActiveTab] = useState<'files' | 'sandbox' | 'run'>('files')
  const [sandboxSaving, setSandboxSaving] = useState(false)

  const setSandboxMode = async (mode: 'restricted' | 'full') => {
    setSandboxSaving(true)
    try {
      await fetch(`${API_BASE}/v1/projects/${id}/sandbox`, {
        method: 'POST', headers: AUTH_HEADERS, body: JSON.stringify({ mode })
      })
      setProject((p: any) => ({ ...p, sandbox_mode: mode }))
    } finally {
      setSandboxSaving(false)
    }
  }
  const [loading, setLoading] = useState(true)
  const [personas, setPersonas] = useState<PersonaLite[]>([])
  const [agents, setAgents] = useState<AgentLite[]>([])
  const [models, setModels] = useState<ModelLite[]>([])
  const [selectedPersonaId, setSelectedPersonaId] = useState('')
  const [selectedAgentId, setSelectedAgentId] = useState('')
  const [selectedModelId, setSelectedModelId] = useState('')
  const [requestIntent, setRequestIntent] = useState('')
  const [autoAgentRouting, setAutoAgentRouting] = useState(true)
  const [showAdvancedLaunch, setShowAdvancedLaunch] = useState(false)
  const [launchPrefsLoaded, setLaunchPrefsLoaded] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [saving, setSaving] = useState(false)

  const fetchProject = useCallback(async () => {
    const [proj, files] = await Promise.all([
      fetch(`${API_BASE}/v1/projects/${id}`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/v1/projects/${id}/files`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ tree: [] })),
    ])
    if (!proj || proj.detail) { router.push('/projects'); return }
    setProject(proj)
    setEditName(proj.name)
    setEditDesc(proj.description || '')
    setTree(files.tree || [])
    setLoading(false)
  }, [id, router])

  useEffect(() => { fetchProject() }, [fetchProject])

  // Restore all advanced launch prefs from localStorage on mount.
  useEffect(() => {
    try {
      const k = (key: string) => localStorage.getItem(`project:${id}:${key}`)
      const open = k('advanced-launch-open')
      if (open === '1') setShowAdvancedLaunch(true)
      if (open === '0') setShowAdvancedLaunch(false)
      const persona = k('launch-persona')
      if (persona !== null) setSelectedPersonaId(persona)
      const agent = k('launch-agent')
      if (agent !== null) setSelectedAgentId(agent)
      const model = k('launch-model')
      if (model !== null) setSelectedModelId(model)
      const intent = k('launch-intent')
      if (intent !== null) setRequestIntent(intent)
      const autoRoute = k('launch-auto-route')
      if (autoRoute !== null) setAutoAgentRouting(autoRoute !== '0')
    } catch {
      // Ignore storage errors in restricted environments.
    } finally {
      setLaunchPrefsLoaded(true)
    }
  }, [id])

  // Persist advanced launch prefs whenever they change (skip before restored).
  useEffect(() => {
    if (!launchPrefsLoaded) return
    try {
      const s = (key: string, val: string) => localStorage.setItem(`project:${id}:${key}`, val)
      s('advanced-launch-open', showAdvancedLaunch ? '1' : '0')
      s('launch-persona', selectedPersonaId)
      s('launch-agent', selectedAgentId)
      s('launch-model', selectedModelId)
      s('launch-intent', requestIntent)
      s('launch-auto-route', autoAgentRouting ? '1' : '0')
    } catch {
      // Ignore storage errors in restricted environments.
    }
  }, [id, launchPrefsLoaded, showAdvancedLaunch, selectedPersonaId, selectedAgentId, selectedModelId, requestIntent, autoAgentRouting])

  useEffect(() => {
    const loadLaunchOptions = async () => {
      try {
        const [personaRes, agentRes, modelRes] = await Promise.all([
          fetch(`${API_BASE}/v1/personas?limit=100`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ data: [] })),
          fetch(`${API_BASE}/v1/agents?limit=100`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ data: [] })),
          fetch(`${API_BASE}/v1/models?active_only=true&usable_only=true&validated_only=true&chat_only=true&limit=250`, { headers: AUTH_HEADERS })
            .then(r => r.json()).catch(() => ({ data: [] })),
        ])
        setPersonas(personaRes.data || [])
        setAgents((agentRes.data || []).filter((a: AgentLite) => a.is_active !== false))
        setModels(modelRes.data || [])
      } catch {
        // Optional launcher helpers only.
      }
    }
    loadLaunchOptions()
  }, [])

  const inferAgentType = (request: string): string => {
    const text = request.toLowerCase()
    if (/review|audit|qa|test|bug|regression/.test(text)) return 'reviewer'
    if (/design|ux|ui|wireframe/.test(text)) return 'designer'
    if (/plan|roadmap|strategy|break down/.test(text)) return 'planner'
    if (/research|investigate|compare|analyze/.test(text)) return 'researcher'
    if (/execute|run|ship|deploy/.test(text)) return 'executor'
    if (/write|docs|documentation|copy/.test(text)) return 'writer'
    return 'coder'
  }

  const selectedPersona = personas.find(p => p.id === selectedPersonaId) || null
  const selectedAgent = agents.find(a => a.id === selectedAgentId) || null

  const resolveLaunchAgentType = (): string => {
    if (selectedAgent?.agent_type) return selectedAgent.agent_type
    if (autoAgentRouting) return inferAgentType(requestIntent)
    return 'coder'
  }

  const resolveLaunchModelRef = (): string | undefined => {
    if (selectedModelId) {
      const model = models.find(m => m.id === selectedModelId)
      if (model?.model_id) return model.model_id
    }

    if (selectedAgent?.resolved_model_id) {
      return selectedAgent.resolved_model_id
    }

    if (selectedAgent?.model_id) {
      const model = models.find(m => m.id === selectedAgent.model_id)
      if (model?.model_id) return model.model_id
    }

    if (selectedPersona?.primary_model_id) {
      const model = models.find(m => m.id === selectedPersona.primary_model_id)
      if (model?.model_id) return model.model_id
    }

    return undefined
  }

  const launchSummary = [
    selectedPersona ? `Persona: ${selectedPersona.name}` : 'Persona: Auto',
    selectedAgent ? `Agent: ${selectedAgent.name}` : `Agent: ${resolveLaunchAgentType()}`,
    selectedModelId ? 'Model: Custom' : 'Model: Auto',
  ].join(' | ')

  // Auto-refresh file tree when a Workbench session for this project completes
  useEffect(() => {
    let lastStatus: string | null = null
    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/v1/workbench/sessions`, { headers: AUTH_HEADERS })
        const data = await res.json()
        const mine = (data.data || []).find((s: any) => s.project_id === id)
        if (!mine) return
        const isActive = mine.status === 'running' || mine.status === 'pending'
        // When a session transitions from active -> done/failed, refresh the tree
        if (lastStatus && ['running', 'pending'].includes(lastStatus) && !isActive) {
          fetchProject()
        }
        lastStatus = mine.status
      } catch { /* ignore */ }
    }
    const timer = setInterval(poll, 4000)
    return () => clearInterval(timer)
  }, [id, fetchProject])

  // Auto-refresh file tree when a Workbench session for this project is active
  useEffect(() => {
    let lastStatus: string | null = null
    const poll = async () => {
      try {
        const res = await fetch('/v1/workbench/sessions', { headers: AUTH_HEADERS })
        const data = await res.json()
        const mine = (data.data || []).find((s: any) => s.project_id === id)
        if (!mine) return
        const isActive = mine.status === 'running' || mine.status === 'pending'
        // When a session transitions from active -> completed/failed, refresh the tree
        if (lastStatus && ['running', 'pending'].includes(lastStatus) && !isActive) {
          fetchProject()
        }
        lastStatus = mine.status
      } catch { /* ignore */ }
    }
    const timer = setInterval(poll, 4000)
    return () => clearInterval(timer)
  }, [id, fetchProject])

  const openFile = async (node: FileNode) => {
    setSelectedFile(node)
    setFileContent(null)
    setLoadingFile(true)
    const res = await fetch(`${API_BASE}/v1/projects/${id}/files/read?file_path=${encodeURIComponent(node.path)}`, { headers: AUTH_HEADERS })
      .then(r => r.json()).catch(() => ({ content: 'Failed to load file.' }))
    setFileContent(res.content || '')
    setLoadingFile(false)
  }

  const saveProject = async () => {
    setSaving(true)
    await fetch(`${API_BASE}/v1/projects/${id}`, {
      method: 'PATCH', headers: AUTH_HEADERS,
      body: JSON.stringify({ name: editName, description: editDesc })
    })
    setProject((p: any) => ({ ...p, name: editName, description: editDesc }))
    setEditing(false)
    setSaving(false)
  }

  const openProjectSession = async () => {
    const preferredAgent = resolveLaunchAgentType()
    const resolvedModel = resolveLaunchModelRef()
    const seededTask = requestIntent.trim() || WORKBENCH_SEED_TASK[preferredAgent] || WORKBENCH_SEED_TASK.coder

    try {
      const listRes = await fetch(`${API_BASE}/v1/workbench/sessions`, { headers: AUTH_HEADERS })
      const listData = listRes.ok ? await listRes.json() : { data: [] }
      const sessions: WorkbenchSessionLite[] = (listData?.data || []).filter((s: WorkbenchSessionLite) => s.project_id === id)

      const matchesPreferredAgent = (s: WorkbenchSessionLite) => (s.agent_type || 'coder') === preferredAgent
      const isContinuable = (s: WorkbenchSessionLite) => !['completed', 'failed', 'cancelled'].includes(s.status)

      const reusable =
        sessions.find(s => matchesPreferredAgent(s) && (s.status === 'running' || s.status === 'pending' || s.status === 'waiting')) ||
        sessions.find(s => matchesPreferredAgent(s) && isContinuable(s)) ||
        sessions.find(s => isContinuable(s))

      if (reusable?.id) {
        router.push(`/workbench/${reusable.id}`)
        return
      }

      const createRes = await fetch(`${API_BASE}/v1/workbench/sessions`, {
        method: 'POST',
        headers: AUTH_HEADERS,
        body: JSON.stringify({
          project_id: id,
          agent_type: preferredAgent,
          model: resolvedModel,
          task: seededTask,
        }),
      })

      if (!createRes.ok) {
        throw new Error(`HTTP ${createRes.status}`)
      }

      const created = await createRes.json()
      if (created?.id) {
        router.push(`/workbench/${created.id}`)
        return
      }

      throw new Error('Session create returned no id')
    } catch {
      const query = new URLSearchParams({ project: id, agent_type: preferredAgent })
      if (resolvedModel) query.set('model', resolvedModel)
      if (selectedPersonaId) query.set('persona', selectedPersonaId)
      if (selectedAgentId) query.set('agent', selectedAgentId)
      router.push(`/workbench?${query.toString()}`)
    }
  }

  if (loading) return (
    <div className="flex justify-center py-16">
      <div className="flex gap-1.5">{[0,1,2].map(i => <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />)}</div>
    </div>
  )

  return (
    <div className="flex flex-col h-full -m-6 lg:-m-10">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-3 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
        <button onClick={() => router.push('/projects')}
          className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 transition-colors">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
        </button>
        <div className="flex-1 min-w-0">
          {editing ? (
            <div className="flex items-center gap-2">
              <input value={editName} onChange={e => setEditName(e.target.value)}
                className="text-sm font-semibold rounded border border-orange-400 px-2 py-0.5 dark:bg-gray-800 dark:text-white" />
              <input value={editDesc} onChange={e => setEditDesc(e.target.value)}
                placeholder="Description"
                className="text-sm rounded border border-gray-300 px-2 py-0.5 dark:bg-gray-800 dark:text-white flex-1" />
              <button onClick={saveProject} disabled={saving}
                className="px-2 py-1 text-xs bg-orange-500 text-white rounded">{saving ? '...' : 'Save'}</button>
              <button onClick={() => setEditing(false)} className="px-2 py-1 text-xs border border-gray-300 rounded text-gray-600">Cancel</button>
            </div>
          ) : (
            <div>
              <button onClick={() => setEditing(true)} className="text-sm font-semibold text-gray-900 dark:text-white hover:text-orange-600 transition-colors">
                {project.name}
              </button>
              <p className="text-xs text-gray-400 font-mono truncate">{project.path}</p>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`text-xs px-2 py-0.5 rounded-full ${project.path_exists ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'}`}>
            {project.path_exists ? '✓ path found' : '✗ path missing'}
          </span>

          {/* Sandbox mode toggle */}
          <div className="flex items-center gap-1 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
            <button
              onClick={() => setSandboxMode('restricted')}
              disabled={sandboxSaving}
              title="Restricted: agent confined to project folder"
              className={`px-2 py-1 text-xs font-medium transition-colors ${
                project.sandbox_mode !== 'full'
                  ? 'bg-green-100 text-green-700 dark:bg-green-900/40'
                  : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >🔒 Restricted</button>
            <button
              onClick={() => setSandboxMode('full')}
              disabled={sandboxSaving}
              title="Full Access: agent has unrestricted system access"
              className={`px-2 py-1 text-xs font-medium transition-colors ${
                project.sandbox_mode === 'full'
                  ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40'
                  : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >🔓 Full</button>
          </div>

          <button onClick={openProjectSession}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-500 hover:bg-orange-600 text-white text-xs font-medium rounded-lg transition-colors">
            🚀 Open in Workbench
          </button>
        </div>
      </div>

      <div className="px-6 py-2.5 bg-orange-50/60 dark:bg-orange-900/10 border-b border-orange-100 dark:border-orange-900/30">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[11px] text-gray-600 dark:text-gray-300">{launchSummary}</p>
          <button
            onClick={() => setShowAdvancedLaunch(v => !v)}
            className="text-xs px-2.5 py-1 rounded-lg border border-orange-200 dark:border-orange-700 bg-white dark:bg-gray-900 text-orange-700 dark:text-orange-300 hover:bg-orange-100/50 dark:hover:bg-orange-900/20"
          >
            {showAdvancedLaunch ? 'Hide advanced launch' : 'Advanced launch options'}
          </button>
        </div>

        {showAdvancedLaunch && (
          <div className="mt-2 pt-2 border-t border-orange-200/70 dark:border-orange-800/60">
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={requestIntent}
                onChange={e => setRequestIntent(e.target.value)}
                placeholder="What do you want to fine-tune or change? (optional)"
                className="min-w-[260px] flex-1 text-xs px-2.5 py-1.5 rounded-lg border border-orange-200 dark:border-orange-700 bg-white dark:bg-gray-900 text-gray-900 dark:text-white"
              />

              <select
                value={selectedPersonaId}
                onChange={e => setSelectedPersonaId(e.target.value)}
                className="text-xs px-2 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-white"
                title="Optional persona; if selected and no model is selected, its primary model is used"
              >
                <option value="">Persona: Auto</option>
                {personas.map(p => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>

              <select
                value={selectedAgentId}
                onChange={e => setSelectedAgentId(e.target.value)}
                className="text-xs px-2 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-white"
                title="Optional agent profile"
              >
                <option value="">Agent: Auto</option>
                {agents.map(a => (
                  <option key={a.id} value={a.id}>{a.name} ({a.agent_type})</option>
                ))}
              </select>

              <select
                value={selectedModelId}
                onChange={e => setSelectedModelId(e.target.value)}
                className="text-xs px-2 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-white"
                title="Optional direct model override"
              >
                <option value="">Model: Auto</option>
                {models.map(m => (
                  <option key={m.id} value={m.id}>{m.display_name || m.model_id}</option>
                ))}
              </select>

              <label className="inline-flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-300 px-2 py-1 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
                <input
                  type="checkbox"
                  checked={autoAgentRouting}
                  onChange={e => setAutoAgentRouting(e.target.checked)}
                  className="rounded border-gray-300"
                />
                Auto-route agent by request
              </label>
            </div>
            <p className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
              {selectedAgent
                ? `This will spin up the ${selectedAgent.agent_type} agent using "${selectedAgent.name}".`
                : `This will spin up a ${resolveLaunchAgentType()} agent${autoAgentRouting ? ' based on your request' : ''}.`}
              {selectedModelId ? ' Model override is enabled.' : ''}
            </p>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 px-6 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
        {([['files', '📁 Files'], ['run', '▶ Run'], ['sandbox', '🔒 Sandbox']] as const).map(([tab, label]) => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${activeTab === tab ? 'border-orange-500 text-orange-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {activeTab === 'sandbox' && (
          <div className="flex-1 overflow-y-auto p-4"><SandboxPanel projectId={id} /></div>
        )}
        {activeTab === 'run' && (
          <div className="flex-1 p-4 min-h-0"><RunPanel projectId={id} /></div>
        )}
        {activeTab === 'files' && (
        <>
        {/* File tree */}
        <div className="w-56 flex-shrink-0 border-r border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 flex flex-col">
          <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Files</p>
            <button onClick={fetchProject} className="text-xs text-gray-400 hover:text-gray-600">↻</button>
          </div>
          <div className="flex-1 overflow-y-auto p-1">
            {tree.length === 0 ? (
              <div className="text-center py-8 text-xs text-gray-400">
                {project.path_exists ? 'Empty directory' : 'Path not found'}
              </div>
            ) : (
              <FileTree nodes={tree} onSelect={openFile} selected={selectedFile?.path || null} />
            )}
          </div>
        </div>

        {/* File content */}
        <div className="flex-1 flex flex-col min-w-0 bg-white dark:bg-gray-950">
          {!selectedFile ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center text-gray-400">
                <div className="text-5xl mb-3">📂</div>
                <p className="text-sm font-medium text-gray-600 dark:text-gray-300">{project.name}</p>
                <p className="text-xs mt-1">{project.description || 'Click a file to preview it'}</p>
                <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-left max-w-xs">
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                    <p className="font-medium text-gray-700 dark:text-gray-300">Template</p>
                    <p className="text-gray-500">{project.template}</p>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                    <p className="font-medium text-gray-700 dark:text-gray-300">Created</p>
                    <p className="text-gray-500">{new Date(project.created_at).toLocaleDateString()}</p>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 flex-shrink-0">
                <span className="text-sm">{fileIcon(selectedFile.name)}</span>
                <span className="text-sm font-mono text-gray-700 dark:text-gray-300">{selectedFile.path}</span>
                <span className="ml-auto text-xs text-gray-400">{selectedFile.size} bytes</span>
                <button onClick={() => { setSelectedFile(null); setFileContent(null) }} className="text-gray-400 hover:text-gray-600 ml-1">✕</button>
              </div>
              <div className="flex-1 overflow-auto p-4">
                {loadingFile ? (
                  <div className="flex justify-center py-12">
                    <div className="flex gap-1">{[0,1,2].map(i => <div key={i} className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.1}s` }} />)}</div>
                  </div>
                ) : selectedFile.name.endsWith('.md') && fileContent ? (
                  <div
                    className="prose prose-sm dark:prose-invert max-w-none text-sm text-gray-700 dark:text-gray-200 leading-relaxed"
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(fileContent) }}
                  />
                ) : (
                  <pre className="text-xs font-mono text-gray-700 dark:text-gray-200 whitespace-pre-wrap break-words leading-relaxed">
                    {fileContent}
                  </pre>
                )}
              </div>
            </>
          )}
        </div>
        </>
        )}
      </div>
    </div>
  )
}
