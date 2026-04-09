'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'
import PreferencesTab from '@/components/PreferencesTab'
import ImageSettingsTab from '@/components/ImageSettingsTab'
import { RemoteAccessTab } from './remote'

import { useState, useEffect, useCallback } from 'react'
import { api } from '@/lib/api'


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

interface ClearImpact {
  provider: string
  affected_models: Array<{ id: string; model_id: string; display_name: string }>
  affected_personas: Array<{ id: string; name: string; slot: string; current_model_id: string }>
  affected_agents: Array<{ id: string; name: string; current_model_id: string }>
  replacement_candidates: Array<{ id: string; model_id: string; display_name: string; provider_name: string }>
  has_references: boolean
}

function ApiKeysTab() {
  const [keys, setKeys] = useState<KeyStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [saved, setSaved] = useState<Record<string, boolean>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [clearImpact, setClearImpact] = useState<ClearImpact | null>(null)
  const [replacements, setReplacements] = useState<Record<string, string>>({})
  const [clearing, setClearing] = useState(false)

  const fetchKeys = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/api-keys`, { headers: AUTH_HEADERS })
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
        headers: AUTH_HEADERS,
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
    // Step 1: fetch impact report — what would happen if we cleared this key?
    const impactRes = await fetch(
      `${API_BASE}/v1/api-keys/${provider}/clear-impact`,
      { headers: AUTH_HEADERS }
    )
    if (!impactRes.ok) {
      alert('Could not check impact of clearing this key.')
      return
    }
    const impact: ClearImpact = await impactRes.json()

    // No references → simple confirm + clear
    if (!impact.has_references) {
      const modelCount = impact.affected_models.length
      const msg = modelCount > 0
        ? `Clear the ${PROVIDER_META[provider]?.label || provider} API key?\n\n${modelCount} model(s) will be deactivated.`
        : `Clear the ${PROVIDER_META[provider]?.label || provider} API key?`
      if (!confirm(msg)) return
      const res = await fetch(`${API_BASE}/v1/api-keys/${provider}`, {
        method: 'DELETE',
        headers: AUTH_HEADERS,
        body: JSON.stringify({}),
      })
      if (res.ok) {
        setKeys(prev => prev.map(k => k.provider === provider ? { ...k, is_set: false, masked_value: null } : k))
      }
      return
    }

    // References exist → show dialog with replacement dropdowns
    setClearImpact(impact)
    setReplacements({})
  }

  const confirmClearWithReplacements = async (useForce: boolean) => {
    if (!clearImpact) return
    setClearing(true)
    try {
      const res = await fetch(`${API_BASE}/v1/api-keys/${clearImpact.provider}`, {
        method: 'DELETE',
        headers: AUTH_HEADERS,
        body: JSON.stringify({
          replacements: useForce ? undefined : replacements,
          force: useForce,
        }),
      })
      if (!res.ok) {
        const err = await res.json()
        alert(err.detail?.message || err.detail || 'Failed to clear key')
        return
      }
      const result = await res.json()
      setKeys(prev => prev.map(k => k.provider === clearImpact.provider ? { ...k, is_set: false, masked_value: null } : k))
      alert(
        `✓ ${PROVIDER_META[clearImpact.provider]?.label} key cleared.\n\n` +
        `Deactivated ${result.deactivated_models} models.\n` +
        `Reassigned ${result.reassigned_personas} personas, ${result.reassigned_agents} agents.`
      )
      setClearImpact(null)
      setReplacements({})
    } finally {
      setClearing(false)
    }
  }

  // OpenRouter OAuth (PKCE) — redirects to OpenRouter, exchanges code for key on return
  const connectOpenRouter = async () => {
    // Generate PKCE code verifier (random 64-char string) + challenge (SHA-256)
    const randomBytes = new Uint8Array(48)
    crypto.getRandomValues(randomBytes)
    const codeVerifier = btoa(String.fromCharCode.apply(null, Array.from(randomBytes)))
      .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')

    const encoder = new TextEncoder()
    const hashBuffer = await crypto.subtle.digest('SHA-256', encoder.encode(codeVerifier))
    const codeChallenge = btoa(String.fromCharCode.apply(null, Array.from(new Uint8Array(hashBuffer))))
      .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')

    sessionStorage.setItem('openrouter_pkce_verifier', codeVerifier)

    const callbackUrl = `${window.location.origin}/auth/openrouter/callback`
    const authUrl = `https://openrouter.ai/auth?callback_url=${encodeURIComponent(callbackUrl)}&code_challenge=${codeChallenge}&code_challenge_method=S256`
    window.location.href = authUrl
  }

  if (loading) return <div className="text-sm text-gray-500 py-8 text-center">Loading keys…</div>

  return (
    <div className="space-y-4">
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
        <strong>🔑 API Keys</strong> are stored in <code className="font-mono bg-amber-100 px-1 rounded">.env</code> and
        loaded into the backend at runtime. Keys are never exposed in full — only the first/last 4 chars are shown.
        Changes take effect immediately (no restart needed).
      </div>
      <div className="bg-purple-50 border border-purple-200 rounded-lg p-4 text-sm text-purple-800">
        <strong>🔗 OpenRouter OAuth</strong> — Click "Connect with OAuth" to authorize via your OpenRouter account
        (no copy/paste needed). OpenRouter proxies GPT-4, Claude, Llama, and many more models through one connection.
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
                  {!isEditing && key.provider === 'openrouter' && (
                    <button
                      onClick={connectOpenRouter}
                      className="text-xs px-2 py-1 rounded border border-purple-300 hover:bg-purple-50 text-purple-700 font-medium">
                      {key.is_set ? 'Reconnect with OAuth' : '🔗 Connect with OAuth'}
                    </button>
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

      {/* Clear-key impact dialog */}
      {clearImpact && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-2xl bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800">
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">
                ⚠️ Clearing {PROVIDER_META[clearImpact.provider]?.label || clearImpact.provider} key will affect other records
              </h2>
              <p className="text-xs text-gray-500 mt-1">
                {clearImpact.affected_models.length} model(s) will be deactivated. Pick replacements for {clearImpact.affected_personas.length + clearImpact.affected_agents.length} reference(s) below.
              </p>
            </div>
            <div className="px-6 py-5 overflow-y-auto flex-1 space-y-5">
              {/* Personas */}
              {clearImpact.affected_personas.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-2">Affected Personas</h3>
                  <div className="space-y-2">
                    {clearImpact.affected_personas.map((p, i) => {
                      const affectedModel = clearImpact.affected_models.find(m => m.id === p.current_model_id)
                      return (
                        <div key={`${p.id}-${p.slot}-${i}`} className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-gray-900 dark:text-white">
                              {p.name} <span className="text-xs text-gray-500 font-normal">({p.slot} model)</span>
                            </span>
                            <span className="text-xs text-gray-500 line-through">{affectedModel?.display_name || affectedModel?.model_id}</span>
                          </div>
                          <select
                            value={replacements[p.current_model_id] || ''}
                            onChange={e => setReplacements(r => ({ ...r, [p.current_model_id]: e.target.value }))}
                            className="w-full rounded-md border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-2 py-1.5 text-xs"
                          >
                            <option value="">— Leave empty (will be set to None) —</option>
                            {clearImpact.replacement_candidates.map(c => (
                              <option key={c.id} value={c.id}>{c.provider_name} / {c.display_name || c.model_id}</option>
                            ))}
                          </select>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Agents */}
              {clearImpact.affected_agents.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-2">Affected Agents</h3>
                  <div className="space-y-2">
                    {clearImpact.affected_agents.map(a => {
                      const affectedModel = clearImpact.affected_models.find(m => m.id === a.current_model_id)
                      return (
                        <div key={a.id} className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-gray-900 dark:text-white">{a.name}</span>
                            <span className="text-xs text-gray-500 line-through">{affectedModel?.display_name || affectedModel?.model_id}</span>
                          </div>
                          <select
                            value={replacements[a.current_model_id] || ''}
                            onChange={e => setReplacements(r => ({ ...r, [a.current_model_id]: e.target.value }))}
                            className="w-full rounded-md border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-2 py-1.5 text-xs"
                          >
                            <option value="">— Leave empty (will be set to None) —</option>
                            {clearImpact.replacement_candidates.map(c => (
                              <option key={c.id} value={c.id}>{c.provider_name} / {c.display_name || c.model_id}</option>
                            ))}
                          </select>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {clearImpact.replacement_candidates.length === 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800">
                  No replacement models available from other providers. You can still clear the key — references will be set to None and you'll need to reassign models manually later.
                </div>
              )}
            </div>
            <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between gap-3">
              <button
                onClick={() => { setClearImpact(null); setReplacements({}) }}
                className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => confirmClearWithReplacements(true)}
                  disabled={clearing}
                  className="px-3 py-2 text-xs font-medium rounded-lg border border-red-300 text-red-600 hover:bg-red-50 disabled:opacity-50"
                >
                  Clear anyway (set refs to None)
                </button>
                <button
                  onClick={() => confirmClearWithReplacements(false)}
                  disabled={clearing}
                  className="px-4 py-2 text-sm font-medium rounded-lg bg-orange-500 hover:bg-orange-600 text-white disabled:bg-gray-300"
                >
                  {clearing ? 'Applying...' : 'Apply Replacements & Clear'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
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

  const [conversations, setConversations] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/v1/conversations?limit=100`, { headers: AUTH_HEADERS })
      .then(r => r.json())
      .then(d => setConversations(d.data || []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const deleteConv = async (id: string) => {
    if (!confirm('Delete this conversation?')) return
    setDeleting(id)
    await fetch(`${API_BASE}/v1/conversations/${id}`, { method: 'DELETE', headers: AUTH_HEADERS })
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

  const [soulContent, setSoulContent] = useState('')
  const [userContent, setUserContent] = useState('')
  const [identityContent, setIdentityContent] = useState('')
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [saved, setSaved] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const [soulRes, userRes, identityRes] = await Promise.all([
          fetch(`${API_BASE}/v1/identity/soul`, { headers: AUTH_HEADERS }).then(r => r.json()),
          fetch(`${API_BASE}/v1/identity/user`, { headers: AUTH_HEADERS }).then(r => r.json()),
          fetch(`${API_BASE}/v1/identity/identity-file`, { headers: AUTH_HEADERS }).then(r => r.json()),
        ])
        setSoulContent(soulRes.content || '')
        setUserContent(userRes.content || '')
        setIdentityContent(identityRes.content || '')
      } catch (e) {
        console.error('Failed to fetch identity files:', e)
      } finally {
        setLoading(false)
      }
    }
    fetchAll()
  }, [])

  const saveFile = async (key: string, url: string, content: string) => {
    setSaving(s => ({ ...s, [key]: true }))
    try {
      await fetch(url, { method: 'PUT', headers: AUTH_HEADERS, body: JSON.stringify({ content }) })
      setSaved(s => ({ ...s, [key]: true }))
      setTimeout(() => setSaved(s => ({ ...s, [key]: false })), 2500)
    } finally {
      setSaving(s => ({ ...s, [key]: false }))
    }
  }

  const resetOnboarding = async () => {
    if (!confirm('This will clear your profile and re-run setup next time you open chat. Continue?')) return
    await fetch(`${API_BASE}/v1/identity/user`, {
      method: 'PUT', headers: AUTH_HEADERS, body: JSON.stringify({ content: '' })
    })
    await fetch(`${API_BASE}/v1/identity/soul`, {
      method: 'PUT', headers: AUTH_HEADERS, body: JSON.stringify({ content: '' })
    })
    setUserContent('')
    setSoulContent('')
    setIdentityContent('')
    alert('Reset complete — refresh the chat page to run setup again.')
  }

  if (loading) return <div className="text-sm text-gray-500 py-8 text-center">Loading...</div>

  const fileCard = (
    key: string,
    title: string,
    description: string,
    hint: string,
    value: string,
    onChange: (v: string) => void,
    saveUrl: string,
    rows: number = 10,
  ) => (
    <div className="bg-white shadow sm:rounded-lg overflow-hidden">
      <div className="px-4 py-5 sm:p-6">
        <div className="flex items-center justify-between mb-1">
          <div>
            <h3 className="text-base font-semibold text-gray-900">{title}</h3>
            <p className="text-xs font-mono text-gray-400 mt-0.5">{hint}</p>
          </div>
          {saved[key] && <span className="text-xs text-green-600 font-medium animate-pulse">Saved!</span>}
        </div>
        <p className="text-sm text-gray-500 mb-3">{description}</p>
        <textarea
          value={value}
          onChange={e => onChange(e.target.value)}
          rows={rows}
          className="block w-full rounded-md border-gray-300 shadow-sm focus:border-orange-500 focus:ring-orange-500 font-mono text-sm"
        />
        <button
          onClick={() => saveFile(key, saveUrl, value)}
          disabled={saving[key]}
          className="mt-3 inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-orange-600 hover:bg-orange-700 disabled:bg-gray-300"
        >
          {saving[key] ? 'Saving...' : `Save`}
        </button>
      </div>
    </div>
  )

  return (
    <div className="space-y-6">

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
        <strong>Tip:</strong> You can also update these from chat using slash commands:{' '}
        <code className="font-mono bg-blue-100 px-1 rounded">/soul</code>,{' '}
        <code className="font-mono bg-blue-100 px-1 rounded">/identity</code>,{' '}
        <code className="font-mono bg-blue-100 px-1 rounded">/user</code>.
        Each starts a guided wizard to walk you through the questions.
      </div>

      {fileCard(
        'soul',
        'AI Soul',
        'Defines your AI\'s personality, tone, and behaviour. Injected as context into every conversation.',
        'data/soul.md',
        soulContent,
        setSoulContent,
        `${API_BASE}/v1/identity/soul`,
        12,
      )}

      {fileCard(
        'identity',
        'AI Identity',
        'Name, creature/role, and vibe tagline. Quick-reference identity card.',
        'data/identity.md',
        identityContent,
        setIdentityContent,
        `${API_BASE}/v1/identity/identity-file`,
        5,
      )}

      {fileCard(
        'user',
        'Your Profile',
        'What the AI knows about you — name, communication style, and primary use. Built during setup, editable anytime.',
        'data/user.md',
        userContent,
        setUserContent,
        `${API_BASE}/v1/identity/user`,
        8,
      )}

      {/* Danger zone */}
      <div className="bg-white shadow sm:rounded-lg overflow-hidden border border-red-100">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-base font-semibold text-red-700 mb-1">Reset Setup</h3>
          <p className="text-sm text-gray-500 mb-3">
            Clears all three identity files. The setup wizard will run again next time you open chat.
          </p>
          <button
            onClick={resetOnboarding}
            className="inline-flex items-center px-4 py-2 border border-red-300 text-sm font-medium rounded-md text-red-600 bg-white hover:bg-red-50"
          >
            Reset Onboarding
          </button>
        </div>
      </div>
    </div>
  )
}
// ─── Server Tab ───────────────────────────────────────────────────────────────
function ServerTab() {
  const [info, setInfo] = useState<any>(null)
  const [health, setHealth] = useState<any>(null)
  const [processes, setProcesses] = useState<any>(null)
  const [logs, setLogs] = useState<{ out: string[]; err: string[] }>({ out: [], err: [] })
  const [logService, setLogService] = useState<'backend' | 'frontend'>('backend')
  const [loading, setLoading] = useState(true)
  const [restarting, setRestarting] = useState(false)
  const [restartMsg, setRestartMsg] = useState('')
  const [actionMsg, setActionMsg] = useState('')
  const [pendingAction, setPendingAction] = useState<string | null>(null)

  const fetchAll = useCallback(async () => {
    try {
      const [infoRes, healthRes, backendStatus] = await Promise.all([
        fetch(`${API_BASE}/v1/system/info`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => null),
        fetch(`${API_BASE}/v1/system/health`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => null),
        fetch('/api/backend').then(r => r.json()).catch(() => null),
      ])
      setInfo(infoRes)
      setHealth(healthRes)
      // Build process list from backend status + assume frontend is running (we're talking to it)
      setProcesses({
        managed: true,
        processes: [
          {
            name: 'devforgeai-backend',
            status: backendStatus?.running ? 'online' : 'stopped',
            pid: backendStatus?.pid ?? null,
            port: 19000,
            memory_mb: null,
            restarts: 0,
          },
          {
            name: 'devforgeai-frontend',
            status: 'online',
            pid: null,
            port: 3001,
            memory_mb: null,
            restarts: 0,
          },
        ]
      })
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchLogs = useCallback(async (service: string) => {
    try {
      const res = await fetch(`${API_BASE}/v1/system/logs?service=${service}&lines=80`, { headers: AUTH_HEADERS })
      const data = await res.json()
      setLogs({ out: data.out || [], err: data.err || [] })
    } catch { setLogs({ out: [], err: [] }) }
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])
  useEffect(() => { fetchLogs(logService) }, [logService, fetchLogs])

  const restart = async () => {
    if (!confirm('Restart the backend server? It will be unavailable for a few seconds.')) return
    setRestarting(true)
    setRestartMsg('Restarting backend…')
    try {
      const res = await fetch('/api/backend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'restart' })
      }).then(r => r.json())
      setRestartMsg(res.ok ? '✅ Back online!' : `⚠️ ${res.message || 'Restart timed out'}`)
    } catch {
      setRestartMsg('⚠️ Restart failed')
    }
    setRestarting(false)
    fetchAll()
  }

  const pmControl = async (action: string, service = 'all') => {
    setActionMsg(`${action}ing…`)
    setPendingAction(action)
    try {
      // Use the Next.js API route — works even when backend is down
      const res = await fetch('/api/backend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: action === 'restart' ? 'restart' : action === 'stop' ? 'stop' : 'start' })
      }).then(r => r.json())
      setTimeout(() => { fetchAll(); setActionMsg(res.ok ? '' : res.message || 'Failed'); setPendingAction(null) }, 2000)
    } catch { setActionMsg('Failed'); setPendingAction(null) }
  }

  const statusColor = (s: string) => s === 'online' ? 'text-green-600' : s === 'stopped' ? 'text-gray-400' : 'text-red-500'
  const statusIcon  = (s: string) => s === 'online' ? '●' : s === 'stopped' ? '○' : '✗'

  if (loading) return <div className="text-sm text-gray-500 py-8 text-center">Loading…</div>

  return (
    <div className="space-y-5">

      {/* PM2 Processes */}
      <div className="bg-white shadow sm:rounded-lg overflow-hidden">
        <div className="px-4 py-4 sm:px-6">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-base font-semibold text-gray-900">Processes</h3>
            <div className="flex gap-2">
              {actionMsg && <span className="text-xs text-gray-500 self-center">{actionMsg}</span>}
              <button onClick={() => pmControl('restart')} className="text-xs px-2.5 py-1 rounded border border-amber-300 text-amber-700 hover:bg-amber-50 disabled:opacity-50" disabled={!!pendingAction}>
                {pendingAction === 'restart' ? <><svg className="animate-spin h-3 w-3 inline mr-1" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>Restarting…</> : '🔄 Restart All'}
              </button>
              <button onClick={() => pmControl('stop')} className="text-xs px-2.5 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50" disabled={!!pendingAction}>
                {pendingAction === 'stop' ? <><svg className="animate-spin h-3 w-3 inline mr-1" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>Stopping…</> : '⏹ Stop All'}
              </button>
              <button onClick={() => pmControl('start', 'ecosystem.config.js')} className="text-xs px-2.5 py-1 rounded border border-green-300 text-green-700 hover:bg-green-50 disabled:opacity-50" disabled={!!pendingAction}>
                {pendingAction === 'start' ? <><svg className="animate-spin h-3 w-3 inline mr-1" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>Starting…</> : '▶ Start All'}
              </button>
              <button onClick={fetchAll} className="text-xs px-2.5 py-1 rounded border border-gray-200 text-gray-500 hover:bg-gray-50">↻</button>
            </div>
          </div>

          {processes?.processes && processes.processes.length > 0 ? (
            <div className="divide-y divide-gray-100">
              {processes.processes.map((p: any) => (
                <div key={p.name} className="flex items-center justify-between py-2.5 text-sm">
                  <div className="flex items-center gap-2">
                    <span className={`text-lg leading-none ${statusColor(p.status)}`}>{statusIcon(p.status)}</span>
                    <div>
                      <p className="font-medium text-gray-900">{p.name}</p>
                      <p className="text-xs text-gray-400">PID {p.pid || '—'} · {p.restarts} restart{p.restarts !== 1 ? 's' : ''}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-gray-500">
                    {p.cpu != null && <span>{p.cpu}% CPU</span>}
                    {p.memory_mb != null && <span>{p.memory_mb} MB</span>}
                    <span className={`font-medium capitalize ${statusColor(p.status)}`}>{p.status}</span>
                    <div className="flex gap-1">
                      <button onClick={() => pmControl('restart', p.name)} className="px-2 py-0.5 rounded border border-amber-200 text-amber-600 hover:bg-amber-50">⟳</button>
                      <button onClick={() => pmControl('stop', p.name)}    className="px-2 py-0.5 rounded border border-gray-200 text-gray-500 hover:bg-gray-50">■</button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-gray-500 py-3">No process info available.</div>
          )}
        </div>
      </div>

      {/* Info + Health side by side */}
      <div className="grid grid-cols-2 gap-5">
        <div className="bg-white shadow sm:rounded-lg overflow-hidden">
          <div className="px-4 py-4 sm:px-6">
            <h3 className="text-base font-semibold text-gray-900 mb-3">Backend Info</h3>
            {info ? (
              <div className="space-y-2 text-sm">
                {([
                  ['Status',  info.status,          'text-green-600'],
                  ['Uptime',  info.uptime,           ''],
                  ['PID',     info.pid,              'font-mono'],
                  ['Python',  info.python_version,   'font-mono'],
                ] as [string, any, string][]).filter(([, val]) => val != null).map(([label, val, cls]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-gray-400">{label}</span>
                    <span className={`font-medium text-gray-800 ${cls}`}>{String(val)}</span>
                  </div>
                ))}
              </div>
            ) : <p className="text-sm text-red-500">⚠️ Backend unreachable</p>}
          </div>
        </div>

        <div className="bg-white shadow sm:rounded-lg overflow-hidden">
          <div className="px-4 py-4 sm:px-6">
            <h3 className="text-base font-semibold text-gray-900 mb-3">Health</h3>
            {health ? (
              <div className="space-y-2 text-sm">
                {Object.entries(health).filter(([,v]) => typeof v !== 'object').map(([k, v]: any) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-gray-400 capitalize">{k.replace(/_/g,' ')}</span>
                    <span className={`font-medium ${String(v).startsWith('healthy')||v===true?'text-green-600':v==='degraded'?'text-amber-500':'text-gray-700'}`}>{String(v)}</span>
                  </div>
                ))}
                {Object.entries(health).filter(([,v]) => v && typeof v === 'object').map(([gk, gv]: any) => (
                  Object.entries(gv).map(([ck, cv]: any) => {
                    const s = String(cv); const ok = s.startsWith('healthy'); const bad = s.startsWith('unhealthy')||s.startsWith('error')
                    const [status, ...rest] = s.split(':'); const detail = rest.join(':').trim()
                    return (
                      <div key={ck} className="flex justify-between">
                        <span className="text-gray-400 capitalize">{ck.replace(/_/g,' ')}</span>
                        <div className="text-right">
                          <span className={`font-medium ${ok?'text-green-600':bad?'text-red-500':'text-amber-500'}`}>{ok?'✓':bad?'✗':'⚠'} {status.trim()}</span>
                          {detail && <p className="text-xs text-gray-400">{detail}</p>}
                        </div>
                      </div>
                    )
                  })
                ))}
              </div>
            ) : <p className="text-sm text-gray-400">—</p>}
          </div>
        </div>
      </div>

      {/* Logs */}
      <div className="bg-white shadow sm:rounded-lg overflow-hidden">
        <div className="px-4 py-4 sm:px-6">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-base font-semibold text-gray-900">Logs</h3>
            <div className="flex gap-2">
              <select value={logService} onChange={e => setLogService(e.target.value as any)}
                className="text-xs border border-gray-300 rounded px-2 py-1 text-gray-600">
                <option value="backend">Backend</option>
                <option value="frontend">Frontend</option>
              </select>
              <button onClick={() => fetchLogs(logService)} className="text-xs px-2.5 py-1 rounded border border-gray-200 text-gray-500 hover:bg-gray-50">↻ Refresh</button>
            </div>
          </div>
          <div className="bg-gray-950 rounded-lg p-3 max-h-64 overflow-y-auto font-mono text-xs text-gray-300 space-y-0.5">
            {[...logs.out, ...logs.err].length > 0
              ? [...logs.out, ...logs.err].map((line, i) => (
                  <div key={i} className={line.toLowerCase().includes('error') || line.toLowerCase().includes('traceback') ? 'text-red-400' : line.toLowerCase().includes('warn') ? 'text-yellow-400' : 'text-gray-300'}>
                    {line}
                  </div>
                ))
              : <span className="text-gray-500">No logs yet — start the app with PM2 to see output here.</span>
            }
          </div>
        </div>
      </div>

      {/* Restart backend worker */}
      <div className="bg-white shadow sm:rounded-lg overflow-hidden border border-amber-100">
        <div className="px-4 py-4 sm:px-6">
          <h3 className="text-base font-semibold text-gray-900 mb-1">Restart Backend Worker</h3>
          <p className="text-sm text-gray-500 mb-3">
            Triggers a graceful worker reload (touches <code className="bg-gray-100 px-1 rounded text-xs">main.py</code>). Useful after editing <code className="bg-gray-100 px-1 rounded text-xs">.env</code>. Use the PM2 controls above to start/stop the entire process.
          </p>
          {restartMsg && (
            <div className={`mb-3 text-sm px-3 py-2 rounded-lg ${restartMsg.startsWith('✅') ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-amber-50 text-amber-700 border border-amber-200'}`}>
              {restartMsg}
            </div>
          )}
          <button onClick={restart} disabled={restarting || !info}
            className="inline-flex items-center gap-2 px-4 py-2 border border-amber-300 text-sm font-medium rounded-md text-amber-700 bg-white hover:bg-amber-50 disabled:opacity-50">
            {restarting ? (
  <><svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/></svg> Restarting…</>
) : (
  <>🔄 Reload Worker</>
)}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function SettingsPage() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [memoryFiles, setMemoryFiles] = useState<MemoryFile[]>([])
  const [loading, setLoading] = useState(true)
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileSaved, setProfileSaved] = useState(false)
  const [activeTab, setActiveTab] = useState<'identity' | 'profile' | 'memory' | 'preferences' | 'conversations' | 'apikeys' | 'remote' | 'images' | 'server'>('identity')

  const saveProfile = async () => {
    if (!profile) return
    setProfileSaving(true)
    try {
      // Save to DB
      await fetch(`${API_BASE}/v1/user`, {
        method: 'PATCH',
        headers: { 'Authorization': 'Bearer modelmesh_local_dev_key', 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: profile.name, email: profile.email })
      })

      // Also update USER.md memory file so the AI knows about the user
      const userMdContent = `# USER.md — About You\n\n## Personal Info\n- Name: ${profile.name || ''}\n- Email: ${profile.email || ''}\n\n## Notes\n- Update this file with more context about yourself via Settings → Identity → Your Profile\n`
      await fetch(`${API_BASE}/v1/identity/user`, {
        method: 'PUT',
        headers: { 'Authorization': 'Bearer modelmesh_local_dev_key', 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: userMdContent })
      })

      setProfileSaved(true)
      setTimeout(() => setProfileSaved(false), 2500)
    } catch (e) {
      console.error('Failed to save profile:', e)
    } finally {
      setProfileSaving(false)
    }
  }
  const [editingFile, setEditingFile] = useState<MemoryFile | null>(null)
  const [newFileName, setNewFileName] = useState('')

  useEffect(() => {
    async function fetchData() {
      try {
        const [profileRes, memoryRes] = await Promise.all([
          fetch(`${API_BASE}/v1/user`, {
            headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
          }).then(r => r.json()),
          fetch(`${API_BASE}/v1/memory`, {
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
      const res = await fetch(`${API_BASE}/v1/memory`, {
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
      await fetch(`${API_BASE}/v1/memory/${file.id}`, {
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
      await fetch(`${API_BASE}/v1/memory/${fileId}`, {
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
        <nav className="-mb-px flex space-x-6 overflow-x-auto">
          {([
            ['identity', 'Identity', 'border-orange-500 text-orange-600'],
            ['profile', 'Profile', 'border-indigo-500 text-indigo-600'],
            ['memory', 'Memory', 'border-indigo-500 text-indigo-600'],
            ['preferences', 'Preferences', 'border-indigo-500 text-indigo-600'],
            ['images', 'Image Generation', 'border-pink-500 text-pink-600'],
            ['conversations', 'Conversations', 'border-indigo-500 text-indigo-600'],
            ['apikeys', 'API Keys', 'border-indigo-500 text-indigo-600'],
            ['remote', '🌐 Remote', 'border-orange-500 text-orange-600'],
            ['server', '⚙️ Server', 'border-gray-500 text-gray-700'],
          ] as const).map(([tab, label, activeClass]) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab as any)}
              className={`flex-shrink-0 py-2 px-1 border-b-2 font-medium text-sm whitespace-nowrap ${
                activeTab === tab
                  ? activeClass
                  : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
              }`}
            >
              {label}
            </button>
          ))}
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
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-lg font-medium text-gray-900">User Profile</h3>
              {profileSaved && <span className="text-sm text-green-600 font-medium animate-pulse">Saved!</span>}
            </div>
            <p className="mt-1 text-sm text-gray-500 mb-4">
              Saved here and synced to your AI's USER.md so it knows who you are.
            </p>
            <div className="space-y-4">
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
              <div className="pt-1">
                <p className="text-xs text-gray-400 mb-3">
                  💡 For richer context (timezone, preferences, projects), use <strong>Settings → Identity → Your Profile</strong> to edit USER.md directly.
                </p>
                <button
                  type="button"
                  onClick={saveProfile}
                  disabled={profileSaving}
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300"
                >
                  {profileSaving ? 'Saving…' : 'Save Profile'}
                </button>
              </div>
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
        <PreferencesTab />
      )}

      {/* Conversations Tab */}
      {activeTab === 'conversations' && (
        <ConversationsTab />
      )}

      {/* Remote Access Tab */}
      {activeTab === 'remote' && (
        <div>
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Remote Access</h2>
            <p className="text-sm text-gray-500 mt-1">Telegram bot, Tailscale, and firewall configuration for remote access.</p>
          </div>
          <RemoteAccessTab />
        </div>
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

      {/* Image Generation Tab */}
      {activeTab === 'images' && (
        <ImageSettingsTab />
      )}

      {/* Server Tab */}
      {activeTab === 'server' && (
        <div>
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-gray-900">Server</h2>
            <p className="text-sm text-gray-500 mt-1">Backend process info, health status, and controls.</p>
          </div>
          <ServerTab />
        </div>
      )}
    </div>
  )
}