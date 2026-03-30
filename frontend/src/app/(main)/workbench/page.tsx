'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'

const API_BASE = 'http://localhost:19000'
const AUTH = { 'Authorization': 'Bearer modelmesh_local_dev_key', 'Content-Type': 'application/json' }

const AGENT_ICONS: Record<string, string> = {
  coder: '💻', researcher: '🔍', designer: '🎨',
  reviewer: '🔎', planner: '📋', executor: '⚡', writer: '✍️',
}

interface Session { id: string; task: string; agent_type: string; model: string; status: string; created_at: string }

export default function WorkbenchListPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [task, setTask] = useState('')
  const [agentType, setAgentType] = useState('coder')
  const [model, setModel] = useState('ollama/glm4:latest')
  const [creating, setCreating] = useState(false)
  const [projectId, setProjectId] = useState<string | null>(null)

  const fetchSessions = useCallback(async () => {
    const res = await fetch(`${API_BASE}/v1/workbench/sessions`, { headers: AUTH }).then(r => r.json()).catch(() => ({ data: [] }))
    setSessions(res.data || [])
    setLoading(false)
  }, [])

  useEffect(() => { fetchSessions() }, [fetchSessions])

  // Auto-open new session modal if coming from a project
  useEffect(() => {
    const pid = searchParams?.get('project')
    if (pid) {
      setProjectId(pid)
      setShowNew(true)
    }
  }, [searchParams])

  const createSession = async () => {
    if (!task.trim() || creating) return
    setCreating(true)
    const body: any = { task: task.trim(), agent_type: agentType, model }
    if (projectId) body.project_id = projectId
    const res = await fetch(`${API_BASE}/v1/workbench/sessions`, {
      method: 'POST', headers: AUTH,
      body: JSON.stringify(body),
    }).then(r => r.json())
    router.push(`/workbench/${res.id}`)
  }

  const STATUS_COLOR: Record<string, string> = {
    pending: 'text-yellow-600 bg-yellow-50', running: 'text-blue-600 bg-blue-50',
    completed: 'text-green-600 bg-green-50', failed: 'text-red-600 bg-red-50',
    cancelled: 'text-gray-500 bg-gray-50',
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Workbench</h1>
          <p className="mt-1 text-sm text-gray-500">Watch agents build in real-time — and step in when needed</p>
        </div>
        <button onClick={() => setShowNew(true)}
          className="flex items-center gap-2 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium rounded-lg transition-colors">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Session
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="flex gap-1.5">{[0,1,2].map(i => <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />)}</div>
        </div>
      ) : sessions.length === 0 ? (
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
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sessions.map(s => (
            <button key={s.id} onClick={() => router.push(`/workbench/${s.id}`)}
              className="text-left bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 hover:border-orange-300 hover:shadow-md transition-all">
              <div className="flex items-start justify-between mb-3">
                <span className="text-2xl">{AGENT_ICONS[s.agent_type] || '🤖'}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLOR[s.status] || 'bg-gray-100 text-gray-600'}`}>{s.status}</span>
              </div>
              <p className="text-sm font-medium text-gray-900 dark:text-white line-clamp-2 mb-2">{s.task}</p>
              <p className="text-xs text-gray-400">{s.agent_type} · {s.model}</p>
            </button>
          ))}
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
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Task</label>
                <textarea value={task} onChange={e => setTask(e.target.value)} rows={4}
                  placeholder="Describe what you want to build or accomplish..."
                  className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none" />
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
                  <input value={model} onChange={e => setModel(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
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
