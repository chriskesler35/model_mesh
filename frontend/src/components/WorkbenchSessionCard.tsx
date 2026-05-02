'use client'

export interface SharedWorkbenchSession {
  id: string
  task: string
  agent_type: string
  model?: string | null
  status: string
  files?: string[]
  input_tokens?: number | null
  output_tokens?: number | null
  estimated_cost?: number | null
  created_at?: string | null
  started_at?: string | null
  completed_at?: string | null
}

const STATUS_CONFIG: Record<string, { label: string; color: string; dot: string; animate: boolean }> = {
  pending: { label: 'Pending', color: 'text-yellow-600 bg-yellow-50 border-yellow-200', dot: 'bg-yellow-400', animate: true },
  running: { label: 'Running', color: 'text-blue-600 bg-blue-50 border-blue-200', dot: 'bg-blue-500', animate: true },
  awaiting_approval: { label: 'Needs Approval', color: 'text-amber-700 bg-amber-100 border-amber-200', dot: 'bg-amber-500', animate: true },
  waiting: { label: 'Idle', color: 'text-amber-600 bg-amber-50 border-amber-200', dot: 'bg-amber-400', animate: false },
  completed: { label: 'Done', color: 'text-green-600 bg-green-50 border-green-200', dot: 'bg-green-500', animate: false },
  failed: { label: 'Failed', color: 'text-red-600 bg-red-50 border-red-200', dot: 'bg-red-500', animate: false },
  cancelled: { label: 'Cancelled', color: 'text-gray-500 bg-gray-50 border-gray-200', dot: 'bg-gray-400', animate: false },
}

const AGENT_ICONS: Record<string, string> = {
  coder: '💻',
  researcher: '🔍',
  designer: '🎨',
  reviewer: '🔎',
  planner: '📋',
  executor: '⚡',
  writer: '✍️',
}

function timeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  const diff = Date.now() - new Date(dateStr).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

function duration(start: string | null | undefined, end: string | null | undefined): string {
  if (!start) return '—'
  const ms = new Date(end || new Date().toISOString()).getTime() - new Date(start).getTime()
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  return `${m}m ${s % 60}s`
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

export default function WorkbenchSessionCard({
  session,
  onOpen,
  onCancel,
  onDelete,
}: {
  session: SharedWorkbenchSession
  onOpen: (id: string) => void
  onCancel?: (id: string) => void
  onDelete?: (id: string) => void
}) {
  const icon = AGENT_ICONS[session.agent_type?.toLowerCase()] || '🤖'
  const isActive = session.status === 'running' || session.status === 'pending' || session.status === 'awaiting_approval'
  const files = session.files || []

  const costStr = session.estimated_cost != null
    ? session.estimated_cost < 0.001
      ? '<$0.001'
      : `$${session.estimated_cost.toFixed(4)}`
    : null

  const tokenStr = (session.input_tokens || session.output_tokens)
    ? `${((session.input_tokens || 0) + (session.output_tokens || 0)).toLocaleString()} tokens`
    : null

  return (
    <div
      onClick={() => onOpen(session.id)}
      className={`bg-white dark:bg-gray-800 rounded-xl border cursor-pointer transition-all hover:shadow-md ${
        isActive
          ? 'border-blue-200 dark:border-blue-700 shadow-sm shadow-blue-100 dark:shadow-none'
          : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
      }`}
    >
      <div className="px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
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
                {files.length > 0 && (
                  <span className="text-green-600">📄 {files.length} file{files.length !== 1 ? 's' : ''}</span>
                )}
                {tokenStr && <span>{tokenStr}</span>}
                {costStr && <span className="text-orange-500">{costStr}</span>}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0" onClick={e => e.stopPropagation()}>
            {isActive && onCancel && (
              <button
                onClick={() => onCancel(session.id)}
                className="px-3 py-1.5 text-xs font-medium rounded-lg border border-red-200 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                Cancel
              </button>
            )}
            {!isActive && onDelete && (
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

        {files.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {files.slice(0, 6).map(f => (
              <span key={f} className="text-xs font-mono px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded">
                {f}
              </span>
            ))}
            {files.length > 6 && (
              <span className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-400 rounded">
                +{files.length - 6} more
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
