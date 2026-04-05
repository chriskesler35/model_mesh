'use client'

// Dynamic rendering for workbench
export const dynamic = 'force-dynamic'
export const revalidate = 0

import { API_BASE, AUTH_HEADERS } from '@/lib/config'
import { renderMarkdown } from '@/lib/markdown'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'


// ─── Types ────────────────────────────────────────────────────────────────────
interface WBEvent {
  type: string
  payload: Record<string, any>
  ts: string
}

interface FileEntry { path: string; status: 'created' | 'modified'; content?: string; diff?: string }

const EVENT_STYLE: Record<string, { icon: string; color: string; label: string }> = {
  agent_thought: { icon: '💭', color: 'text-purple-600 dark:text-purple-400',  label: 'Thinking'     },
  tool_call:     { icon: '🔧', color: 'text-blue-600 dark:text-blue-400',      label: 'Tool'         },
  file_created:  { icon: '📄', color: 'text-green-600 dark:text-green-400',    label: 'Created'      },
  file_modified: { icon: '✏️',  color: 'text-yellow-600 dark:text-yellow-400',  label: 'Modified'     },
  error:         { icon: '❌', color: 'text-red-600 dark:text-red-400',        label: 'Error'        },
  waiting:       { icon: '⏳', color: 'text-orange-500 dark:text-orange-400',  label: 'Waiting'      },
  user_message:  { icon: '💬', color: 'text-indigo-600 dark:text-indigo-400',  label: 'You'          },
  agent_reply:   { icon: '🤖', color: 'text-emerald-600 dark:text-emerald-400', label: 'Agent'       },
  info:          { icon: 'ℹ️',  color: 'text-gray-500 dark:text-gray-400',      label: 'Info'         },
  done:          { icon: '✅', color: 'text-green-600 dark:text-green-400',    label: 'Done'         },
  ping:          { icon: '·',  color: 'text-gray-300',                          label: ''             },
}

