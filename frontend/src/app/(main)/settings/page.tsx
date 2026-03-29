'use client'

import { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/api'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:19000'
const AUTH = { 'Authorization': 'Bearer modelmesh_local_dev_key', 'Content-Type': 'application/json' }

const PROVIDER_META: Record<string, { label: string; placeholder: string; link: string; color: string }> = {
  anthropic:  { label: 'Anthropic',  placeholder: 'sk-ant-…',        link: 'https://console.anthropic.com/settings/keys',    color: 'bg-orange-100 text-orange-800' },
  google:     { label: 'Google',     placeholder: 'AIzaSy…',         link: 'https://aistudio.google.com/app/apikey',          color: 'bg-blue-100 text-blue-800' },
  gemini:     { label: 'Gemini',     placeholder: 'AIzaSy…',         link: 'https://aistudio.google.com/app/apikey',          color: 'bg-blue-100 text-blue-800' },
  openrouter: { label: 'OpenRouter', placeholder: 'sk-or-v1-…',      link: 'https://openrouter.ai/keys',                      color: 'bg-purple-100 text-purple-800' },
  openai:     { label: 'OpenAI',     placeholder: 'sk-…',            link: 'https://platform.openai.com/api-keys',            color: 'bg-green-100 text-green-800' },
}

interface KeyStatus {
  provider: string
  env_var: string
  is_set: boolean
  masked_value: string | null
}

function ApiKeysTab() {
  const [keys, setKeys] = useState<KeyStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [saved, setSaved] = useState<Record<string, boolean>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})

  const fetchKeys = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/api-keys`, { headers: AUTH })
      const data = await res.json()
      setKeys(data.data || [])
    } catch (e) {
      console.error('Failed to fetch keys', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchKeys() }, [fetchKeys])

  const saveKey = async (provider: string) => {
    const value = editing[provider]?.trim()
    if (!value) return
    setSaving(s => ({ ...s, [provider]: true }))
    setErrors(e => ({ ...e, [provider]: '' }))
    try {
      const res = await fetch(`${API_BASE}/v1/api-keys/${provider}`, {
        method: 'PUT',
        headers: AUTH,
        body: JSON.stringify({ value }),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Save failed')
      }
      const updated = await res.json()
      setKeys(prev => prev.map(k => k.provider === provider
        ? { ...k, is_set: true, masked_value: updated.masked_value }
        : k
      ))
      setEditing(e => { const n = { ...e }; delete n[provider]; return n })
      setSaved(s => ({ ...s, [provider]: true }))
      setTimeout(() => setSaved(s => ({ ...s, [provider]: false })), 2500)
    } catch (e: any) {
      setErrors(err => ({ ...err, [provider]: e.message }))
    } finally {
      setSaving(s => ({ ...s, [provider]: false }))
    }
  }

  const clearKey = async (provider: string) => {
    if (!confirm(`Clear the ${PROVIDER_META[provider]?.label || provider} API key?`)) return
    await fetch(`${API_BASE}/v1/api-keys/${provider}`, { method: 'DELETE', headers: AUTH })
    setKeys(prev => prev.map(k => k.provider === provider ? { ...k, is_set: false, masked_value: null } : k))
  }

  if (loading) return <div className="text-sm text-gray-500 py-8 text-center">Loading keys…</div>

  return (
    <div className="space-y-4">
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
        <strong>🔑 API Keys</strong> are stored in <code className="font-mono bg-amber-100 px-1 rounded">.env</code> and
        loaded into the backend at runtime. Keys are never exposed in full — only the first/last 4 chars are shown.
        Changes take effect immediately (no restart needed).
      </div>

      {keys.map((key) => {
        const meta = PROVIDER_META[key.provider]
        const isEditing = key.provider in editing
        return (
          <div key={key.provider} className="bg-white shadow sm:rounded-lg overflow-hidden">
            <div className="px-4 py-4 sm:px-6">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-3">
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${meta?.color || 'bg-gray-100 text-gray-800'}`}>
                    {meta?.label || key.provider}
                  </span>
                  <code className="text-xs text-gray-400 font-mono">{key.env_var}</code>
                  {key.is_set
                    ? <span className="text-xs text-green-600 font-medium">✓ Set</span>
                    : <span className="text-xs text-red-500 font-medium">✗ Not set</span>
                  }
                  {saved[key.provider] && <span className="text-xs text-green-600 animate-pulse">Saved!</span>}
                </div>
                <div className="flex items-center gap-2">
                  {meta?.link && (
                    <a href={meta.link} target="_blank" rel="noreferrer"
                      className="text-xs text-indigo-500 hover:text-indigo-700 underline">
                      Get key ↗
                    </a>
                  )}
                  {!isEditing && (
                    <button
                      onClick={() => setEditing(e => ({ ...e, [key.provider]: '' }))}
                      className="text-xs px-2 py-1 rounded border border-gray-200 hover:bg-gray-50 text-gray-600">
                      {key.is_set ? 'Update' : 'Set Key'}
                    </button>
                  )}
                  {key.is_set && !isEditing && (
                    <button onClick={() => clearKey(key.provider)}
                      className="text-xs px-2 py-1 rounded border border-red-200 hover:bg-red-50 text-red-500">
                      Clear
                    </button>
                  )}
                </div>
              </div>

              {key.is_set && !isEditing && (
                <div className="mt-2 font-mono text-sm text-gray-500">{key.masked_value}</div>
              )}

              {isEditing && (
                <div className="mt-3 space-y-2">
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder={meta?.placeholder || 'Paste your API key…'}
                    value={editing[key.provider] || ''}
                    onChange={e => setEditing(prev => ({ ...prev, [key.provider]: e.target.value }))}
                    onKeyDown={e => e.key === 'Enter' && saveKey(key.provider)}
                    className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 font-mono text-sm"
                  />
                  {errors[key.provider] && (
                    <p className="text-xs text-red-500">{errors[key.provider]}</p>
                  )}
                  <div className="flex gap-2">
                    <button
                      onClick={() => saveKey(key.provider)}
                      disabled={saving[key.provider] || !editing[key.provider]?.trim()}
                      className="px-3 py-1.5 text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300">
                      {saving[key.provider] ? 'Saving…' : 'Save'}
                    </button>
                    <button
                      onClick={() => setEditing(e => { const n = { ...e }; delete n[key.provider]; return n })}
                      className="px-3 py-1.5 text-sm font-medium rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50">
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

interface MemoryFile {
  id: string
  name: string
  content: string
  description?: string
  created_at: string
  updated_at: string
}

interface UserProfile {
  id: string
  name: string
  email?: string
  preferences: Record<string, any>
}



// ─── Conversations Tab ────────────────────────────────────────────────────────
function ConversationsTab() {
  const API_BASE = 'http://localhost:19000'
  const AUTH = { 'Authorization': 'Bearer modelmesh_local_dev_key', 'Content-Type': 'application/json' }

  const [conversations, setConversations] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/v1/conversations?limit=100`, { headers: AUTH })
      .then(r => r.json())
      .then(d => setConversations(d.data || []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const deleteConv = async (id: string) => {
    if (!confirm('Delete this conversation?')) return
    setDeleting(id)
    await fetch(`${API_BASE}/v1/conversations/${id}`, { method: 'DELETE', headers: AUTH })
    setConversations(prev => prev.filter(c => c.id !== id))
    setDeleting(null)
  }

  const timeAgo = (d: string) => {
    const s = Math.floor((Date.now() - new Date(d).getTime()) / 1000)
    if (s < 60) return `${s}s ago`
    if (s < 3600) return `${Math.floor(s/60)}m ago`
    if (s < 86400) return `${Math.floor(s/3600)}h ago`
    return `${Math.floor(s/86400)}d ago`
  }

  if (loading) return <div className="text-sm text-gray-500 py-8 text-center">Loading...</div>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">{conversations.length} conversation{conversations.length !== 1 ? 's' : ''}</p>
        <a href="/chat" className="text-sm text-orange-600 hover:text-orange-700 font-medium">Open Chat →</a>
      </div>
      {conversations.length === 0 ? (
        <div className="text-center py-12 text-sm text-gray-400">No conversations yet.</div>
      ) : (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg divide-y divide-gray-100 dark:divide-gray-700 overflow-hidden">
          {conversations.map(c => (
            <div key={c.id} className="flex items-center justify-between px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-800 dark:text-white truncate">{c.title || 'Untitled conversation'}</p>
                <p className="text-xs text-gray-400 mt-0.5">
                  {timeAgo(c.last_message_at || c.created_at)}
                  {c.message_count > 0 && ` · ${c.message_count} messages`}
                  {c.pinned && ' · 📌'}
                  {c.keep_forever && ' · 🔒'}
                </p>
              </div>
              <div className="flex items-center gap-2 ml-4 flex-shrink-0">
                <a
                  href={`/chat?session=${c.id}`}
                  className="text-xs text-indigo-500 hover:text-indigo-700"
                >
                  Open
                </a>
                <button
                  onClick={() => deleteConv(c.id)}
                  disabled={deleting === c.id}
                  className="text-xs text-red-400 hover:text-red-600 disabled:opacity-40"
                >
                  {deleting === c.id ? '...' : 'Delete'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
// ─── Identity Tab ─────────────────────────────────────────────────────────────
function IdentityTab() {
  const API_BASE = 'http://localhost:19000'
  const AUTH = { 'Authorization': 'Bearer modelmesh_local_dev_key', 'Content-Type': 'application/json' }

  const [soulContent, setSoulContent] = useState('')
  const [userContent, setUserContent] = useState('')
  const [savingSoul, setSavingSoul] = useState(false)
  const [savingUser, setSavingUser] = useState(false)
  const [soulSaved, setSoulSaved] = useState(false)
  const [userSaved, setUserSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchBoth = async () => {
      try {
        const [soulRes, userRes] = await Promise.all([
          fetch(`${API_BASE}/v1/identity/soul`, { headers: AUTH }).then(r => r.json()),
          fetch(`${API_BASE}/v1/identity/user`, { headers: AUTH }).then(r => r.json()),
        ])
        setSoulContent(soulRes.content || '')
        setUserContent(userRes.content || '')
      } catch (e) {
        console.error('Failed to fetch identity files:', e)
      } finally {
        setLoading(false)
      }
    }
    fetchBoth()
  }, [])

  const saveSoul = async () => {
    setSavingSoul(true)
    try {
      await fetch(`${API_BASE}/v1/identity/soul`, {
        method: 'PUT', headers: AUTH, body: JSON.stringify({ content: soulContent })
      })
      setSoulSaved(true)
      setTimeout(() => setSoulSaved(false), 2500)
    } finally { setSavingSoul(false) }
  }

  const saveUser = async () => {
    setSavingUser(true)
    try {
      await fetch(`${API_BASE}/v1/identity/user`, {
        method: 'PUT', headers: AUTH, body: JSON.stringify({ content: userContent })
      })
      setUserSaved(true)
      setTimeout(() => setUserSaved(false), 2500)
    } finally { setSavingUser(false) }
  }

  const resetOnboarding = async () => {
    await fetch(`${API_BASE}/v1/identity/user`, {
      method: 'PUT', headers: AUTH, body: JSON.stringify({ content: '' })
    })
    setUserContent('')
    alert('Onboarding reset — refresh the chat page to run setup again.')
  }

  if (loading) return <div className="text-sm text-gray-500 py-8 text-center">Loading...</div>

  return (
    <div className="space-y-6">
      {/* Soul */}
      <div className="bg-white shadow sm:rounded-lg overflow-hidden">
        <div className="px-4 py-5 sm:p-6">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-base font-semibold text-gray-900">AI Soul (SOUL.md)</h3>
            {soulSaved && <span className="text-xs text-green-600 font-medium animate-pulse">Saved!</span>}
          </div>
          <p className="text-sm text-gray-500 mb-3">Defines your AI personality. Injected as context into every conversation.</p>
          <textarea
            value={soulContent}
            onChange={e => setSoulContent(e.target.value)}
            rows={12}
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-orange-500 focus:ring-orange-500 font-mono text-sm"
          />
          <button
            onClick={saveSoul}
            disabled={savingSoul}
            className="mt-3 inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-orange-600 hover:bg-orange-700 disabled:bg-gray-300"
          >
            {savingSoul ? 'Saving...' : 'Save Soul'}
          </button>
        </div>
      </div>

      {/* User profile */}
      <div className="bg-white shadow sm:rounded-lg overflow-hidden">
        <div className="px-4 py-5 sm:p-6">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-base font-semibold text-gray-900">Your Profile (USER.md)</h3>
            {userSaved && <span className="text-xs text-green-600 font-medium animate-pulse">Saved!</span>}
          </div>
          <p className="text-sm text-gray-500 mb-3">What the AI knows about you. Built during onboarding, editable anytime.</p>
          <textarea
            value={userContent}
            onChange={e => setUserContent(e.target.value)}
            rows={8}
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-orange-500 focus:ring-orange-500 font-mono text-sm"
          />
          <div className="mt-3 flex gap-3">
            <button
              onClick={saveUser}
              disabled={savingUser}
              className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-orange-600 hover:bg-orange-700 disabled:bg-gray-300"
            >
              {savingUser ? 'Saving...' : 'Save Profile'}
            </button>
            <button
              onClick={resetOnboarding}
              className="inline-flex items-center px-4 py-2 border border-red-300 text-sm font-medium rounded-md text-red-600 bg-white hover:bg-red-50"
            >
              Reset Onboarding
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
export default function SettingsPage() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [memoryFiles, setMemoryFiles] = useState<MemoryFile[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'identity' | 'profile' | 'memory' | 'preferences' | 'conversations' | 'apikeys'>('identity')
  const [editingFile, setEditingFile] = useState<MemoryFile | null>(null)
  const [newFileName, setNewFileName] = useState('')

  useEffect(() => {
    async function fetchData() {
      try {
        const [profileRes, memoryRes] = await Promise.all([
          fetch('http://localhost:19000/v1/user', {
            headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
          }).then(r => r.json()),
          fetch('http://localhost:19000/v1/memory', {
            headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
          }).then(r => r.json())
        ])
        setProfile(profileRes)
        setMemoryFiles(memoryRes.data || [])
      } catch (e) {
        console.error('Failed to fetch:', e)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  const createMemoryFile = async (name: string) => {
    try {
      const res = await fetch('http://localhost:19000/v1/memory', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer modelmesh_local_dev_key'
        },
        body: JSON.stringify({ name, content: '# ' + name + '\n\nAdd your content here...' })
      })
      const newFile = await res.json()
      setMemoryFiles([...memoryFiles, newFile])
      setNewFileName('')
    } catch (e) {
      console.error('Failed to create:', e)
    }
  }

  const updateMemoryFile = async (file: MemoryFile) => {
    try {
      await fetch(`http://localhost:19000/v1/memory/${file.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer modelmesh_local_dev_key'
        },
        body: JSON.stringify({ content: file.content })
      })
      setEditingFile(null)
    } catch (e) {
      console.error('Failed to update:', e)
    }
  }

  const deleteMemoryFile = async (fileId: string) => {
    try {
      await fetch(`http://localhost:19000/v1/memory/${fileId}`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
      })
      setMemoryFiles(memoryFiles.filter(f => f.id !== fileId))
    } catch (e) {
      console.error('Failed to delete:', e)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-gray-500">Loading...</div>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage your profile, memory files, and preferences
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('profile')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'profile'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Profile
          </button>
          <button
            onClick={() => setActiveTab('memory')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'memory'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Memory Files
          </button>
          <button
            onClick={() => setActiveTab('preferences')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'preferences'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Preferences
          </button>
          <button
            onClick={() => setActiveTab('apikeys')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'apikeys'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            API Keys
          </button>
        </nav>
      </div>

      {/* Identity Tab */}
      {activeTab === 'identity' && (
        <div>
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-900">Identity</h2>
            <p className="text-sm text-gray-500 mt-1">Manage your AI's personality and your personal profile.</p>
          </div>
          <IdentityTab />
        </div>
      )}

      {/* Profile Tab */}
      {activeTab === 'profile' && (
        <div className="bg-white shadow sm:rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <h3 className="text-lg font-medium text-gray-900">User Profile</h3>
            <p className="mt-1 text-sm text-gray-500">
              This information helps personalize your AI interactions.
            </p>
            <div className="mt-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Name</label>
                <input
                  type="text"
                  value={profile?.name || ''}
                  onChange={(e) => setProfile({ ...profile!, name: e.target.value })}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Email</label>
                <input
                  type="email"
                  value={profile?.email || ''}
                  onChange={(e) => setProfile({ ...profile!, email: e.target.value })}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                />
              </div>
              <button
                type="button"
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700"
              >
                Save Profile
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Memory Files Tab */}
      {activeTab === 'memory' && (
        <div className="space-y-6">
          <div className="bg-white shadow sm:rounded-lg">
            <div className="px-4 py-5 sm:p-6">
              <h3 className="text-lg font-medium text-gray-900">Memory Files</h3>
              <p className="mt-1 text-sm text-gray-500">
                Memory files are injected into AI system prompts to provide context and personalization.
              </p>

              {/* Create new file */}
              <div className="mt-4 flex gap-2">
                <input
                  type="text"
                  placeholder="New file name (e.g., USER.md, CONTEXT.md)"
                  value={newFileName}
                  onChange={(e) => setNewFileName(e.target.value)}
                  className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                />
                <button
                  onClick={() => newFileName && createMemoryFile(newFileName)}
                  disabled={!newFileName}
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300"
                >
                  Create
                </button>
              </div>
            </div>
          </div>

          {/* Memory files list */}
          {memoryFiles.map((file) => (
            <div key={file.id} className="bg-white shadow sm:rounded-lg">
              <div className="px-4 py-5 sm:p-6">
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="text-sm font-medium text-gray-900">{file.name}</h4>
                    {file.description && (
                      <p className="text-sm text-gray-500">{file.description}</p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setEditingFile(file)}
                      className="text-sm text-indigo-600 hover:text-indigo-500"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => deleteMemoryFile(file.id)}
                      className="text-sm text-red-600 hover:text-red-500"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {editingFile?.id === file.id ? (
                  <div className="mt-4">
                    <textarea
                      value={file.content}
                      onChange={(e) => {
                        const updated = memoryFiles.map(f => 
                          f.id === file.id ? { ...f, content: e.target.value } : f
                        )
                        setMemoryFiles(updated)
                      }}
                      rows={10}
                      className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 font-mono text-sm"
                    />
                    <div className="mt-2 flex gap-2">
                      <button
                        onClick={() => updateMemoryFile(file)}
                        className="inline-flex items-center px-3 py-1.5 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700"
                      >
                        Save
                      </button>
                      <button
                        onClick={() => setEditingFile(null)}
                        className="inline-flex items-center px-3 py-1.5 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <pre className="mt-2 text-sm text-gray-600 whitespace-pre-wrap line-clamp-3">
                    {file.content}
                  </pre>
                )}
              </div>
            </div>
          ))}

          {memoryFiles.length === 0 && (
            <div className="text-center py-8">
              <p className="text-sm text-gray-500">No memory files yet. Create one to personalize your AI interactions.</p>
            </div>
          )}
        </div>
      )}

      {/* Preferences Tab */}
      {activeTab === 'preferences' && (
        <div className="bg-white shadow sm:rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <h3 className="text-lg font-medium text-gray-900">Learned Preferences</h3>
            <p className="mt-1 text-sm text-gray-500">
              These preferences are learned from your chat interactions.
            </p>
            <div className="mt-4 text-sm text-gray-500">
              Preferences will appear here as you interact with the AI.
            </div>
          </div>
        </div>
      )}

      {/* Conversations Tab */}
      {activeTab === 'conversations' && (
        <ConversationsTab />
      )}

      {/* API Keys Tab */}
      {activeTab === 'apikeys' && (
        <div>
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-900">API Keys</h2>
            <p className="text-sm text-gray-500 mt-1">Manage provider API keys. Changes are applied immediately.</p>
          </div>
          <ApiKeysTab />
        </div>
      )}
    </div>
  )
}