'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'


// ─── Types ────────────────────────────────────────────────────────────────────
interface WorkbenchSession {
  id: string
  task: string
  agent_type: string
  model: string | null
  project_id: string | null
  project_path: string | null
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  files: string[]
  input_tokens: number | null
  output_tokens: number | null
  estimated_cost: number | null
  created_at: string
  started_at: string | null
  completed_at: string | null
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
  pending:   { label: 'Pending',   color: 'text-yellow-600 bg-yellow-50 border-yellow-200',  dot: 'bg-yellow-400', animate: true  },
  running:   { label: 'Running',   color: 'text-blue-600 bg-blue-50 border-blue-200',        dot: 'bg-blue-500',   animate: true  },
  completed: { label: 'Done',      color: 'text-green-600 bg-green-50 border-green-200',     dot: 'bg-green-500',  animate: false },
  failed:    { label: 'Failed',    color: 'text-red-600 bg-red-50 border-red-200',           dot: 'bg-red-500',    animate: false },
  cancelled: { label: 'Cancelled', color: 'text-gray-500 bg-gray-50 border-gray-200',        dot: 'bg-gray-400',   animate: false },
}

const AGENT_ICONS: Record<string, string> = {
  coder: '💻', researcher: '🔍', designer: '🎨',
  reviewer: '🔎', planner: '📋', executor: '⚡', writer: '✍️',
}

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${cfg.color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot} ${cfg.animate ? 'animate-pulse' : ''}`} />
      {cfg.label}
    </span>
  )
}

function StatCard({ label, value, sub, color = 'text-gray-900' }: {
  label: string; value: string | number; sub?: string; color?: string
}) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 px-5 py-4">
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${color} dark:text-white`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  )
}