// ─── Event row ────────────────────────────────────────────────────────────────
function EventRow({ evt, index }: { evt: WBEvent; index: number }) {
  const [expanded, setExpanded] = useState(false)
  const cfg = EVENT_STYLE[evt.type] || EVENT_STYLE.info
  if (evt.type === 'ping' || evt.type === 'init') return null

  const hasDetail = evt.payload.content || evt.payload.diff || evt.payload.result || evt.payload.args

  const summary = (() => {
    const p = evt.payload
    switch (evt.type) {
      case 'agent_thought': return p.thought
      case 'tool_call':     return `${p.tool}(${JSON.stringify(p.args || {}).slice(0, 60)}) → ${p.result || '...'}`
      case 'file_created':  return p.path
      case 'file_modified': return p.path
      case 'error':         return p.message || p.error
      case 'waiting':       return p.message || 'Waiting for human input...'
      case 'user_message':  return p.message
      case 'agent_reply':    return p.message
      case 'info':          return p.message
      case 'done':          return p.message
      default: return JSON.stringify(p).slice(0, 100)
    }
  })()

  return (
    <div className={`flex gap-3 py-2 px-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800/50 group transition-colors ${evt.type === 'error' ? 'bg-red-50 dark:bg-red-900/10' : ''} ${evt.type === 'waiting' ? 'bg-orange-50 dark:bg-orange-900/10 border border-orange-200 dark:border-orange-800' : ''}`}>
      <div className="flex-shrink-0 w-6 text-center mt-0.5 text-base">{cfg.icon}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          {cfg.label && <span className={`text-xs font-semibold uppercase tracking-wider ${cfg.color}`}>{cfg.label}</span>}
          <span className="text-sm text-gray-700 dark:text-gray-200 truncate flex-1">{summary}</span>
          <span className="text-xs text-gray-400 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
            {new Date(evt.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
        </div>

        {hasDetail && (
          <button onClick={() => setExpanded(e => !e)}
            className="text-xs text-gray-400 hover:text-gray-600 mt-0.5">
            {expanded ? '▲ hide' : '▼ show details'}
          </button>
        )}

        {expanded && hasDetail && (
          <pre className="mt-2 text-xs bg-gray-900 text-green-400 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto">
            {evt.payload.diff || evt.payload.content || JSON.stringify(evt.payload, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}

// ─── Agent Card ───────────────────────────────────────────────────────────────
const AGENT_AVATARS: Record<string, { icon: string; color: string }> = {
  coder:     { icon: '💻', color: 'from-blue-400 to-indigo-500' },
  researcher:{ icon: '🔍', color: 'from-purple-400 to-pink-500' },
  designer:  { icon: '🎨', color: 'from-pink-400 to-rose-500' },
  reviewer:  { icon: '👀', color: 'from-amber-400 to-orange-500' },
  planner:   { icon: '📋', color: 'from-emerald-400 to-teal-500' },
  executor:  { icon: '⚙️',  color: 'from-gray-400 to-slate-500' },
  writer:    { icon: '✍️',  color: 'from-violet-400 to-purple-500' },
}

function AgentCard({
  agentType, model, status, currentActivity, currentRole, turnCount, fileCount,
}: {
  agentType: string
  model: string
  status: string
  currentActivity: string | null
  currentRole: string | null
  turnCount: number
  fileCount: number
}) {
  const meta = AGENT_AVATARS[agentType] || AGENT_AVATARS.coder
  const statusLabel = status === 'running' ? 'Working…' : status === 'waiting' ? 'Idle — send another message or close' : status === 'completed' ? 'Done' : status === 'failed' ? 'Failed' : status === 'cancelled' ? 'Cancelled' : 'Connecting'
  const isWorking = status === 'running' || status === 'pending'

  return (
    <div className="flex items-center gap-3 px-4 py-3 bg-gradient-to-r from-white to-gray-50 dark:from-gray-900 dark:to-gray-800 border-b border-gray-200 dark:border-gray-700">
      {/* Avatar */}
      <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${meta.color} flex items-center justify-center text-2xl shadow-md flex-shrink-0 relative`}>
        {meta.icon}
        {isWorking && (
          <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-green-400 border-2 border-white dark:border-gray-900 animate-pulse" />
        )}
        {status === 'waiting' && (
          <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-orange-400 border-2 border-white dark:border-gray-900" />
        )}
      </div>

      {/* Details */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-semibold text-gray-900 dark:text-white capitalize">{agentType} Agent</span>
          {currentRole && (
            <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-700">
              🎭 {currentRole}
            </span>
          )}
          <span className="text-xs text-gray-400">·</span>
          <span className="text-xs text-gray-500 font-mono truncate">{model}</span>
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className={`text-xs font-medium ${
            isWorking ? 'text-green-600 dark:text-green-400' :
            status === 'waiting' ? 'text-orange-600 dark:text-orange-400' :
            status === 'failed' || status === 'error' ? 'text-red-600 dark:text-red-400' :
            'text-gray-500'
          }`}>
            {statusLabel}
          </span>
          {currentActivity && isWorking && (
            <>
              <span className="text-xs text-gray-400">·</span>
              <span className="text-xs text-gray-600 dark:text-gray-300 truncate italic">{currentActivity}</span>
            </>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="flex items-center gap-3 flex-shrink-0">
        <div className="text-center">
          <div className="text-sm font-semibold text-gray-900 dark:text-white">{turnCount}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wider">Turns</div>
        </div>
        <div className="w-px h-8 bg-gray-200 dark:bg-gray-700" />
        <div className="text-center">
          <div className="text-sm font-semibold text-gray-900 dark:text-white">{fileCount}</div>
          <div className="text-[10px] text-gray-400 uppercase tracking-wider">Files</div>
        </div>
      </div>
    </div>
  )
}


// ─── Conversation turn (groups events into a message bubble pair) ──────────────
interface Turn {
  userMessage: string
  userTime: string
  role: string | null           // role declared by agent for this turn
  agentActivities: string[]  // plain-text descriptions of what the agent did
  agentReply: string | null
  filesTouched: string[]
  turnStatus: 'running' | 'done' | 'error'
  error: string | null
}

function buildTurns(events: WBEvent[], initialTask: string | null): Turn[] {
  const turns: Turn[] = []
  let current: Turn | null = null

  // Seed with the initial task as turn 1
  if (initialTask) {
    current = {
      userMessage: initialTask,
      userTime: '',
      role: null,
      agentActivities: [],
      agentReply: null,
      filesTouched: [],
      turnStatus: 'running',
      error: null,
    }
  }

  for (const evt of events) {
    const p = evt.payload || {}
    if (evt.type === 'user_message') {
      // Close out current turn (if any) and start a new one
      if (current) turns.push(current)
      current = {
        userMessage: p.message || '',
        userTime: evt.ts,
        role: null,
        agentActivities: [],
        agentReply: null,
        filesTouched: [],
        turnStatus: 'running',
        error: null,
      }
    } else if (evt.type === 'role_change') {
      if (current) current.role = p.role || null
    } else if (evt.type === 'agent_thought') {
      if (current) current.agentActivities.push(p.thought || '')
    } else if (evt.type === 'info') {
      if (current) current.agentActivities.push(p.message || '')
    } else if (evt.type === 'file_created') {
      if (current) current.filesTouched.push(p.path || '')
    } else if (evt.type === 'file_modified') {
      if (current) current.filesTouched.push(p.path || '')
    } else if (evt.type === 'agent_reply') {
      if (current) current.agentReply = p.message || ''
    } else if (evt.type === 'done') {
      if (current) {
        current.turnStatus = p.status === 'waiting' || p.status === 'completed' ? 'done' : 'error'
        if (!current.agentReply) current.agentReply = p.message || ''
      }
    } else if (evt.type === 'error') {
      if (current) {
        current.turnStatus = 'error'
        current.error = p.message || p.error || 'Error'
      }
    }
  }
  if (current) turns.push(current)
  return turns
}


function TurnBubble({ turn, isLast, isActive }: { turn: Turn; isLast: boolean; isActive: boolean }) {
  const working = isLast && isActive && turn.turnStatus === 'running'

  return (
    <div className="space-y-3">
      {/* User message (right-aligned) */}
      {turn.userMessage && (
        <div className="flex justify-end">
          <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-orange-500 text-white px-4 py-2.5 text-sm whitespace-pre-wrap break-words shadow-sm">
            {turn.userMessage}
          </div>
        </div>
      )}

      {/* Agent response (left-aligned) */}
      <div className="flex justify-start">
        <div className="max-w-[85%] rounded-2xl rounded-tl-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
          {/* Role badge — shows which role the agent took for this turn */}
          {turn.role && (
            <div className="px-4 pt-3 flex items-center gap-2">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-gradient-to-r from-indigo-100 to-purple-100 dark:from-indigo-900/30 dark:to-purple-900/30 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-700">
                🎭 {turn.role}
              </span>
            </div>
          )}
          {/* Activity list — collapsed once turn is done */}
          {turn.agentActivities.length > 0 && (
            <div className={`px-4 py-3 space-y-1.5 border-b border-gray-100 dark:border-gray-700 ${working ? '' : 'bg-gray-50 dark:bg-gray-900/50'}`}>
              {turn.agentActivities.slice(-4).map((a, i) => (
                <div key={i} className="flex items-start gap-2 text-xs text-gray-600 dark:text-gray-400">
                  <span className="text-gray-400 mt-0.5">{working && i === turn.agentActivities.slice(-4).length - 1 ? '⏳' : '✓'}</span>
                  <span className="flex-1">{a}</span>
                </div>
              ))}
              {turn.agentActivities.length > 4 && (
                <div className="text-[10px] text-gray-400 italic">({turn.agentActivities.length - 4} earlier steps)</div>
              )}
            </div>
          )}

          {/* Agent final reply (rendered as markdown) */}
          {turn.agentReply ? (
            <div
              className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 break-words leading-relaxed prose-sm"
              dangerouslySetInnerHTML={{ __html: `<p class="mb-2">${renderMarkdown(turn.agentReply)}</p>` }}
            />
          ) : working ? (
            <div className="px-4 py-3 flex items-center gap-2 text-sm text-gray-500">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-xs italic">Working on it…</span>
            </div>
          ) : null}

          {/* Files touched this turn */}
          {turn.filesTouched.length > 0 && (
            <div className="px-4 py-2.5 bg-gray-50 dark:bg-gray-900/50 border-t border-gray-100 dark:border-gray-700">
              <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">
                {turn.filesTouched.length} file{turn.filesTouched.length === 1 ? '' : 's'} touched
              </div>
              <div className="flex flex-wrap gap-1.5">
                {turn.filesTouched.map((f, i) => (
                  <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 text-[11px] font-mono text-gray-700 dark:text-gray-300">
                    📄 {f}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Error */}
          {turn.error && (
            <div className="px-4 py-2.5 bg-red-50 dark:bg-red-900/20 border-t border-red-200 dark:border-red-800 text-xs text-red-700 dark:text-red-300">
              ❌ {turn.error}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}


// ─── File tree ────────────────────────────────────────────────────────────────
function FileTree({ files, onSelect, selected }: { files: FileEntry[]; onSelect: (f: FileEntry) => void; selected: string | null }) {
  if (files.length === 0) return (
    <div className="text-center py-8 text-xs text-gray-400">No files yet</div>
  )
  return (
    <div className="space-y-0.5">
      {files.map(f => (
        <button key={f.path} onClick={() => onSelect(f)}
          className={`w-full flex items-center gap-2 px-3 py-2 text-left rounded-lg text-sm transition-colors ${
            selected === f.path
              ? 'bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300'
              : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
          }`}>
          <span className={f.status === 'created' ? 'text-green-500' : 'text-yellow-500'}>
            {f.status === 'created' ? '+ ' : '~ '}
          </span>
          <span className="font-mono truncate">{f.path}</span>
          <span className={`ml-auto text-xs px-1.5 py-0.5 rounded ${
            f.status === 'created' ? 'bg-green-100 text-green-600' : 'bg-yellow-100 text-yellow-600'
          }`}>{f.status}</span>
        </button>
      ))}
    </div>
  )
}

// ─── Main workbench page ──────────────────────────────────────────────────────
export default function WorkbenchSessionPage() {
  const { id } = useParams() as { id: string }
  const router = useRouter()

  const [session, setSession] = useState<any>(null)
  const [events, setEvents] = useState<WBEvent[]>([])
  const [files, setFiles] = useState<FileEntry[]>([])
  const [selectedFile, setSelectedFile] = useState<FileEntry | null>(null)
  const [status, setStatus] = useState<string>('connecting')
  const [intervention, setIntervention] = useState('')
  const [sending, setSending] = useState(false)
  const [waitingForHuman, setWaitingForHuman] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)

  const streamRef = useRef<EventSource | null>(null)
  const streamEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Auto-scroll stream
  useEffect(() => {
    if (autoScroll) streamEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events, autoScroll])

  // SSE stream
  useEffect(() => {
    const es = new EventSource(`${API_BASE}/v1/workbench/sessions/${id}/stream`)
    streamRef.current = es

    es.onmessage = (e) => {
      try {
        const evt: WBEvent = JSON.parse(e.data)

        if (evt.type === 'init') {
          setSession(evt.payload)
          setStatus(evt.payload.status || 'running')
          return
        }

        if (evt.type === 'ping') return

        setEvents(prev => [...prev, evt])

        if (evt.type === 'file_created') {
          setFiles(prev => {
            const existingIdx = prev.findIndex(f => f.path === evt.payload.path)
            const entry = { path: evt.payload.path, status: 'created' as const, content: evt.payload.content }
            if (existingIdx >= 0) {
              // File touched again on a later turn — update its preview
              const next = [...prev]
              next[existingIdx] = entry
              return next
            }
            return [...prev, entry]
          })
          // If the user is currently viewing this file, refresh its preview
          setSelectedFile(current => {
            if (current && current.path === evt.payload.path) {
              return { ...current, content: evt.payload.content }
            }
            return current
          })
        }
        if (evt.type === 'file_modified') {
          setFiles(prev => prev.map(f =>
            f.path === evt.payload.path ? { ...f, status: 'modified' as const, diff: evt.payload.diff } : f
          ).concat(prev.find(f => f.path === evt.payload.path) ? [] : [{ path: evt.payload.path, status: 'modified' as const, diff: evt.payload.diff }])
          )
        }
        if (evt.type === 'waiting') {
          setWaitingForHuman(true)
          setStatus('waiting')
          inputRef.current?.focus()
        }
        if (evt.type === 'done') {
          const newStatus = evt.payload.status || 'completed'
          setStatus(newStatus)
          // 'waiting' means turn finished but session stays open for follow-ups.
          // Keep the SSE stream alive so the next turn's events flow in.
          if (newStatus === 'waiting') {
            setWaitingForHuman(true)
            inputRef.current?.focus()
          } else {
            setWaitingForHuman(false)
            es.close()
          }
        }
        if (evt.type === 'error') {
          setStatus('error')
        }
      } catch { /* ignore malformed */ }
    }

    es.onerror = () => {
      setStatus(prev => prev === 'running' || prev === 'connecting' ? 'disconnected' : prev)
    }

    return () => es.close()
  }, [id])

  const sendIntervention = useCallback(async () => {
    if (!intervention.trim() || sending) return
    setSending(true)
    const msg = intervention.trim()
    const res = await fetch(`${API_BASE}/v1/workbench/sessions/${id}/message`, {
      method: 'POST', headers: AUTH_HEADERS,
      body: JSON.stringify({ message: msg })
    })
    if (res.ok) {
      // Optimistically add user's message to event log + flip status to running
      setEvents(prev => [...prev, {
        type: 'user_message',
        payload: { message: msg, handled: true },
        ts: new Date().toISOString(),
      }])
      setStatus('running')
      setWaitingForHuman(false)
      setIntervention('')
    }
    setSending(false)
  }, [id, intervention, sending])

  const cancelSession = async () => {
    if (!confirm('Cancel this session?')) return
    await fetch(`${API_BASE}/v1/workbench/sessions/${id}/cancel`, { method: 'POST', headers: AUTH_HEADERS })
    setStatus('cancelled')
  }
  const completeSession = async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/workbench/sessions/${id}/complete`, { method: 'POST', headers: AUTH_HEADERS })
      if (!res.ok) {
        const body = await res.text()
        throw new Error(`HTTP ${res.status}: ${body.slice(0, 200)}`)
      }
      setStatus('completed')
    } catch (e: any) {
      alert(`Failed to mark session complete: ${e.message}\n\nIf this says "Not Found", restart the backend so it picks up the new endpoint.`)
    }
  }

  // Click file in the tree → fetch full content from disk (SSE payload is truncated)
  const selectFile = useCallback(async (f: FileEntry) => {
    // Show immediately with preview, then replace with full content
    setSelectedFile(f)
    if (f.diff) return  // diff view doesn't need a file read
    try {
      const url = `${API_BASE}/v1/workbench/sessions/${id}/files/read?path=${encodeURIComponent(f.path)}`
      const res = await fetch(url, { headers: AUTH_HEADERS })
      if (!res.ok) return  // keep truncated preview
      const data = await res.json()
      setSelectedFile({ ...f, content: data.content })
    } catch { /* silent — keep truncated preview */ }
  }, [id])

  const STATUS_BADGE: Record<string, string> = {
    connecting:   'bg-gray-100 text-gray-600',
    pending:      'bg-yellow-100 text-yellow-700',
    running:      'bg-blue-100 text-blue-700',
    waiting:      'bg-orange-100 text-orange-700',
    completed:    'bg-green-100 text-green-700',
    cancelled:    'bg-gray-100 text-gray-500',
    error:        'bg-red-100 text-red-700',
    disconnected: 'bg-red-100 text-red-600',
  }

  const isActive = status === 'running' || status === 'pending' || status === 'waiting'

  return (
    <div className="flex flex-col h-full -m-6 lg:-m-10">

      {/* Top bar */}
      <div className="flex items-center gap-3 px-6 py-3 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
        <button onClick={() => router.push('/workbench')}
          className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 transition-colors flex-shrink-0">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        <div className="flex-1 min-w-0">
          <p className="text-xs text-gray-400 uppercase tracking-wider">Session</p>
          <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
            {session?.task || 'Loading…'}
          </p>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <button onClick={() => setAutoScroll(a => !a)}
            className={`px-2.5 py-1 text-xs rounded-lg border transition-colors ${autoScroll ? 'bg-green-50 border-green-200 text-green-700' : 'border-gray-200 text-gray-500'}`}>
            {autoScroll ? '↓ Auto' : '↓ Manual'}
          </button>
          {isActive && status !== 'waiting' && (
            <button onClick={cancelSession}
              className="px-3 py-1.5 text-xs font-medium rounded-lg border border-red-200 text-red-600 hover:bg-red-50 transition-colors">
              Cancel
            </button>
          )}
          {status === 'waiting' && (
            <button onClick={completeSession}
              className="px-3 py-1.5 text-xs font-medium rounded-lg bg-green-600 hover:bg-green-700 text-white transition-colors"
              title="Mark session as complete — closes it out, no more follow-ups">
              ✓ Mark complete
            </button>
          )}
        </div>
      </div>

      {/* Main 3-panel layout */}
      <div className="flex-1 flex min-h-0 overflow-hidden">

        {/* LEFT: File tree */}
        <div className="w-56 flex-shrink-0 border-r border-gray-200 dark:border-gray-700 flex flex-col bg-gray-50 dark:bg-gray-900">
          <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Files ({files.length})</p>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            <FileTree files={files} selected={selectedFile?.path || null} onSelect={selectFile} />
          </div>
        </div>

        {/* CENTER: Conversation timeline */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          {/* Agent Card header */}
          <AgentCard
            agentType={session?.agent_type || 'coder'}
            model={session?.model || 'unknown'}
            status={status}
            currentActivity={(() => {
              // Latest agent_thought or info from the current turn
              for (let i = events.length - 1; i >= 0; i--) {
                const e = events[i]
                if (e.type === 'user_message') break
                if (e.type === 'agent_thought') return e.payload.thought
                if (e.type === 'info') return e.payload.message
              }
              return null
            })()}
            currentRole={(() => {
              // Most recent role_change event (since last user_message)
              for (let i = events.length - 1; i >= 0; i--) {
                const e = events[i]
                if (e.type === 'user_message') break
                if (e.type === 'role_change') return e.payload.role
              }
              return null
            })()}
            turnCount={events.filter(e => e.type === 'user_message').length + (session?.task ? 1 : 0)}
            fileCount={files.length}
          />

          {/* Conversation turns */}
          <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
            {(() => {
              const turns = buildTurns(events, session?.task || null)
              if (turns.length === 0) {
                return (
                  <div className="flex items-center justify-center h-full">
                    <div className="text-center text-gray-400">
                      <div className="text-3xl mb-2">⚡</div>
                      <p className="text-sm">Connecting to agent…</p>
                    </div>
                  </div>
                )
              }
              return turns.map((turn, i) => (
                <TurnBubble
                  key={i}
                  turn={turn}
                  isLast={i === turns.length - 1}
                  isActive={isActive}
                />
              ))
            })()}
            <div ref={streamEndRef} />
          </div>

          {/* Intervention bar */}
          <div className={`flex-shrink-0 border-t transition-colors ${
            waitingForHuman
              ? 'border-orange-300 dark:border-orange-600 bg-orange-50 dark:bg-orange-900/10'
              : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900'
          } px-4 py-3`}>
            {waitingForHuman && (
              <div className="flex items-center gap-2 mb-2 text-xs font-medium text-orange-600 dark:text-orange-400">
                <span className="w-2 h-2 rounded-full bg-orange-400 animate-pulse" />
                Agent is waiting for your input
              </div>
            )}
            <div className="flex gap-2">
              <input
                ref={inputRef}
                value={intervention}
                onChange={e => setIntervention(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && sendIntervention()}
                placeholder={waitingForHuman ? 'Type your response to the agent...' : 'Send a message to the agent (e.g. "use port 3001", "skip that step")...'}
                disabled={!isActive && !waitingForHuman}
                className={`flex-1 rounded-xl border px-3.5 py-2 text-sm focus:outline-none focus:ring-2 disabled:opacity-40 dark:bg-gray-800 dark:text-white ${
                  waitingForHuman
                    ? 'border-orange-300 focus:ring-orange-400 dark:border-orange-600'
                    : 'border-gray-200 dark:border-gray-700 focus:ring-gray-400'
                }`}
              />
              <button
                onClick={sendIntervention}
                disabled={!intervention.trim() || sending || (!isActive && !waitingForHuman)}
                className={`px-4 py-2 text-sm font-medium rounded-xl text-white transition-colors disabled:opacity-40 ${
                  waitingForHuman
                    ? 'bg-orange-500 hover:bg-orange-600'
                    : 'bg-gray-700 hover:bg-gray-800'
                }`}
              >
                {sending ? '...' : 'Send'}
              </button>
            </div>
            <p className="text-xs text-gray-400 mt-1.5">
              {isActive ? 'Agent will receive your message on its next iteration.' : 'Session ended — no new messages can be sent.'}
            </p>
          </div>
        </div>

        {/* RIGHT: File preview */}
        <div className="w-80 flex-shrink-0 border-l border-gray-200 dark:border-gray-700 flex flex-col bg-white dark:bg-gray-900">
          <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider truncate">
              {selectedFile ? selectedFile.path : 'File Preview'}
            </p>
            {selectedFile && (
              <button onClick={() => setSelectedFile(null)} className="text-gray-400 hover:text-gray-600 text-xs ml-2">✕</button>
            )}
          </div>
          <div className="flex-1 overflow-auto p-3">
            {!selectedFile ? (
              <div className="flex items-center justify-center h-full text-center">
                <div className="text-gray-400">
                  <div className="text-3xl mb-2">📄</div>
                  <p className="text-xs">Click a file in the tree to preview it</p>
                </div>
              </div>
            ) : (
              <pre className="text-xs font-mono text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-all">
                {selectedFile.diff
                  ? selectedFile.diff.split('\n').map((line, i) => (
                      <span key={i} className={`block ${line.startsWith('+') ? 'text-green-600 bg-green-50 dark:bg-green-900/20' : line.startsWith('-') ? 'text-red-600 bg-red-50 dark:bg-red-900/20' : ''}`}>
                        {line}
                      </span>
                    ))
                  : selectedFile.content || '(empty)'}
              </pre>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
