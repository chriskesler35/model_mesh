'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { useState, useEffect, useCallback } from 'react'


interface Preference {
  id: string
  key: string
  value: string
  category: string
  source: string
  is_active: boolean
  created_at: string
  updated_at: string
}

const CATEGORY_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
  general:       { icon: '⚙️',  color: 'bg-gray-100 text-gray-700 border-gray-200',     label: 'General' },
  coding:        { icon: '💻', color: 'bg-blue-50 text-blue-700 border-blue-200',       label: 'Coding' },
  communication: { icon: '💬', color: 'bg-purple-50 text-purple-700 border-purple-200', label: 'Communication' },
  ui:            { icon: '🎨', color: 'bg-pink-50 text-pink-700 border-pink-200',       label: 'UI' },
  workflow:      { icon: '🔄', color: 'bg-green-50 text-green-700 border-green-200',    label: 'Workflow' },
}

function CategoryBadge({ category }: { category: string }) {
  const cfg = CATEGORY_CONFIG[category] || CATEGORY_CONFIG.general
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${cfg.color}`}>
      {cfg.icon} {cfg.label}
    </span>
  )
}

export default function PreferencesTab() {
  const [prefs, setPrefs] = useState<Preference[]>([])
  const [loading, setLoading] = useState(true)
  const [showInactive, setShowInactive] = useState(false)
  const [adding, setAdding] = useState(false)
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')
  const [newCategory, setNewCategory] = useState('general')
  const [saving, setSaving] = useState(false)
  const [detecting, setDetecting] = useState(false)
  const [filter, setFilter] = useState<string>('all')

  const fetchPrefs = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_BASE}/v1/preferences?include_inactive=${showInactive}`,
        { headers: AUTH_HEADERS }
      )
      const data = await res.json()
      setPrefs(data.data || [])
    } catch (e) {
      console.error('Failed to fetch preferences:', e)
    } finally {
      setLoading(false)
    }
  }, [showInactive])

  useEffect(() => { fetchPrefs() }, [fetchPrefs])

  const addPref = async () => {
    if (!newKey.trim() || !newValue.trim()) return
    setSaving(true)
    try {
      const res = await fetch(`${API_BASE}/v1/preferences`, {
        method: 'POST', headers: AUTH_HEADERS,
        body: JSON.stringify({ key: newKey.trim(), value: newValue.trim(), category: newCategory, source: 'manual' }),
      })
      const pref = await res.json()
      setPrefs(prev => [pref, ...prev])
      setNewKey('')
      setNewValue('')
      setNewCategory('general')
      setAdding(false)
    } finally {
      setSaving(false)
    }
  }

  const togglePref = async (id: string, active: boolean) => {
    await fetch(`${API_BASE}/v1/preferences/${id}`, {
      method: 'PATCH', headers: AUTH_HEADERS,
      body: JSON.stringify({ is_active: active }),
    })
    setPrefs(prev => prev.map(p => p.id === id ? { ...p, is_active: active } : p))
  }

  const deletePref = async (id: string) => {
    if (!confirm('Delete this preference?')) return
    await fetch(`${API_BASE}/v1/preferences/${id}`, { method: 'DELETE', headers: AUTH_HEADERS })
    setPrefs(prev => prev.filter(p => p.id !== id))
  }

  const runDetection = async () => {
    setDetecting(true)
    try {
      // Fetch last 20 messages from most recent conversation
      const convsRes = await fetch(`${API_BASE}/v1/conversations?limit=1`, { headers: AUTH_HEADERS }).then(r => r.json())
      const convs = convsRes.data || []
      if (convs.length === 0) {
        alert('No conversations found to analyze.')
        return
      }
      const convId = convs[0].id
      const msgsRes = await fetch(`${API_BASE}/v1/conversations/${convId}/messages?limit=20`, { headers: AUTH_HEADERS }).then(r => r.json())
      const messages = (msgsRes.data || []).map((m: any) => ({ role: m.role, content: m.content }))

      if (messages.length < 2) {
        alert('Not enough messages to analyze.')
        return
      }

      const res = await fetch(`${API_BASE}/v1/preferences/detect`, {
        method: 'POST', headers: AUTH_HEADERS,
        body: JSON.stringify({ messages }),
      })
      const result = await res.json()

      if (result.error) {
        alert(`Detection error: ${result.error}`)
      } else if (result.saved === 0) {
        alert(`Analyzed conversation — no new preferences found.${result.detected?.length > 0 ? ` (${result.detected.length} already known)` : ''}`)
      } else {
        fetchPrefs()
        alert(`Found and saved ${result.saved} new preference(s)!`)
      }
    } catch (e: any) {
      alert(`Detection failed: ${e.message}`)
    } finally {
      setDetecting(false)
    }
  }

  const filtered = filter === 'all' ? prefs : prefs.filter(p => p.category === filter)
  const categories = ['all', ...Object.keys(CATEGORY_CONFIG)]

  if (loading) {
    return (
      <div className="flex justify-center py-12">
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
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Learned Preferences</h2>
          <p className="text-sm text-gray-500 mt-1">
            Preferences detected from your conversations and manually added. These shape how the AI responds to you.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={() => setShowInactive(s => !s)}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
              showInactive ? 'bg-gray-100 border-gray-300 text-gray-700' : 'border-gray-200 text-gray-500 hover:bg-gray-50'
            }`}
          >
            {showInactive ? '👁 Showing inactive' : '👁 Active only'}
          </button>
          <button
            onClick={runDetection}
            disabled={detecting}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-purple-200 text-purple-600 hover:bg-purple-50 transition-colors disabled:opacity-50"
          >
            {detecting ? (
              <>
                <span className="w-3 h-3 border-2 border-purple-300 border-t-purple-600 rounded-full animate-spin" />
                Analyzing...
              </>
            ) : (
              <>🔍 Detect from Chat</>
            )}
          </button>
          <button
            onClick={() => setAdding(true)}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-orange-500 hover:bg-orange-600 text-white text-xs font-medium rounded-lg transition-colors"
          >
            + Add
          </button>
        </div>
      </div>

      {/* Add form */}
      {adding && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-orange-200 dark:border-orange-700 p-5 space-y-3">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Add Preference</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <input
              value={newKey}
              onChange={e => setNewKey(e.target.value)}
              placeholder="Key (e.g. prefers_dark_mode)"
              className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm focus:ring-orange-400 focus:border-orange-400"
            />
            <input
              value={newValue}
              onChange={e => setNewValue(e.target.value)}
              placeholder="Description (e.g. Always use dark mode)"
              className="sm:col-span-2 rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm focus:ring-orange-400 focus:border-orange-400"
            />
          </div>
          <div className="flex items-center gap-3">
            <select
              value={newCategory}
              onChange={e => setNewCategory(e.target.value)}
              className="rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm"
            >
              {Object.entries(CATEGORY_CONFIG).map(([k, v]) => (
                <option key={k} value={k}>{v.icon} {v.label}</option>
              ))}
            </select>
            <div className="flex-1" />
            <button onClick={() => setAdding(false)}
              className="px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50">
              Cancel
            </button>
            <button onClick={addPref} disabled={!newKey.trim() || !newValue.trim() || saving}
              className="px-4 py-1.5 text-xs font-medium rounded-lg bg-orange-500 hover:bg-orange-600 text-white disabled:opacity-40 transition-colors">
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>
      )}

      {/* Category filter */}
      <div className="flex items-center gap-1 overflow-x-auto">
        {categories.map(cat => {
          const cfg = CATEGORY_CONFIG[cat]
          const count = cat === 'all' ? prefs.length : prefs.filter(p => p.category === cat).length
          return (
            <button
              key={cat}
              onClick={() => setFilter(cat)}
              className={`flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-full border transition-colors whitespace-nowrap ${
                filter === cat
                  ? 'bg-orange-50 border-orange-300 text-orange-700 dark:bg-orange-900/20 dark:border-orange-600 dark:text-orange-400'
                  : 'border-gray-200 dark:border-gray-700 text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
            >
              {cfg?.icon || '📋'} {cat === 'all' ? 'All' : cfg?.label || cat}
              {count > 0 && (
                <span className={`ml-0.5 text-xs px-1 py-0 rounded-full ${
                  filter === cat ? 'bg-orange-200 dark:bg-orange-800' : 'bg-gray-100 dark:bg-gray-700'
                }`}>
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Preferences list */}
      {filtered.length === 0 ? (
        <div className="text-center py-12 bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
          <div className="text-4xl mb-3">🧠</div>
          <h3 className="text-sm font-medium text-gray-900 dark:text-white">
            {prefs.length === 0 ? 'No preferences yet' : `No ${filter} preferences`}
          </h3>
          <p className="text-sm text-gray-500 mt-1">
            {prefs.length === 0
              ? 'Preferences will be detected as you chat, or add them manually.'
              : 'Try a different category filter.'}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(pref => (
            <div
              key={pref.id}
              className={`bg-white dark:bg-gray-800 rounded-xl border px-5 py-4 flex items-start gap-4 transition-all ${
                pref.is_active
                  ? 'border-gray-200 dark:border-gray-700'
                  : 'border-gray-100 dark:border-gray-800 opacity-50'
              }`}
            >
              {/* Toggle */}
              <button
                onClick={() => togglePref(pref.id, !pref.is_active)}
                className={`mt-0.5 w-9 h-5 rounded-full transition-colors flex-shrink-0 relative ${
                  pref.is_active ? 'bg-green-400' : 'bg-gray-300'
                }`}
              >
                <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                  pref.is_active ? 'left-4' : 'left-0.5'
                }`} />
              </button>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-gray-900 dark:text-white font-mono">
                    {pref.key}
                  </span>
                  <CategoryBadge category={pref.category} />
                  {pref.source === 'detected' && (
                    <span className="text-xs text-purple-500 font-medium">🔍 auto-detected</span>
                  )}
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-0.5">{pref.value}</p>
                <p className="text-xs text-gray-400 mt-1">
                  Added {new Date(pref.created_at).toLocaleDateString()}
                  {pref.updated_at !== pref.created_at && ` · Updated ${new Date(pref.updated_at).toLocaleDateString()}`}
                </p>
              </div>

              {/* Delete */}
              <button
                onClick={() => deletePref(pref.id)}
                className="p-1.5 rounded-lg text-gray-300 hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors flex-shrink-0"
                title="Delete preference"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Info footer */}
      <div className="bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-gray-200 dark:border-gray-700 px-5 py-4">
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">How it works</h4>
        <ul className="text-xs text-gray-500 space-y-1">
          <li>🔍 <strong>Auto-detection:</strong> Every 10 messages, the AI scans for preferences in your conversation</li>
          <li>✏️ <strong>Manual:</strong> Add preferences explicitly using the + Add button</li>
          <li>🔄 <strong>Toggle:</strong> Disable a preference without deleting it — the AI won't use it until re-enabled</li>
          <li>🧠 <strong>Usage:</strong> Active preferences are injected into the AI's context for every chat</li>
        </ul>
      </div>
    </div>
  )
}
