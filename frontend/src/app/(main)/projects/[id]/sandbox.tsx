'use client'

import { useState, useEffect, useCallback } from 'react'

const API_BASE = 'http://localhost:19000'
const AUTH = { 'Authorization': 'Bearer modelmesh_local_dev_key', 'Content-Type': 'application/json' }

interface SandboxStatus {
  project_id: string
  project_name: string
  path_exists: boolean
  venv_exists: boolean
  venv_path: string | null
  git_initialized: boolean
  git_status: string | null
  snapshots: Array<{ hash: string; message: string }>
  installed_packages: string[]
}

export function SandboxPanel({ projectId }: { projectId: string }) {
  const [status, setStatus] = useState<SandboxStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [output, setOutput] = useState<{ type: 'ok' | 'error'; text: string } | null>(null)
  const [packages, setPackages] = useState('')
  const [snapMsg, setSnapMsg] = useState('')
  const [envKey, setEnvKey] = useState('')
  const [envVal, setEnvVal] = useState('')
  const [envVars, setEnvVars] = useState<Record<string, string>>({})

  const fetchStatus = useCallback(async () => {
    const res = await fetch(`${API_BASE}/v1/sandbox/projects/${projectId}/status`, { headers: AUTH })
      .then(r => r.json()).catch(() => null)
    if (res) setStatus(res)
    setLoading(false)
  }, [projectId])

  const fetchEnvVars = useCallback(async () => {
    const res = await fetch(`${API_BASE}/v1/sandbox/projects/${projectId}/env-vars`, { headers: AUTH })
      .then(r => r.json()).catch(() => ({ env_vars: {} }))
    setEnvVars(res.env_vars || {})
  }, [projectId])

  useEffect(() => { fetchStatus(); fetchEnvVars() }, [fetchStatus, fetchEnvVars])

  const run = async (fn: () => Promise<any>, successMsg?: string) => {
    setWorking(true)
    setOutput(null)
    try {
      const res = await fn()
      if (res.ok === false || res.detail) throw new Error(res.detail || res.stderr || 'Failed')
      setOutput({ type: 'ok', text: successMsg || res.message || res.output || 'Done' })
      await fetchStatus()
    } catch (e: any) {
      setOutput({ type: 'error', text: e.message })
    } finally {
      setWorking(false)
    }
  }

  const createVenv = () => run(async () =>
    fetch(`${API_BASE}/v1/sandbox/projects/${projectId}/venv`, {
      method: 'POST', headers: AUTH,
      body: JSON.stringify({ requirements: packages || null })
    }).then(r => r.json())
  )

  const gitInit = () => run(async () =>
    fetch(`${API_BASE}/v1/sandbox/projects/${projectId}/git/init`, {
      method: 'POST', headers: AUTH, body: '{}'
    }).then(r => r.json()), 'Git repository initialized'
  )

  const createSnapshot = () => run(async () =>
    fetch(`${API_BASE}/v1/sandbox/projects/${projectId}/snapshot`, {
      method: 'POST', headers: AUTH,
      body: JSON.stringify({ message: snapMsg || 'DevForgeAI snapshot' })
    }).then(r => r.json()),
    `Snapshot created: "${snapMsg || 'DevForgeAI snapshot'}"`
  )

  const rollback = (hash: string, message: string) => {
    if (!confirm(`Roll back to "${message}" (${hash})?\n\nA safety snapshot will be created first.`)) return
    run(async () =>
      fetch(`${API_BASE}/v1/sandbox/projects/${projectId}/rollback`, {
        method: 'POST', headers: AUTH, body: JSON.stringify({ commit_hash: hash })
      }).then(r => r.json()), `Rolled back to ${hash}`
    )
  }

  const installPackages = () => {
    if (!packages.trim()) return
    run(async () =>
      fetch(`${API_BASE}/v1/sandbox/projects/${projectId}/install`, {
        method: 'POST', headers: AUTH, body: JSON.stringify({ requirements: packages })
      }).then(r => r.json()), `Installed: ${packages}`
    )
  }

  const saveEnvVar = async () => {
    if (!envKey.trim()) return
    const updated = { ...envVars, [envKey]: envVal }
    await fetch(`${API_BASE}/v1/sandbox/projects/${projectId}/env-vars`, {
      method: 'POST', headers: AUTH, body: JSON.stringify(updated)
    })
    setEnvVars(updated)
    setEnvKey(''); setEnvVal('')
  }

  const deleteEnvVar = async (key: string) => {
    const updated = Object.fromEntries(Object.entries(envVars).filter(([k]) => k !== key))
    await fetch(`${API_BASE}/v1/sandbox/projects/${projectId}/env-vars`, {
      method: 'POST', headers: AUTH, body: JSON.stringify(updated)
    })
    setEnvVars(updated)
  }

  if (loading) return <div className="text-sm text-gray-400 py-8 text-center">Loading sandbox...</div>
  if (!status) return <div className="text-sm text-red-400 py-4">Failed to load sandbox status</div>

  return (
    <div className="space-y-5 p-1">
      {/* Status summary */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Python venv', ok: status.venv_exists, okText: 'Created', failText: 'Not created' },
          { label: 'Git', ok: status.git_initialized, okText: 'Initialized', failText: 'Not initialized' },
          { label: 'Project path', ok: status.path_exists, okText: 'Found', failText: 'Missing' },
        ].map(s => (
          <div key={s.label} className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm ${s.ok ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-700' : 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700'}`}>
            <span className={s.ok ? 'text-green-500' : 'text-gray-400'}>{s.ok ? '✓' : '○'}</span>
            <div>
              <p className="font-medium text-gray-800 dark:text-white text-xs">{s.label}</p>
              <p className={`text-xs ${s.ok ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`}>{s.ok ? s.okText : s.failText}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Output */}
      {output && (
        <div className={`px-3 py-2 rounded-lg text-sm ${output.type === 'ok' ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-700' : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-700'}`}>
          {output.type === 'ok' ? '✓ ' : '✗ '}{output.text}
        </div>
      )}

      {/* Virtual Environment */}
      <Section title="🐍 Python Virtual Environment">
        {status.venv_exists ? (
          <div className="space-y-3">
            <p className="text-xs font-mono text-gray-500 bg-gray-50 dark:bg-gray-900 px-2 py-1 rounded">{status.venv_path}</p>
            {status.installed_packages.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {status.installed_packages.map(p => (
                  <span key={p} className="text-xs px-2 py-0.5 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded-full font-mono">{p}</span>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <input value={packages} onChange={e => setPackages(e.target.value)}
                placeholder="fastapi uvicorn requests..."
                className="flex-1 text-sm rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-orange-400" />
              <button onClick={installPackages} disabled={working || !packages.trim()}
                className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-40">
                pip install
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-gray-500">No virtual environment yet. Create one to isolate this project's dependencies.</p>
            <div className="flex gap-2">
              <input value={packages} onChange={e => setPackages(e.target.value)}
                placeholder="Initial packages (optional): fastapi uvicorn..."
                className="flex-1 text-sm rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-orange-400" />
              <button onClick={createVenv} disabled={working}
                className="px-3 py-1.5 text-sm bg-green-600 hover:bg-green-700 text-white rounded-lg disabled:opacity-40">
                {working ? '...' : 'Create venv'}
              </button>
            </div>
          </div>
        )}
      </Section>

      {/* Git / Snapshots */}
      <Section title="📷 Snapshots (Git)">
        {!status.git_initialized ? (
          <div className="space-y-2">
            <p className="text-sm text-gray-500">Initialize git to enable snapshots and rollbacks.</p>
            <button onClick={gitInit} disabled={working}
              className="px-3 py-1.5 text-sm bg-gray-700 hover:bg-gray-800 text-white rounded-lg disabled:opacity-40">
              Initialize Git
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {status.git_status && (
              <pre className="text-xs font-mono text-gray-500 bg-gray-50 dark:bg-gray-900 px-3 py-2 rounded-lg overflow-x-auto">{status.git_status || 'Working tree clean'}</pre>
            )}
            <div className="flex gap-2">
              <input value={snapMsg} onChange={e => setSnapMsg(e.target.value)}
                placeholder="Snapshot message..."
                className="flex-1 text-sm rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-orange-400"
                onKeyDown={e => e.key === 'Enter' && createSnapshot()} />
              <button onClick={createSnapshot} disabled={working}
                className="px-3 py-1.5 text-sm bg-orange-500 hover:bg-orange-600 text-white rounded-lg disabled:opacity-40">
                📷 Snapshot
              </button>
            </div>
            {status.snapshots.length > 0 && (
              <div className="space-y-1">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">History</p>
                {status.snapshots.map((s, i) => (
                  <div key={s.hash} className="flex items-center justify-between py-1.5 px-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700">
                    <div className="flex items-center gap-2 min-w-0">
                      {i === 0 && <span className="text-xs bg-green-100 text-green-700 px-1.5 py-0.5 rounded-full">latest</span>}
                      <code className="text-xs text-gray-400 font-mono flex-shrink-0">{s.hash}</code>
                      <span className="text-sm text-gray-700 dark:text-gray-300 truncate">{s.message}</span>
                    </div>
                    {i > 0 && (
                      <button onClick={() => rollback(s.hash, s.message)} disabled={working}
                        className="text-xs text-orange-600 hover:text-orange-800 border border-orange-200 px-2 py-0.5 rounded ml-2 flex-shrink-0 disabled:opacity-40">
                        Rollback
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Section>

      {/* Environment Variables */}
      <Section title="🔒 Environment Variables (.env)">
        <div className="space-y-2">
          {Object.entries(envVars).map(([k, v]) => (
            <div key={k} className="flex items-center gap-2 text-sm">
              <code className="font-mono text-xs bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded text-gray-700 dark:text-gray-300 w-40 truncate">{k}</code>
              <code className="font-mono text-xs text-gray-500 flex-1 truncate">{v.length > 20 ? v.substring(0, 20) + '...' : v}</code>
              <button onClick={() => deleteEnvVar(k)} className="text-red-400 hover:text-red-600 text-xs">✕</button>
            </div>
          ))}
          <div className="flex gap-2 mt-2">
            <input value={envKey} onChange={e => setEnvKey(e.target.value)}
              placeholder="KEY"
              className="w-32 text-sm font-mono rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-orange-400" />
            <input value={envVal} onChange={e => setEnvVal(e.target.value)}
              placeholder="value"
              className="flex-1 text-sm rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-orange-400"
              onKeyDown={e => e.key === 'Enter' && saveEnvVar()} />
            <button onClick={saveEnvVar} disabled={!envKey.trim()}
              className="px-3 py-1.5 text-sm bg-gray-700 hover:bg-gray-800 text-white rounded-lg disabled:opacity-40">
              Add
            </button>
          </div>
        </div>
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="px-4 py-2.5 border-b border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
        <p className="text-sm font-semibold text-gray-700 dark:text-gray-300">{title}</p>
      </div>
      <div className="px-4 py-4">{children}</div>
    </div>
  )
}
