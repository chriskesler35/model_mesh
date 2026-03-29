'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'

const API_BASE = 'http://localhost:19000'
const API_KEY = 'modelmesh_local_dev_key'
const AUTH = { 'Authorization': `Bearer ${API_KEY}`, 'Content-Type': 'application/json' }

// ─── Types ────────────────────────────────────────────────────────────────────
interface AgentSession {
  session_id: string
  agent_type: string
  task: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  created_at: string
  started_at: string | null
  completed_at: string | null
  result: string | null
  error: string | null
  progress: Record<string, any> | null
}

interface Agent {
  id: string
  name: string
  agent_type: string
  description: string
  is_active: boolean
}

interface SystemHealth {
  status: string
  version: string
  uptime_seconds: number
  models_count: number
  personas_count: number
  agents_count: number
  sessions_active: number
  system: {
    cpu_percent: number
    memory_percent: number
    disk_percent: number
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '—'
  const diff = Date.now() - new Date(dateStr).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return `${h}h ago`
}

function duration(start: string | null, end: string | null): string {
  if (!start) return '—'
  const ms = new Date(end || new Date().toISOString()).getTime() - new Date(start).getTime()
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return `${m}m ${s % 60}s`
}

const STATUS_CONFIG: Record<string, { label: string; color: string; dot: string; animate: boolean }> = {
  pending:   { label: 'Pending',   color: 'text-yellow-600 bg-yellow-50 border-yellow-200',  dot: 'bg-yellow-400', animate: true },
  running:   { label: 'Running',   color: 'text-blue-600 bg-blue-50 border-blue-200',        dot: 'bg-blue-500',   animate: true },
  completed: { label: 'Done',      color: 'text-green-600 bg-green-50 border-green-200',     dot: 'bg-green-500',  animate: false },
  failed:    { label: 'Failed',    color: 'text-red-600 bg-red-50 border-red-200',           dot: 'bg-red-500',    animate: false },
  cancelled: { label: 'Cancelled', color: 'text-gray-500 bg-gray-50 border-gray-200',        dot: 'bg-gray-400',   animate: false },
}

const AGENT_TYPE_ICONS: Record<string, string> = {
  coder:      '💻',
  researcher: '🔍',
  designer:   '🎨',
  reviewer:   '🔎',
  planner:    '📋',
  executor:   '⚡',
  writer:     '✍️',
}

// ─── Status badge ─────────────────────────────────────────────────────────────
function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${cfg.color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot} ${cfg.animate ? 'animate-pulse' : ''}`} />
      {cfg.label}
    </span>
  )
}

// ─── Stat card ────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, color = 'text-gray-900' }: { label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 px-5 py-4">
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${color} dark:text-white`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  )
}

