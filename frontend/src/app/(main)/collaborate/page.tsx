'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { useState, useEffect, useCallback } from 'react'


interface User {
  id: string; username: string; display_name: string
  role: string; is_active: boolean; created_at: string; last_active?: string
  has_github_token?: boolean; github_token_masked?: string | null
}
interface AuditEntry {
  id: string; ts: string; action: string; resource_type: string
  resource_id?: string; details?: string; user: string
}
interface Workspace {
  id: string; name: string; description?: string
  project_ids: string[]; member_ids: string[]; created_at: string
}
interface Handoff {
  id: string; from_user: string; to_user: string
  conversation_id: string; note?: string; status: string; created_at: string
}

const ROLE_COLORS: Record<string, string> = {
  owner: 'bg-purple-100 text-purple-700', admin: 'bg-red-100 text-red-700',
  member: 'bg-blue-100 text-blue-700', viewer: 'bg-gray-100 text-gray-600',
}

export default function CollaboratePage() {
  const [tab, setTab] = useState<'users' | 'workspaces' | 'audit' | 'handoffs'>('users')
  const [users, setUsers] = useState<User[]>([])
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [handoffs, setHandoffs] = useState<Handoff[]>([])
  const [loading, setLoading] = useState(true)

  // New user form
  const [showNewUser, setShowNewUser] = useState(false)
  const [userForm, setUserForm] = useState({ username: '', display_name: '', password: '', role: 'member', github_token: '' })
  const [savingUser, setSavingUser] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [editForm, setEditForm] = useState({ display_name: '', role: 'member', github_token: '' })
  const [savingEdit, setSavingEdit] = useState(false)

  // New workspace form
  const [showNewWs, setShowNewWs] = useState(false)
  const [wsForm, setWsForm] = useState({ name: '', description: '' })
  const [savingWs, setSavingWs] = useState(false)

  const fetchAll = useCallback(async () => {
    const [usersRes, auditRes, wsRes, handoffsRes] = await Promise.all([
      fetch(`${API_BASE}/v1/collab/users`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ data: [] })),
      fetch(`${API_BASE}/v1/collab/audit?limit=30`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ data: [] })),
      fetch(`${API_BASE}/v1/collab/workspaces`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ data: [] })),
      fetch(`${API_BASE}/v1/collab/handoff`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ data: [] })),
    ])
    setUsers(usersRes.data || [])
    setAudit(auditRes.data || [])
    setWorkspaces(wsRes.data || [])
    setHandoffs(handoffsRes.data || [])
    setLoading(false)
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  const createUser = async () => {
    if (!userForm.username.trim() || !userForm.password.trim()) return
    setSavingUser(true)
    await fetch(`${API_BASE}/v1/collab/users`, {
      method: 'POST', headers: AUTH_HEADERS, body: JSON.stringify(userForm)
    })
    setShowNewUser(false)
    setUserForm({ username: '', display_name: '', password: '', role: 'member', github_token: '' })
    setSavingUser(false)
    fetchAll()
  }

  const openEditUser = (user: User) => {
    setEditingUser(user)
    setEditForm({
      display_name: user.display_name,
      role: user.role,
      github_token: '',
    })
  }

  const saveUserEdit = async () => {
    if (!editingUser) return
    setSavingEdit(true)
    await fetch(`${API_BASE}/v1/collab/users/${editingUser.id}`, {
      method: 'PATCH',
      headers: AUTH_HEADERS,
      body: JSON.stringify({
        display_name: editForm.display_name,
        role: editForm.role,
        github_token: editForm.github_token,
      }),
    })
    setSavingEdit(false)
    setEditingUser(null)
    fetchAll()
  }

  const deleteUser = async (id: string, name: string) => {
    if (!confirm(`Remove user "${name}"?`)) return
    await fetch(`${API_BASE}/v1/collab/users/${id}`, { method: 'DELETE', headers: AUTH_HEADERS })
    fetchAll()
  }

  const createWorkspace = async () => {
    if (!wsForm.name.trim()) return
    setSavingWs(true)
    await fetch(`${API_BASE}/v1/collab/workspaces`, {
      method: 'POST', headers: AUTH_HEADERS,
      body: JSON.stringify({ name: wsForm.name, description: wsForm.description, project_ids: [], member_ids: [] })
    })
    setShowNewWs(false)
    setWsForm({ name: '', description: '' })
    setSavingWs(false)
    fetchAll()
  }

  const deleteWorkspace = async (id: string) => {
    await fetch(`${API_BASE}/v1/collab/workspaces/${id}`, { method: 'DELETE', headers: AUTH_HEADERS })
    fetchAll()
  }

  const acceptHandoff = async (id: string) => {
    await fetch(`${API_BASE}/v1/collab/handoff/${id}/accept`, { method: 'POST', headers: AUTH_HEADERS })
    fetchAll()
  }

  const timeAgo = (d: string) => {
    const s = Math.floor((Date.now() - new Date(d).getTime()) / 1000)
    if (s < 60) return `${s}s ago`
    if (s < 3600) return `${Math.floor(s/60)}m ago`
    if (s < 86400) return `${Math.floor(s/3600)}h ago`
    return `${Math.floor(s/86400)}d ago`
  }

  if (loading) return (
    <div className="flex justify-center py-16">
      <div className="flex gap-1.5">{[0,1,2].map(i => <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />)}</div>
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Collaboration</h1>
          <p className="mt-1 text-sm text-gray-500">Manage users, shared workspaces, session handoffs, and audit logs</p>
        </div>
        <button onClick={fetchAll} className="px-3 py-1.5 text-xs border border-gray-300 dark:border-gray-600 rounded-lg text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800">Refresh</button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        {([['users', `👥 Users (${users.length})`], ['workspaces', `🗂️ Workspaces (${workspaces.length})`], ['handoffs', `🤝 Handoffs (${handoffs.filter(h=>h.status==='pending').length})`], ['audit', '📋 Audit Log']] as const).map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${tab === t ? 'border-orange-500 text-orange-600 dark:text-orange-400' : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'}`}>
            {label}
          </button>
        ))}
      </div>

      {/* Users */}
      {tab === 'users' && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button onClick={() => setShowNewUser(true)}
              className="flex items-center gap-1.5 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium rounded-lg">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
              Add User
            </button>
          </div>

          {users.length === 0 ? (
            <div className="text-center py-12 text-sm text-gray-400">No users yet. Add a user to enable collaboration.</div>
          ) : (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700 overflow-hidden">
              {users.map(u => (
                <div key={u.id} className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-orange-400 to-red-500 flex items-center justify-center text-white font-bold text-sm flex-shrink-0">
                      {u.display_name.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium text-gray-900 dark:text-white">{u.display_name}</p>
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${ROLE_COLORS[u.role] || 'bg-gray-100 text-gray-600'}`}>{u.role}</span>
                        {!u.is_active && <span className="text-xs text-gray-400">(inactive)</span>}
                        {u.has_github_token && <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-medium">GitHub token set</span>}
                      </div>
                      <p className="text-xs text-gray-400">@{u.username} · joined {timeAgo(u.created_at)}</p>
                      {u.github_token_masked && <p className="text-xs text-gray-400 font-mono mt-0.5">{u.github_token_masked}</p>}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <button onClick={() => openEditUser(u)} className="text-xs text-indigo-500 hover:text-indigo-700">Edit</button>
                    <button onClick={() => deleteUser(u.id, u.display_name)} className="text-xs text-red-400 hover:text-red-600">Remove</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {showNewUser && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
              <div className="w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
                  <h2 className="text-base font-semibold text-gray-900 dark:text-white">Add User</h2>
                  <button onClick={() => setShowNewUser(false)} className="text-gray-400 hover:text-gray-600">✕</button>
                </div>
                <div className="px-6 py-5 space-y-3">
                  <input value={userForm.username} onChange={e => setUserForm(f => ({ ...f, username: e.target.value }))}
                    placeholder="Username" className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
                  <input value={userForm.display_name} onChange={e => setUserForm(f => ({ ...f, display_name: e.target.value }))}
                    placeholder="Display Name" className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
                  <input type="password" value={userForm.password} onChange={e => setUserForm(f => ({ ...f, password: e.target.value }))}
                    placeholder="Password" className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
                  <input type="password" value={userForm.github_token} onChange={e => setUserForm(f => ({ ...f, github_token: e.target.value }))}
                    placeholder="Optional GitHub OAuth / PAT token for Copilot"
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
                  <select value={userForm.role} onChange={e => setUserForm(f => ({ ...f, role: e.target.value }))}
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400">
                    <option value="viewer">Viewer — read only</option>
                    <option value="member">Member — can chat and run agents</option>
                    <option value="admin">Admin — full access except billing</option>
                    <option value="owner">Owner — full access</option>
                  </select>
                </div>
                <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-800 flex gap-3 justify-end">
                  <button onClick={() => setShowNewUser(false)} className="px-4 py-2 text-sm border border-gray-300 rounded-lg text-gray-700">Cancel</button>
                  <button onClick={createUser} disabled={savingUser || !userForm.username.trim() || !userForm.password.trim()}
                    className="px-4 py-2 text-sm bg-orange-500 hover:bg-orange-600 text-white rounded-lg disabled:opacity-40">
                    {savingUser ? 'Adding...' : 'Add User'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {editingUser && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
              <div className="w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
                  <h2 className="text-base font-semibold text-gray-900 dark:text-white">Edit User</h2>
                  <button onClick={() => setEditingUser(null)} className="text-gray-400 hover:text-gray-600">✕</button>
                </div>
                <div className="px-6 py-5 space-y-3">
                  <input value={editForm.display_name} onChange={e => setEditForm(f => ({ ...f, display_name: e.target.value }))}
                    placeholder="Display Name" className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
                  <select value={editForm.role} onChange={e => setEditForm(f => ({ ...f, role: e.target.value }))}
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400">
                    <option value="viewer">Viewer — read only</option>
                    <option value="member">Member — can chat and run agents</option>
                    <option value="admin">Admin — full access except billing</option>
                    <option value="owner">Owner — full access</option>
                  </select>
                  <input type="password" value={editForm.github_token} onChange={e => setEditForm(f => ({ ...f, github_token: e.target.value }))}
                    placeholder="Paste new GitHub OAuth / PAT token, or leave blank to clear"
                    className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
                  {editingUser.github_token_masked && (
                    <p className="text-xs text-gray-400 font-mono">Current token: {editingUser.github_token_masked}</p>
                  )}
                </div>
                <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-800 flex gap-3 justify-end">
                  <button onClick={() => setEditingUser(null)} className="px-4 py-2 text-sm border border-gray-300 rounded-lg text-gray-700">Cancel</button>
                  <button onClick={saveUserEdit} disabled={savingEdit}
                    className="px-4 py-2 text-sm bg-orange-500 hover:bg-orange-600 text-white rounded-lg disabled:opacity-40">
                    {savingEdit ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Workspaces */}
      {tab === 'workspaces' && (
        <div className="space-y-4">
          <div className="flex justify-end">
            <button onClick={() => setShowNewWs(true)}
              className="flex items-center gap-1.5 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium rounded-lg">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
              New Workspace
            </button>
          </div>
          {workspaces.length === 0 ? (
            <div className="text-center py-12 text-sm text-gray-400">No workspaces yet. Create one to share projects with your team.</div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {workspaces.map(w => (
                <div key={w.id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                  <div className="flex items-start justify-between mb-2">
                    <h3 className="font-semibold text-gray-900 dark:text-white">{w.name}</h3>
                    <button onClick={() => deleteWorkspace(w.id)} className="text-xs text-red-400 hover:text-red-600">✕</button>
                  </div>
                  {w.description && <p className="text-sm text-gray-500 mb-2">{w.description}</p>}
                  <div className="flex gap-3 text-xs text-gray-400">
                    <span>{w.project_ids.length} projects</span>
                    <span>{w.member_ids.length} members</span>
                    <span>Created {timeAgo(w.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          {showNewWs && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
              <div className="w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden">
                <div className="px-6 py-4 border-b flex items-center justify-between">
                  <h2 className="font-semibold text-gray-900 dark:text-white">New Workspace</h2>
                  <button onClick={() => setShowNewWs(false)} className="text-gray-400 hover:text-gray-600">✕</button>
                </div>
                <div className="px-6 py-5 space-y-3">
                  <input value={wsForm.name} onChange={e => setWsForm(f => ({ ...f, name: e.target.value }))}
                    placeholder="Workspace name" className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
                  <input value={wsForm.description} onChange={e => setWsForm(f => ({ ...f, description: e.target.value }))}
                    placeholder="Description (optional)" className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
                </div>
                <div className="px-6 py-4 border-t flex gap-3 justify-end">
                  <button onClick={() => setShowNewWs(false)} className="px-4 py-2 text-sm border border-gray-300 rounded-lg text-gray-700">Cancel</button>
                  <button onClick={createWorkspace} disabled={savingWs || !wsForm.name.trim()}
                    className="px-4 py-2 text-sm bg-orange-500 hover:bg-orange-600 text-white rounded-lg disabled:opacity-40">
                    Create
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Handoffs */}
      {tab === 'handoffs' && (
        <div className="space-y-3">
          {handoffs.length === 0 ? (
            <div className="text-center py-12 text-sm text-gray-400">No session handoffs yet.</div>
          ) : (
            handoffs.map(h => (
              <div key={h.id} className={`bg-white dark:bg-gray-800 rounded-xl border p-4 ${h.status === 'pending' ? 'border-orange-200 dark:border-orange-700' : 'border-gray-200 dark:border-gray-700'}`}>
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-gray-900 dark:text-white">{h.from_user} → {h.to_user}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${h.status === 'pending' ? 'bg-orange-100 text-orange-700' : 'bg-green-100 text-green-700'}`}>{h.status}</span>
                    </div>
                    {h.note && <p className="text-sm text-gray-500">{h.note}</p>}
                    <p className="text-xs text-gray-400 mt-1">Conversation: <code className="font-mono">{h.conversation_id.substring(0, 8)}...</code> · {timeAgo(h.created_at)}</p>
                  </div>
                  {h.status === 'pending' && (
                    <button onClick={() => acceptHandoff(h.id)}
                      className="px-3 py-1.5 text-xs bg-green-600 hover:bg-green-700 text-white rounded-lg">Accept</button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Audit Log */}
      {tab === 'audit' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          {audit.length === 0 ? (
            <div className="text-center py-12 text-sm text-gray-400">No audit events yet.</div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {audit.map(e => (
                <div key={e.id} className="flex items-start gap-3 px-4 py-3">
                  <span className="text-xs text-gray-400 font-mono flex-shrink-0 mt-0.5 w-16">{timeAgo(e.ts)}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-mono bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 px-1.5 py-0.5 rounded">{e.action}</span>
                      <span className="text-xs text-gray-500">{e.resource_type}</span>
                      {e.user !== 'system' && <span className="text-xs text-indigo-500">by {e.user}</span>}
                    </div>
                    {e.details && <p className="text-xs text-gray-500 mt-0.5 truncate">{e.details}</p>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