// ─── Session card ─────────────────────────────────────────────────────────────
function SessionCard({ session, onCancel, onDelete }: {
  session: WorkbenchSession
  onCancel: (id: string) => void
  onDelete: (id: string) => void
}) {
  const router = useRouter()
  const icon = AGENT_ICONS[session.agent_type?.toLowerCase()] || '🤖'
  const isActive = session.status === 'running' || session.status === 'pending'

  const costStr = session.estimated_cost != null
    ? session.estimated_cost < 0.001
      ? `<$0.001`
      : `$${session.estimated_cost.toFixed(4)}`
    : null

  const tokenStr = (session.input_tokens || session.output_tokens)
    ? `${((session.input_tokens || 0) + (session.output_tokens || 0)).toLocaleString()} tokens`
    : null

  return (
    <div
      onClick={() => router.push(`/workbench/${session.id}`)}
      className={`bg-white dark:bg-gray-800 rounded-xl border cursor-pointer transition-all hover:shadow-md ${
        isActive
          ? 'border-blue-200 dark:border-blue-700 shadow-sm shadow-blue-100 dark:shadow-none'
          : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
      }`}
    >
      <div className="px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            {/* Icon */}
            <div className="relative flex-shrink-0 mt-0.5">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-xl ${
                isActive ? 'bg-blue-50 dark:bg-blue-900/30' : 'bg-gray-50 dark:bg-gray-700'
              }`}>
                {icon}
              </div>
              {isActive && (
                <span className="absolute -top-0.5 -right-0.5 flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500" />
                </span>
              )}
            </div>

            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-semibold text-gray-900 dark:text-white capitalize">
                  {session.agent_type}
                </span>
                <StatusBadge status={session.status} />
                {session.model && (
                  <span className="text-xs text-gray-400 font-mono truncate max-w-[160px]">
                    {session.model.split('/').pop()}
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-300 mt-0.5 line-clamp-2">{session.task}</p>
              <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-400 flex-wrap">
                <span>{timeAgo(session.created_at)}</span>
                {session.started_at && (
                  <span>Duration: {duration(session.started_at, session.completed_at)}</span>
                )}
                {session.files.length > 0 && (
                  <span className="text-green-600">📄 {session.files.length} file{session.files.length !== 1 ? 's' : ''}</span>
                )}
                {tokenStr && <span>{tokenStr}</span>}
                {costStr && <span className="text-orange-500">{costStr}</span>}
              </div>
            </div>
          </div>

          {/* Actions — stop propagation so clicks don't navigate */}
          <div className="flex items-center gap-2 flex-shrink-0" onClick={e => e.stopPropagation()}>
            {isActive && (
              <button
                onClick={() => onCancel(session.id)}
                className="px-3 py-1.5 text-xs font-medium rounded-lg border border-red-200 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                Cancel
              </button>
            )}
            {!isActive && (
              <button
                onClick={() => onDelete(session.id)}
                className="p-1.5 rounded-lg text-gray-300 hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                title="Delete session"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            )}
            <svg className="w-4 h-4 text-gray-300 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </div>
        </div>

        {/* File list for completed sessions */}
        {session.files.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {session.files.slice(0, 6).map(f => (
              <span key={f} className="text-xs font-mono px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded">
                {f}
              </span>
            ))}
            {session.files.length > 6 && (
              <span className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-400 rounded">
                +{session.files.length - 6} more
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function AgentSessionsPage() {
  const router = useRouter()
  const [sessions, setSessions] = useState<WorkbenchSession[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string>('all')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/workbench/sessions`, { headers: AUTH_HEADERS })
      const data = await res.json()
      setSessions(data.data || [])
      setLastRefresh(new Date())
    } catch (e) {
      console.error('Failed to fetch workbench sessions:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchSessions() }, [fetchSessions])

  // Auto-refresh: fast when active sessions, slow otherwise
  useEffect(() => {
    if (!autoRefresh) return
    const hasActive = sessions.some(s => s.status === 'running' || s.status === 'pending')
    const timer = setInterval(fetchSessions, hasActive ? 3000 : 15000)
    return () => clearInterval(timer)
  }, [autoRefresh, sessions, fetchSessions])

  const cancelSession = async (id: string) => {
    await fetch(`${API_BASE}/v1/workbench/sessions/${id}/cancel`, { method: 'POST', headers: AUTH_HEADERS })
    setSessions(prev => prev.map(s => s.id === id ? { ...s, status: 'cancelled' } : s))
  }

  const deleteSession = async (id: string) => {
    if (!confirm('Delete this session?')) return
    await fetch(`${API_BASE}/v1/workbench/sessions/${id}`, { method: 'DELETE', headers: AUTH_HEADERS })
    setSessions(prev => prev.filter(s => s.id !== id))
  }

  const filtered = filter === 'all' ? sessions : sessions.filter(s => s.status === filter)

  const counts = {
    all:       sessions.length,
    running:   sessions.filter(s => s.status === 'running').length,
    pending:   sessions.filter(s => s.status === 'pending').length,
    completed: sessions.filter(s => s.status === 'completed').length,
    failed:    sessions.filter(s => s.status === 'failed').length,
  }

  const activeCount = counts.running + counts.pending
  const totalTokens = sessions.reduce((a, s) => a + (s.input_tokens || 0) + (s.output_tokens || 0), 0)
  const totalCost   = sessions.reduce((a, s) => a + (s.estimated_cost || 0), 0)
  const totalFiles  = sessions.reduce((a, s) => a + s.files.length, 0)

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
            Workbench agent runs — click any session to view the event log
            {lastRefresh && <span className="ml-2 text-gray-400">· Updated {timeAgo(lastRefresh.toISOString())}</span>}
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
            onClick={fetchSessions}
            className="px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            Refresh
          </button>
          <button
            onClick={() => router.push('/workbench')}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-orange-500 hover:bg-orange-600 text-white text-xs font-medium rounded-lg transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Session
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Active"
          value={activeCount}
          sub={activeCount > 0 ? 'agents working' : 'all idle'}
          color={activeCount > 0 ? 'text-blue-600' : 'text-gray-900'}
        />
        <StatCard label="Total Sessions" value={counts.all} sub={`${counts.completed} completed`} />
        <StatCard label="Files Written"  value={totalFiles} sub="across all sessions" />
        <StatCard
          label="Total Cost"
          value={totalCost < 0.001 ? '<$0.001' : `$${totalCost.toFixed(4)}`}
          sub={totalTokens > 0 ? `${(totalTokens / 1000).toFixed(1)}k tokens` : 'no usage yet'}
          color="text-orange-600"
        />
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-1 border-b border-gray-200 dark:border-gray-700">
        {(['all', 'running', 'pending', 'completed', 'failed'] as const).map(key => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 transition-colors capitalize ${
              filter === key
                ? 'border-orange-500 text-orange-600 dark:text-orange-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            {key}
            {counts[key] > 0 && (
              <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                filter === key ? 'bg-orange-100 text-orange-600 dark:bg-orange-900/30' : 'bg-gray-100 dark:bg-gray-700 text-gray-500'
              }`}>
                {counts[key]}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Session list */}
      {filtered.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-4xl mb-3">🤖</div>
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">
            {filter === 'all' ? 'No sessions yet' : `No ${filter} sessions`}
          </h3>
          <p className="text-sm text-gray-500 mt-1">
            {filter === 'all' ? 'Launch a Workbench session to get started.' : 'Switch to "all" to see other sessions.'}
          </p>
          {filter === 'all' && (
            <button
              onClick={() => router.push('/workbench')}
              className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Open Workbench
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(s => (
            <SessionCard
              key={s.id}
              session={s}
              onCancel={cancelSession}
              onDelete={deleteSession}
            />
          ))}
        </div>
      )}
    </div>
  )
}