// ─── Session card ─────────────────────────────────────────────────────────────
function SessionCard({ session, onCancel, onRetry }: {
  session: AgentSession
  onCancel: (id: string) => void
  onRetry: (session: AgentSession) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const icon = AGENT_TYPE_ICONS[session.agent_type?.toLowerCase()] || '🤖'
  const isActive = session.status === 'running' || session.status === 'pending'

  return (
    <div className={`bg-white dark:bg-gray-800 rounded-xl border ${isActive ? 'border-blue-200 dark:border-blue-700 shadow-sm shadow-blue-100 dark:shadow-none' : 'border-gray-200 dark:border-gray-700'} overflow-hidden transition-all`}>
      <div className="px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            {/* Icon + pulse ring for active */}
            <div className="relative flex-shrink-0 mt-0.5">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-xl ${isActive ? 'bg-blue-50 dark:bg-blue-900/30' : 'bg-gray-50 dark:bg-gray-700'}`}>
                {icon}
              </div>
              {isActive && (
                <span className="absolute -top-0.5 -right-0.5 flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500" />
                </span>
              )}
            </div>

            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-semibold text-gray-900 dark:text-white capitalize">{session.agent_type}</span>
                <StatusBadge status={session.status} />
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-300 mt-0.5 line-clamp-2">{session.task}</p>
              <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-400">
                <span>Started {timeAgo(session.created_at)}</span>
                {(session.status === 'running' || session.status === 'completed') && (
                  <span>Duration: {duration(session.started_at, session.completed_at)}</span>
                )}
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 flex-shrink-0">
            {isActive && (
              <button
                onClick={() => onCancel(session.session_id)}
                className="px-3 py-1.5 text-xs font-medium rounded-lg border border-red-200 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                Cancel
              </button>
            )}
            {session.status === 'failed' && (
              <button
                onClick={() => onRetry(session)}
                className="px-3 py-1.5 text-xs font-medium rounded-lg border border-orange-200 text-orange-600 hover:bg-orange-50 transition-colors"
              >
                Retry
              </button>
            )}
            <button
              onClick={() => setExpanded(e => !e)}
              className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 transition-colors"
            >
              <svg className={`w-4 h-4 transition-transform ${expanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
          </div>
        </div>

        {/* Progress bar for running sessions */}
        {session.status === 'running' && (
          <div className="mt-3">
            <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
              <div className="bg-blue-500 h-full rounded-full animate-pulse" style={{ width: `${session.progress?.percent ?? 50}%` }} />
            </div>
          </div>
        )}
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-gray-100 dark:border-gray-700 px-5 py-4 bg-gray-50 dark:bg-gray-900/50 space-y-3">
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">Session ID</p>
            <code className="text-xs font-mono text-gray-600 dark:text-gray-400">{session.session_id}</code>
          </div>

          {session.progress && Object.keys(session.progress).length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">Progress</p>
              <pre className="text-xs text-gray-600 dark:text-gray-400 bg-white dark:bg-gray-800 rounded-lg p-2 overflow-x-auto">
                {JSON.stringify(session.progress, null, 2)}
              </pre>
            </div>
          )}

          {session.result && (
            <div>
              <p className="text-xs font-medium text-green-600 uppercase tracking-wider mb-1">Result</p>
              <div className="text-sm text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 rounded-lg p-3 whitespace-pre-wrap max-h-48 overflow-y-auto">
                {session.result}
              </div>
            </div>
          )}

          {session.error && (
            <div>
              <p className="text-xs font-medium text-red-600 uppercase tracking-wider mb-1">Error</p>
              <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-lg p-3 font-mono">
                {session.error}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── New session modal ────────────────────────────────────────────────────────
function NewSessionModal({ agents, onClose, onCreate }: {
  agents: Agent[]
  onClose: () => void
  onCreate: (session: AgentSession) => void
}) {
  const [agentType, setAgentType] = useState(agents[0]?.agent_type || 'coder')
  const [task, setTask] = useState('')
  const [model, setModel] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    if (!task.trim()) return
    setSubmitting(true)
    setError('')
    try {
      const res = await fetch(`${API_BASE}/v1/remote/sessions`, {
        method: 'POST',
        headers: AUTH,
        body: JSON.stringify({ agent_type: agentType, task: task.trim(), model: model || undefined }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      onCreate(data)
      onClose()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">New Agent Session</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Agent Type</label>
            <select
              value={agentType}
              onChange={e => setAgentType(e.target.value)}
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
            >
              {agents.map(a => (
                <option key={a.id} value={a.agent_type}>
                  {AGENT_TYPE_ICONS[a.agent_type] || '🤖'} {a.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Task</label>
            <textarea
              value={task}
              onChange={e => setTask(e.target.value)}
              rows={4}
              placeholder="Describe what you want this agent to do..."
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Model <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <input
              value={model}
              onChange={e => setModel(e.target.value)}
              placeholder="e.g. ollama/glm4:latest"
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
            />
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
        </div>
        <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-800 flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={!task.trim() || submitting}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-orange-500 hover:bg-orange-600 disabled:bg-gray-200 dark:disabled:bg-gray-700 text-white disabled:text-gray-400 transition-colors"
          >
            {submitting ? 'Launching...' : 'Launch Agent'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function AgentSessionsPage() {
  const [sessions, setSessions] = useState<AgentSession[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')
  const [showNewModal, setShowNewModal] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const fetchAll = useCallback(async () => {
    try {
      const [sessionsRes, agentsRes, healthRes] = await Promise.all([
        fetch(`${API_BASE}/v1/remote/sessions?limit=50`, { headers: AUTH }).then(r => r.json()).catch(() => []),
        fetch(`${API_BASE}/v1/agents`, { headers: AUTH }).then(r => r.json()).catch(() => ({ data: [] })),
        fetch(`${API_BASE}/v1/remote/health`, { headers: AUTH }).then(r => r.json()).catch(() => null),
      ])
      setSessions(Array.isArray(sessionsRes) ? sessionsRes : [])
      setAgents(agentsRes.data || [])
      setHealth(healthRes)
      setLastRefresh(new Date())
    } catch (e) {
      console.error('Failed to fetch:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => { fetchAll() }, [fetchAll])

  // Auto-refresh every 5s when active sessions exist
  useEffect(() => {
    if (!autoRefresh) return
    const hasActive = sessions.some(s => s.status === 'running' || s.status === 'pending')
    const interval = hasActive ? 3000 : 10000
    const timer = setInterval(fetchAll, interval)
    return () => clearInterval(timer)
  }, [autoRefresh, sessions, fetchAll])

  const cancelSession = async (id: string) => {
    await fetch(`${API_BASE}/v1/remote/sessions/${id}/cancel`, { method: 'POST', headers: AUTH })
    setSessions(prev => prev.map(s => s.session_id === id ? { ...s, status: 'cancelled' } : s))
  }

  const retrySession = async (session: AgentSession) => {
    try {
      const res = await fetch(`${API_BASE}/v1/remote/sessions`, {
        method: 'POST',
        headers: AUTH,
        body: JSON.stringify({ agent_type: session.agent_type, task: session.task }),
      })
      const newSession = await res.json()
      setSessions(prev => [newSession, ...prev])
    } catch (e) {
      console.error('Retry failed:', e)
    }
  }

  const filteredSessions = filter === 'all'
    ? sessions
    : sessions.filter(s => s.status === filter)

  const counts = {
    all: sessions.length,
    running: sessions.filter(s => s.status === 'running').length,
    pending: sessions.filter(s => s.status === 'pending').length,
    completed: sessions.filter(s => s.status === 'completed').length,
    failed: sessions.filter(s => s.status === 'failed').length,
  }

  const activeCount = counts.running + counts.pending

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="flex gap-1.5">
          {[0, 1, 2].map(i => (
            <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Agent Sessions</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Monitor and manage active agent tasks
            {lastRefresh && (
              <span className="ml-2 text-gray-400">· Updated {timeAgo(lastRefresh.toISOString())}</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={() => setAutoRefresh(a => !a)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              autoRefresh
                ? 'bg-green-50 border-green-200 text-green-700 dark:bg-green-900/20 dark:border-green-700 dark:text-green-400'
                : 'border-gray-200 dark:border-gray-600 text-gray-500 hover:bg-gray-50'
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${autoRefresh ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
            {autoRefresh ? 'Live' : 'Paused'}
          </button>
          <button
            onClick={fetchAll}
            className="px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            Refresh
          </button>
          <button
            onClick={() => setShowNewModal(true)}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-orange-500 hover:bg-orange-600 text-white text-xs font-medium rounded-lg transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Session
          </button>
        </div>
      </div>

      {/* System health stats */}
      {health && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard
            label="Active Sessions"
            value={activeCount}
            sub={activeCount > 0 ? 'agents working' : 'all idle'}
            color={activeCount > 0 ? 'text-blue-600' : 'text-gray-900'}
          />
          <StatCard
            label="CPU"
            value={`${Math.round(health.system.cpu_percent)}%`}
            sub="system load"
            color={health.system.cpu_percent > 80 ? 'text-red-600' : health.system.cpu_percent > 50 ? 'text-yellow-600' : 'text-green-600'}
          />
          <StatCard
            label="Memory"
            value={`${Math.round(health.system.memory_percent)}%`}
            sub="RAM used"
            color={health.system.memory_percent > 85 ? 'text-red-600' : 'text-gray-900'}
          />
          <StatCard
            label="Uptime"
            value={health.uptime_seconds < 3600
              ? `${Math.floor(health.uptime_seconds / 60)}m`
              : `${Math.floor(health.uptime_seconds / 3600)}h`}
            sub={`v${health.version}`}
          />
        </div>
      )}

      {/* Agent roster */}
      {agents.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Available Agents</h2>
          <div className="flex flex-wrap gap-2">
            {agents.map(a => (
              <div
                key={a.id}
                className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-full text-sm"
              >
                <span>{AGENT_TYPE_ICONS[a.agent_type] || '🤖'}</span>
                <span className="text-gray-700 dark:text-gray-300">{a.name}</span>
                <span className={`w-1.5 h-1.5 rounded-full ${a.is_active ? 'bg-green-400' : 'bg-gray-300'}`} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex items-center gap-1 border-b border-gray-200 dark:border-gray-700">
        {[
          { key: 'all', label: 'All' },
          { key: 'running', label: 'Running' },
          { key: 'pending', label: 'Pending' },
          { key: 'completed', label: 'Completed' },
          { key: 'failed', label: 'Failed' },
        ].map(tab => (
          <button
            key={tab.key}
            onClick={() => setFilter(tab.key)}
            className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
              filter === tab.key
                ? 'border-orange-500 text-orange-600 dark:text-orange-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            {tab.label}
            {counts[tab.key as keyof typeof counts] > 0 && (
              <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                filter === tab.key ? 'bg-orange-100 text-orange-600 dark:bg-orange-900/30' : 'bg-gray-100 dark:bg-gray-700 text-gray-500'
              }`}>
                {counts[tab.key as keyof typeof counts]}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Session list */}
      {filteredSessions.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-4xl mb-3">🤖</div>
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">
            {filter === 'all' ? 'No sessions yet' : `No ${filter} sessions`}
          </h3>
          <p className="text-sm text-gray-500 mt-1">
            {filter === 'all' ? 'Launch an agent to get started.' : `Switch to "All" to see other sessions.`}
          </p>
          {filter === 'all' && (
            <button
              onClick={() => setShowNewModal(true)}
              className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Launch First Agent
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filteredSessions.map(session => (
            <SessionCard
              key={session.session_id}
              session={session}
              onCancel={cancelSession}
              onRetry={retrySession}
            />
          ))}
        </div>
      )}

      {/* New session modal */}
      {showNewModal && (
        <NewSessionModal
          agents={agents}
          onClose={() => setShowNewModal(false)}
          onCreate={s => setSessions(prev => [s, ...prev])}
        />
      )}
    </div>
  )
}
