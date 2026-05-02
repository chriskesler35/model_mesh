'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'
import WorkbenchSessionCard from '@/components/WorkbenchSessionCard'
import SessionListToolbar, { SessionFilterKey, SessionSortKey } from '@/components/SessionListToolbar'

import { useState, useEffect, useCallback } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'


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

// ─── Main page ────────────────────────────────────────────────────────────────
export default function AgentSessionsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [sessions, setSessions] = useState<WorkbenchSession[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<SessionFilterKey>('all')
  const [sort, setSort] = useState<SessionSortKey>('newest')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  useEffect(() => {
    const q = searchParams?.get('filter')
    if (!q) return
    const allowed = new Set<SessionFilterKey>(['all', 'active', 'running', 'pending', 'completed', 'failed'])
    if (allowed.has(q as SessionFilterKey)) setFilter(q as SessionFilterKey)
  }, [searchParams])

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

  const filtered = (() => {
    let list =
      filter === 'all'
        ? sessions
        : filter === 'active'
          ? sessions.filter(s => s.status === 'running' || s.status === 'pending')
          : sessions.filter(s => s.status === filter)

    if (sort === 'newest') list = [...list].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    else if (sort === 'oldest') list = [...list].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    else if (sort === 'status') {
      const order: Record<string, number> = { running: 0, pending: 1, failed: 2, completed: 3, cancelled: 4 }
      list = [...list].sort((a, b) => (order[a.status] ?? 5) - (order[b.status] ?? 5))
    }
    return list
  })()

  const counts = {
    all:       sessions.length,
    active:    sessions.filter(s => s.status === 'running' || s.status === 'pending').length,
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
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Sessions</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Live agent work tracking across Projects and Workbench
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

      {/* Filter toolbar */}
      <SessionListToolbar
        filter={filter}
        sort={sort}
        counts={counts}
        onFilterChange={setFilter}
        onSortChange={setSort}
      />

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
            <WorkbenchSessionCard
              key={s.id}
              session={s}
              onOpen={(id) => router.push(`/workbench/${id}`)}
              onCancel={cancelSession}
              onDelete={deleteSession}
            />
          ))}
        </div>
      )}
    </div>
  )
}
