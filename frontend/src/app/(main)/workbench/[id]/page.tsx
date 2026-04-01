'use client'

// Dynamic rendering for workbench
export const dynamic = 'force-dynamic'
export const revalidate = 0

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

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
            const exists = prev.find(f => f.path === evt.payload.path)
            if (exists) return prev
            return [...prev, { path: evt.payload.path, status: 'created' as const, content: evt.payload.content }]
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
          setStatus(evt.payload.status || 'completed')
          setWaitingForHuman(false)
          es.close()
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
    await fetch(`${API_BASE}/v1/workbench/sessions/${id}/message`, {
      method: 'POST', headers: AUTH_HEADERS,
      body: JSON.stringify({ message: intervention.trim() })
    })
    setIntervention('')
    setWaitingForHuman(false)
    setSending(false)
  }, [id, intervention, sending])

  const cancelSession = async () => {
    if (!confirm('Cancel this session?')) return
    await fetch(`${API_BASE}/v1/workbench/sessions/${id}/cancel`, { method: 'POST', headers: AUTH_HEADERS })
    setStatus('cancelled')
  }

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
          <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
            {session?.task || 'Loading...'}
          </p>
          <div className="flex items-center gap-2 mt-0.5">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[status] || 'bg-gray-100 text-gray-600'}`}>
              {isActive && <span className="inline-block w-1.5 h-1.5 rounded-full bg-current mr-1 animate-pulse" />}
              {status}
            </span>
            {session && <span className="text-xs text-gray-400">{session.agent_type} · {session.model}</span>}
            <span className="text-xs text-gray-300">{events.filter(e => e.type !== 'ping').length} events</span>
          </div>
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
            <FileTree files={files} selected={selectedFile?.path || null} onSelect={f => setSelectedFile(f)} />
          </div>
        </div>

        {/* CENTER: Event stream */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          <div className="flex-1 overflow-y-auto p-4 space-y-0.5 font-mono text-xs">
            {events.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center text-gray-400">
                  <div className="text-3xl mb-2">⚡</div>
                  <p className="text-sm">Connecting to agent stream...</p>
                </div>
              </div>
            ) : (
              events.map((evt, i) => <EventRow key={i} evt={evt} index={i} />)
            )}
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
