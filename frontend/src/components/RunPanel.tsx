'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { API_BASE, AUTH_HEADERS } from '@/lib/config'

interface RunEvent {
  type: string
  stream?: 'stdout' | 'stderr'
  text?: string
  ts?: string
  [k: string]: any
}

interface RunConfig {
  run_command: string
  detected_command: string
  venv_python: string | null
  effective_command: string
}

interface RunStatus {
  running: boolean
  pid: number | null
  command?: string
  started_at?: string
  exit_code?: number | null
}

/**
 * RunPanel — terminal-style panel for running a project's command and
 * viewing its live output. Reusable on the project detail page and the
 * workbench detail page.
 */
export function RunPanel({
  projectId,
  compact = false,
}: {
  projectId: string
  compact?: boolean
}) {
  const [config, setConfig] = useState<RunConfig | null>(null)
  const [status, setStatus] = useState<RunStatus>({ running: false, pid: null })
  const [output, setOutput] = useState<RunEvent[]>([])
  const [command, setCommand] = useState('')
  const [editingCommand, setEditingCommand] = useState(false)
  const [savingCommand, setSavingCommand] = useState(false)
  const [starting, setStarting] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const outputEndRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)

  // Extract "localhost:PORT" URLs from the output for a quick-open button
  const detectedUrls = Array.from(new Set(
    output
      .filter(e => e.type === 'output' && e.text)
      .flatMap(e => {
        const m = (e.text || '').match(/https?:\/\/(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?::\d+)?[^\s)]*/gi)
        return m || []
      })
      .map(u => u.replace('0.0.0.0', 'localhost').replace('127.0.0.1', 'localhost'))
  )).slice(0, 3)

  // Load config once
  useEffect(() => {
    fetch(`${API_BASE}/v1/projects/${projectId}/run/config`, { headers: AUTH_HEADERS })
      .then(r => r.ok ? r.json() : null)
      .then(c => {
        if (c) {
          setConfig(c)
          setCommand(c.run_command || c.detected_command || '')
        }
      })
      .catch(() => {})
  }, [projectId])

  // Subscribe to SSE stream
  useEffect(() => {
    const es = new EventSource(`${API_BASE}/v1/projects/${projectId}/run/stream`)
    esRef.current = es
    es.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data) as RunEvent
        if (evt.type === 'ping') return
        if (evt.type === 'init') {
          setStatus(evt.payload as RunStatus)
          return
        }
        setOutput(prev => [...prev, evt])
        if (evt.type === 'started') {
          setStatus({ running: true, pid: evt.pid, command: evt.command, started_at: evt.ts })
          setStarting(false)
        } else if (evt.type === 'exited' || evt.type === 'stopped') {
          setStatus(s => ({ ...s, running: false, exit_code: evt.return_code ?? null }))
        } else if (evt.type === 'error') {
          setStarting(false)
        }
      } catch { /* ignore */ }
    }
    es.onerror = () => { /* browser auto-retries */ }
    return () => { es.close(); esRef.current = null }
  }, [projectId])

  // Auto-scroll
  useEffect(() => {
    if (autoScroll) outputEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [output, autoScroll])

  const saveCommand = async () => {
    setSavingCommand(true)
    try {
      const res = await fetch(`${API_BASE}/v1/projects/${projectId}/run/config`, {
        method: 'PUT',
        headers: AUTH_HEADERS,
        body: JSON.stringify({ run_command: command }),
      })
      if (res.ok) {
        const updated = await res.json()
        setConfig(c => c ? { ...c, run_command: updated.run_command, effective_command: updated.run_command } : c)
        setEditingCommand(false)
      } else {
        alert(`Save failed: ${res.status}`)
      }
    } catch (e: any) {
      alert(`Save failed: ${e.message}`)
    } finally {
      setSavingCommand(false)
    }
  }

  const start = async () => {
    setStarting(true)
    setOutput([])  // clear previous output on fresh run
    try {
      const res = await fetch(`${API_BASE}/v1/projects/${projectId}/run`, {
        method: 'POST',
        headers: AUTH_HEADERS,
        body: JSON.stringify({}),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: 'unknown error' }))
        alert(`Run failed: ${body.detail || res.status}`)
        setStarting(false)
      }
      // `started` event will flip starting=false + set status
    } catch (e: any) {
      alert(`Run failed: ${e.message}`)
      setStarting(false)
    }
  }

  const stop = async () => {
    try {
      await fetch(`${API_BASE}/v1/projects/${projectId}/run/stop`, {
        method: 'POST',
        headers: AUTH_HEADERS,
      })
    } catch (e) {
      console.error(e)
    }
  }

  const clearOutput = async () => {
    setOutput([])
    await fetch(`${API_BASE}/v1/projects/${projectId}/run/buffer`, {
      method: 'DELETE',
      headers: AUTH_HEADERS,
    })
  }

  const effectiveCommand = config?.run_command || config?.detected_command || ''
  const isRunning = status.running

  return (
    <div className={`flex flex-col rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 overflow-hidden ${compact ? '' : 'h-full'}`}>
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${isRunning ? 'bg-green-400 animate-pulse' : status.exit_code != null && status.exit_code !== 0 ? 'bg-red-400' : 'bg-gray-300'}`} />
        <span className="text-xs font-semibold text-gray-700 dark:text-gray-300 flex-shrink-0">
          {isRunning ? `Running (pid ${status.pid})` : status.exit_code != null ? `Exited (${status.exit_code})` : 'Idle'}
        </span>
        <div className="flex-1 min-w-0">
          {editingCommand ? (
            <input
              value={command}
              onChange={e => setCommand(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') saveCommand(); if (e.key === 'Escape') setEditingCommand(false) }}
              className="w-full px-2 py-0.5 text-xs font-mono border border-indigo-300 dark:border-indigo-700 rounded bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-400"
              placeholder="e.g. python main.py"
              autoFocus
            />
          ) : (
            <button
              onClick={() => setEditingCommand(true)}
              className="w-full text-left text-xs font-mono text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white truncate"
              title="Click to edit run command"
            >
              {effectiveCommand || <span className="italic text-gray-400">no run command — click to set</span>}
              {config?.venv_python && command.startsWith('python') && <span className="ml-1 text-[10px] text-green-600 dark:text-green-400">(venv)</span>}
            </button>
          )}
        </div>
        <div className="flex gap-1 flex-shrink-0">
          {editingCommand ? (
            <>
              <button onClick={saveCommand} disabled={savingCommand}
                className="px-2 py-0.5 text-xs rounded bg-indigo-500 hover:bg-indigo-600 text-white disabled:opacity-50">
                {savingCommand ? '…' : 'Save'}
              </button>
              <button onClick={() => setEditingCommand(false)}
                className="px-2 py-0.5 text-xs rounded border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700">
                Cancel
              </button>
            </>
          ) : isRunning ? (
            <button onClick={stop}
              className="px-3 py-1 text-xs font-semibold rounded bg-red-500 hover:bg-red-600 text-white">
              ■ Stop
            </button>
          ) : (
            <button onClick={start} disabled={starting || !effectiveCommand}
              className="px-3 py-1 text-xs font-semibold rounded bg-green-600 hover:bg-green-700 text-white disabled:opacity-40 disabled:cursor-not-allowed">
              {starting ? 'Starting…' : '▶ Run'}
            </button>
          )}
        </div>
      </div>

      {/* Detected URLs */}
      {detectedUrls.length > 0 && (
        <div className="flex items-center gap-2 px-3 py-1.5 border-b border-gray-200 dark:border-gray-700 bg-indigo-50 dark:bg-indigo-900/20">
          <span className="text-[10px] uppercase tracking-wider font-semibold text-indigo-700 dark:text-indigo-300">Detected</span>
          {detectedUrls.map(url => (
            <a key={url} href={url} target="_blank" rel="noreferrer"
              className="text-xs font-mono text-indigo-600 dark:text-indigo-300 hover:underline truncate">
              {url} ↗
            </a>
          ))}
        </div>
      )}

      {/* Output */}
      <div className={`flex-1 overflow-y-auto bg-gray-950 text-gray-200 p-2 font-mono text-[11px] leading-relaxed ${compact ? 'max-h-60' : ''}`}>
        {output.length === 0 ? (
          <div className="text-gray-500 italic p-2">No output yet. Click ▶ Run to start.</div>
        ) : (
          output.map((evt, i) => {
            if (evt.type === 'output') {
              const color = evt.stream === 'stderr' ? 'text-red-300' : 'text-gray-200'
              return <div key={i} className={`whitespace-pre-wrap ${color}`}>{evt.text}</div>
            }
            if (evt.type === 'starting') {
              return <div key={i} className="text-cyan-300">$ {evt.command}</div>
            }
            if (evt.type === 'started') {
              return <div key={i} className="text-green-400">--- started (pid {evt.pid}) ---</div>
            }
            if (evt.type === 'exited') {
              const rc = evt.return_code
              const color = rc === 0 ? 'text-green-400' : 'text-red-400'
              return <div key={i} className={color}>--- exited with code {rc} ---</div>
            }
            if (evt.type === 'stopped') {
              return <div key={i} className="text-amber-400">--- stopped ---</div>
            }
            if (evt.type === 'killed_previous') {
              return <div key={i} className="text-amber-400">--- killed previous run (pid {evt.pid}) ---</div>
            }
            if (evt.type === 'error') {
              return <div key={i} className="text-red-400">ERROR: {evt.message}</div>
            }
            return null
          })
        )}
        <div ref={outputEndRef} />
      </div>

      {/* Footer controls */}
      <div className="flex items-center justify-between px-3 py-1 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 text-[10px] text-gray-500 dark:text-gray-400">
        <button onClick={() => setAutoScroll(a => !a)}
          className={autoScroll ? 'text-green-600 dark:text-green-400' : ''}>
          {autoScroll ? '↓ auto-scroll' : '↓ manual'}
        </button>
        <button onClick={clearOutput} className="hover:text-gray-700 dark:hover:text-gray-200">
          Clear
        </button>
      </div>
    </div>
  )
}
