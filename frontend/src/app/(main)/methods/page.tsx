'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'
import { getApiBase, getAuthHeaders } from '@/lib/config'

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'


interface Method {
  id: string; name: string; tagline: string; icon: string; color: string
  description: string; system_prompt: string; phases: string[]
  settings: Record<string, any>; is_active: boolean
  in_stack: boolean; stack_position: number | null
}

interface CustomMethod {
  id: string
  name: string
  description: string
  phases: { name: string; prompt: string; default_model?: string; depends_on?: string[] }[]
  created_at?: string
  updated_at?: string
}

const COLOR_MAP: Record<string, { border: string; bg: string; badge: string; btn: string; addBtn: string; phase: string }> = {
  gray:   { border: 'border-gray-300',   bg: 'bg-gray-50 dark:bg-gray-800/50',        badge: 'bg-gray-100 text-gray-700',          btn: 'bg-gray-700 hover:bg-gray-800 text-white',           addBtn: 'border-gray-300 text-gray-600 hover:bg-gray-50',         phase: 'bg-gray-100 text-gray-600' },
  purple: { border: 'border-purple-400', bg: 'bg-purple-50 dark:bg-purple-900/20',    badge: 'bg-purple-100 text-purple-700',       btn: 'bg-purple-600 hover:bg-purple-700 text-white',       addBtn: 'border-purple-300 text-purple-600 hover:bg-purple-50',   phase: 'bg-purple-100 text-purple-700' },
  orange: { border: 'border-orange-400', bg: 'bg-orange-50 dark:bg-orange-900/20',    badge: 'bg-orange-100 text-orange-700',       btn: 'bg-orange-500 hover:bg-orange-600 text-white',       addBtn: 'border-orange-300 text-orange-600 hover:bg-orange-50',   phase: 'bg-orange-100 text-orange-700' },
  blue:   { border: 'border-blue-400',   bg: 'bg-blue-50 dark:bg-blue-900/20',        badge: 'bg-blue-100 text-blue-700',           btn: 'bg-blue-600 hover:bg-blue-700 text-white',           addBtn: 'border-blue-300 text-blue-600 hover:bg-blue-50',         phase: 'bg-blue-100 text-blue-700' },
  green:  { border: 'border-green-400',  bg: 'bg-green-50 dark:bg-green-900/20',      badge: 'bg-green-100 text-green-700',         btn: 'bg-green-600 hover:bg-green-700 text-white',         addBtn: 'border-green-300 text-green-600 hover:bg-green-50',      phase: 'bg-green-100 text-green-700' },
}

export default function MethodsPage() {
  const [methods, setMethods] = useState<Method[]>([])
  const [customMethods, setCustomMethods] = useState<CustomMethod[]>([])
  const [activeId, setActiveId] = useState('standard')
  const [stack, setStack] = useState<string[]>([])
  const [conflicts, setConflicts] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [expandedPrompt, setExpandedPrompt] = useState<string | null>(null)
  const [expandedCustom, setExpandedCustom] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null)
  const [editingMethod, setEditingMethod] = useState<CustomMethod | null>(null)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [importError, setImportError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const fetchMethods = useCallback(async () => {
    const res = await fetch(`${API_BASE}/v1/methods/`, { headers: AUTH_HEADERS })
      .then(r => r.json()).catch(() => ({ data: [], active_method: 'standard', active_stack: [] }))
    setMethods(res.data || [])
    setActiveId(res.active_method || 'standard')
    setStack(res.active_stack || [])
    setConflicts(res.conflicts || [])
    setLoading(false)
  }, [])

  const fetchCustomMethods = useCallback(async () => {
    const res = await fetch(`${getApiBase()}/v1/methods/custom`, { headers: getAuthHeaders() })
      .then(r => r.ok ? r.json() : []).catch(() => [])
    setCustomMethods(Array.isArray(res) ? res : res.data || [])
  }, [])

  useEffect(() => { fetchMethods(); fetchCustomMethods() }, [fetchMethods, fetchCustomMethods])

  const activate = async (id: string) => {
    if (working) return
    setWorking(true)
    const res = await fetch(`${API_BASE}/v1/methods/activate`, {
      method: 'POST', headers: AUTH_HEADERS, body: JSON.stringify({ method_id: id })
    }).then(r => r.json())
    setActiveId(res.active_method)
    setStack(res.active_stack || [])
    setConflicts([])
    setMethods(prev => prev.map(m => ({
      ...m,
      is_active: m.id === id,
      in_stack: res.active_stack?.includes(m.id) || false,
      stack_position: res.active_stack?.indexOf(m.id) >= 0 ? res.active_stack.indexOf(m.id) + 1 : null
    })))
    setWorking(false)
  }

  const addToStack = async (id: string) => {
    if (working) return
    setWorking(true)
    const res = await fetch(`${API_BASE}/v1/methods/stack/add`, {
      method: 'POST', headers: AUTH_HEADERS, body: JSON.stringify({ method_id: id })
    }).then(r => r.json())
    setStack(res.active_stack || [])
    setConflicts(res.conflicts || [])
    setMethods(prev => prev.map(m => ({
      ...m,
      in_stack: res.active_stack?.includes(m.id) || false,
      stack_position: res.active_stack?.indexOf(m.id) >= 0 ? res.active_stack.indexOf(m.id) + 1 : null
    })))
    setWorking(false)
  }

  const removeFromStack = async (id: string) => {
    if (working) return
    setWorking(true)
    const res = await fetch(`${API_BASE}/v1/methods/stack/remove`, {
      method: 'POST', headers: AUTH_HEADERS, body: JSON.stringify({ method_id: id })
    }).then(r => r.json())
    setStack(res.active_stack || [])
    setConflicts([])
    setActiveId(res.active_stack?.[0] || 'standard')
    setMethods(prev => prev.map(m => ({
      ...m,
      in_stack: res.active_stack?.includes(m.id) || false,
      stack_position: res.active_stack?.indexOf(m.id) >= 0 ? res.active_stack.indexOf(m.id) + 1 : null
    })))
    setWorking(false)
  }

  const clearStack = async () => {
    if (working) return
    setWorking(true)
    await fetch(`${API_BASE}/v1/methods/stack`, { method: 'DELETE', headers: AUTH_HEADERS })
    setStack([])
    setActiveId('standard')
    setConflicts([])
    setMethods(prev => prev.map(m => ({ ...m, is_active: m.id === 'standard', in_stack: false, stack_position: null })))
    setWorking(false)
  }

  const deleteCustomMethod = async (id: string) => {
    setWorking(true)
    await fetch(`${getApiBase()}/v1/methods/custom/${encodeURIComponent(id)}`, {
      method: 'DELETE', headers: getAuthHeaders()
    })
    setDeleteConfirm(null)
    await fetchCustomMethods()
    setWorking(false)
  }

  const saveEditMethod = async () => {
    if (!editingMethod) return
    setWorking(true)
    await fetch(`${getApiBase()}/v1/methods/custom/${encodeURIComponent(editingMethod.id)}`, {
      method: 'PUT',
      headers: getAuthHeaders(),
      body: JSON.stringify({ name: editName, description: editDescription })
    })
    setEditingMethod(null)
    await fetchCustomMethods()
    setWorking(false)
  }

  const exportMethod = async (id: string) => {
    const res = await fetch(`${getApiBase()}/v1/methods/custom/${encodeURIComponent(id)}/export`, {
      headers: getAuthHeaders()
    })
    if (!res.ok) return
    const data = await res.json()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `method-${id}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const importMethod = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImportError(null)
    try {
      const text = await file.text()
      const json = JSON.parse(text)
      const res = await fetch(`${getApiBase()}/v1/methods/custom/import`, {
        method: 'POST', headers: getAuthHeaders(), body: JSON.stringify(json)
      })
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}))
        throw new Error(detail.detail || `Import failed (${res.status})`)
      }
      await fetchCustomMethods()
    } catch (err: any) {
      setImportError(err.message || 'Failed to import method')
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const stackMethods = methods.filter(m => stack.includes(m.id)).sort((a, b) => (a.stack_position || 0) - (b.stack_position || 0))
  const isStackMode = stack.length > 1

  const query = searchQuery.toLowerCase().trim()
  const filteredBuiltIn = useMemo(() => {
    if (!query) return methods.filter(m => m.id !== 'standard')
    return methods.filter(m => m.id !== 'standard' && (
      m.name.toLowerCase().includes(query) ||
      m.tagline?.toLowerCase().includes(query) ||
      m.description?.toLowerCase().includes(query) ||
      m.phases?.some(p => p.toLowerCase().includes(query))
    ))
  }, [methods, query])

  const filteredCustom = useMemo(() => {
    if (!query) return customMethods
    return customMethods.filter(m =>
      m.name.toLowerCase().includes(query) ||
      m.description?.toLowerCase().includes(query) ||
      m.phases?.some(p => p.name.toLowerCase().includes(query))
    )
  }, [customMethods, query])

  if (loading) return (
    <div className="flex justify-center py-16">
      <div className="flex gap-1.5">{[0,1,2].map(i => <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />)}</div>
    </div>
  )

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Development Methods</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Choose how the AI approaches your work. Activate one method or build a stack — methods combine their system prompts in order.
          </p>
        </div>
      </div>

      {/* Search bar */}
      <div className="relative">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">🔍</span>
        <input
          type="text"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          placeholder="Search methods by name or keyword…"
          className="w-full pl-9 pr-4 py-2.5 text-sm rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent"
        />
        {searchQuery && (
          <button onClick={() => setSearchQuery('')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-sm">✕</button>
        )}
      </div>

      {/* Active stack display */}
      {stack.length > 0 && (
        <div className="rounded-xl border-2 border-purple-300 bg-purple-50 dark:bg-purple-900/20 p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-lg">🔀</span>
              <span className="text-sm font-semibold text-gray-900 dark:text-white">
                {isStackMode ? 'Method Stack Active' : `${stackMethods[0]?.name} Active`}
              </span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300 font-medium">
                {stack.length} method{stack.length > 1 ? 's' : ''}
              </span>
            </div>
            <button onClick={clearStack} disabled={working}
              className="text-xs text-gray-500 hover:text-gray-700 border border-gray-300 dark:border-gray-600 px-2.5 py-1 rounded-lg disabled:opacity-40">
              Reset to Standard
            </button>
          </div>

          {/* Stack order visualization */}
          <div className="flex items-center gap-2 flex-wrap">
            {stackMethods.map((m, i) => {
              const colors = COLOR_MAP[m.color] || COLOR_MAP.gray
              return (
                <div key={m.id} className="flex items-center gap-1.5">
                  {i > 0 && <span className="text-gray-400 text-xs font-bold">+</span>}
                  <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full border ${colors.border} ${colors.bg}`}>
                    <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">{i + 1}.</span>
                    <span className="text-base">{m.icon}</span>
                    <span className="text-sm font-medium text-gray-800 dark:text-white">{m.name}</span>
                    <button onClick={() => removeFromStack(m.id)} disabled={working}
                      className="ml-1 text-gray-400 hover:text-red-500 transition-colors disabled:opacity-40 text-xs">✕</button>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Conflict warnings */}
          {conflicts.length > 0 && (
            <div className="mt-3 space-y-1">
              {conflicts.map((w, i) => (
                <p key={i} className="text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 px-3 py-1.5 rounded-lg border border-amber-200 dark:border-amber-700">
                  {w}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Built-in Methods */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
          <span>📦</span> Built-in Methods
          <span className="text-xs font-normal text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded-full">
            {filteredBuiltIn.length} method{filteredBuiltIn.length !== 1 ? 's' : ''}
          </span>
        </h2>

        {filteredBuiltIn.length === 0 && query ? (
          <p className="text-sm text-gray-400 italic py-4 text-center">No built-in methods match &quot;{searchQuery}&quot;</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {filteredBuiltIn.map(m => {
              const colors = COLOR_MAP[m.color] || COLOR_MAP.gray
              const inStack = stack.includes(m.id)
              return (
                <div key={m.id} className={`rounded-2xl border-2 overflow-hidden transition-all ${
                  inStack ? `${colors.border} ${colors.bg}` : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
                }`}>
                  <div className="p-5">
                    {/* Header */}
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <span className="text-3xl">{m.icon}</span>
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="font-bold text-gray-900 dark:text-white">{m.name}</h3>
                            {inStack && (
                              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${colors.badge}`}>
                                {isStackMode ? `Stack #${m.stack_position}` : 'Active'}
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-gray-500 dark:text-gray-400">{m.tagline}</p>
                        </div>
                      </div>
                    </div>

                    <p className="text-sm text-gray-600 dark:text-gray-300 mb-3">{m.description}</p>

                    {m.phases.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mb-3">
                        {m.phases.map((phase, i) => (
                          <span key={phase} className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${colors.phase}`}>
                            <span className="text-gray-400 font-normal">{i + 1}.</span> {phase}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex items-center gap-2 flex-wrap">
                      {!inStack ? (
                        <>
                          <button onClick={() => activate(m.id)} disabled={working}
                            className={`px-3 py-1.5 text-sm font-medium rounded-xl transition-colors disabled:opacity-50 ${colors.btn}`}>
                            Activate
                          </button>
                          <button onClick={() => addToStack(m.id)} disabled={working}
                            className={`px-3 py-1.5 text-sm font-medium rounded-xl border transition-colors disabled:opacity-50 ${colors.addBtn}`}>
                            + Add to Stack
                          </button>
                        </>
                      ) : (
                        <button onClick={() => removeFromStack(m.id)} disabled={working}
                          className="px-3 py-1.5 text-sm font-medium rounded-xl border border-red-200 text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50">
                          Remove from Stack
                        </button>
                      )}
                      {m.system_prompt && (
                        <button onClick={() => setExpandedPrompt(expandedPrompt === m.id ? null : m.id)}
                          className="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700 border border-gray-200 dark:border-gray-700 rounded-xl">
                          {expandedPrompt === m.id ? 'Hide' : 'View prompt'}
                        </button>
                      )}
                    </div>

                    {expandedPrompt === m.id && (
                      <div className="mt-4 bg-gray-900 rounded-xl p-4 overflow-auto max-h-64">
                        <pre className="text-xs text-green-400 whitespace-pre-wrap font-mono">{m.system_prompt}</pre>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Standard option */}
      <div className={`rounded-xl border p-4 flex items-center justify-between ${
        stack.length === 0 ? 'border-gray-300 bg-gray-50 dark:bg-gray-800/50' : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800'
      }`}>
        <div className="flex items-center gap-3">
          <span className="text-2xl">💬</span>
          <div>
            <p className="text-sm font-semibold text-gray-900 dark:text-white">
              Standard
              {stack.length === 0 && <span className="ml-2 text-xs font-normal text-gray-500 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded-full">Active</span>}
            </p>
            <p className="text-xs text-gray-500">Default — no method injection. AI responds naturally.</p>
          </div>
        </div>
        {stack.length > 0 && (
          <button onClick={clearStack} disabled={working}
            className="px-3 py-1.5 text-sm font-medium rounded-xl bg-gray-700 hover:bg-gray-800 text-white transition-colors disabled:opacity-50">
            Reset to Standard
          </button>
        )}
      </div>

      {/* Custom Methods */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <span>🛠️</span> Custom Methods
            <span className="text-xs font-normal text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded-full">
              {filteredCustom.length} method{filteredCustom.length !== 1 ? 's' : ''}
            </span>
          </h2>
          <div className="flex items-center gap-2">
            <input ref={fileInputRef} type="file" accept=".json" onChange={importMethod} className="hidden" />
            <button onClick={() => fileInputRef.current?.click()} disabled={working}
              className="px-3 py-1.5 text-sm font-medium rounded-xl border border-blue-300 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors disabled:opacity-50">
              ⬆ Import JSON
            </button>
          </div>
        </div>

        {importError && (
          <div className="mb-3 text-sm text-red-600 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-xl px-4 py-2 flex items-center justify-between">
            <span>{importError}</span>
            <button onClick={() => setImportError(null)} className="text-red-400 hover:text-red-600 ml-2">✕</button>
          </div>
        )}

        {filteredCustom.length === 0 ? (
          <div className="text-center py-8 border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-2xl">
            <p className="text-sm text-gray-400">
              {query ? `No custom methods match "${searchQuery}"` : 'No custom methods yet. Use the Workflow Builder to create one, or import a JSON file.'}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredCustom.map(cm => {
              const isExpanded = expandedCustom === cm.id
              const isDeleting = deleteConfirm === cm.id
              const isEditing = editingMethod?.id === cm.id
              return (
                <div key={cm.id} className="rounded-2xl border-2 border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden transition-all">
                  <div className="p-5">
                    {/* Header row */}
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="text-2xl shrink-0">⚙️</span>
                        <div className="min-w-0">
                          {isEditing ? (
                            <input value={editName} onChange={e => setEditName(e.target.value)}
                              className="text-sm font-bold rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 px-2 py-1 text-gray-900 dark:text-white w-full focus:outline-none focus:ring-2 focus:ring-orange-400" />
                          ) : (
                            <h3 className="font-bold text-gray-900 dark:text-white truncate">{cm.name}</h3>
                          )}
                          <p className="text-xs text-gray-400">{cm.phases?.length || 0} phase{(cm.phases?.length || 0) !== 1 ? 's' : ''}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button onClick={() => {
                          if (isEditing) { saveEditMethod() } else {
                            setEditingMethod(cm); setEditName(cm.name); setEditDescription(cm.description || '')
                          }
                        }} disabled={working}
                          className="px-2.5 py-1.5 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50">
                          {isEditing ? '💾 Save' : '✏️ Edit'}
                        </button>
                        {isEditing && (
                          <button onClick={() => setEditingMethod(null)}
                            className="px-2.5 py-1.5 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-600 text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                            Cancel
                          </button>
                        )}
                        <button onClick={() => exportMethod(cm.id)} disabled={working}
                          className="px-2.5 py-1.5 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50">
                          ⬇ Export
                        </button>
                        {isDeleting ? (
                          <div className="flex items-center gap-1">
                            <button onClick={() => deleteCustomMethod(cm.id)} disabled={working}
                              className="px-2.5 py-1.5 text-xs font-medium rounded-lg bg-red-600 text-white hover:bg-red-700 transition-colors disabled:opacity-50">
                              Confirm
                            </button>
                            <button onClick={() => setDeleteConfirm(null)}
                              className="px-2.5 py-1.5 text-xs font-medium rounded-lg border border-gray-300 dark:border-gray-600 text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button onClick={() => setDeleteConfirm(cm.id)} disabled={working}
                            className="px-2.5 py-1.5 text-xs font-medium rounded-lg border border-red-200 dark:border-red-700 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50">
                            🗑 Delete
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Description */}
                    {isEditing ? (
                      <textarea value={editDescription} onChange={e => setEditDescription(e.target.value)} rows={2}
                        className="mt-2 w-full text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 px-3 py-2 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-orange-400" />
                    ) : cm.description ? (
                      <p className="text-sm text-gray-600 dark:text-gray-300 mt-2">{cm.description}</p>
                    ) : null}

                    {/* Expand/collapse detail */}
                    <button onClick={() => setExpandedCustom(isExpanded ? null : cm.id)}
                      className="mt-3 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
                      {isExpanded ? '▼ Hide details' : '▶ Show phases, dependencies & model defaults'}
                    </button>

                    {/* Expanded detail */}
                    {isExpanded && cm.phases && cm.phases.length > 0 && (
                      <div className="mt-3 border-t border-gray-100 dark:border-gray-700 pt-3 space-y-2">
                        {cm.phases.map((phase, i) => (
                          <div key={i} className="rounded-xl bg-gray-50 dark:bg-gray-700/50 p-3">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-sm font-medium text-gray-800 dark:text-gray-200">
                                <span className="text-gray-400 mr-1">{i + 1}.</span> {phase.name}
                              </span>
                              {phase.default_model && (
                                <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-mono">
                                  {phase.default_model}
                                </span>
                              )}
                            </div>
                            {phase.depends_on && phase.depends_on.length > 0 && (
                              <p className="text-xs text-gray-400 mt-1">
                                Depends on: {phase.depends_on.map((d, di) => (
                                  <span key={di} className="inline-block px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 mr-1">{d}</span>
                                ))}
                              </p>
                            )}
                            {phase.prompt && (
                              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">{phase.prompt}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-xl p-4 text-sm text-amber-800 dark:text-amber-300">
        <strong>How stacking works:</strong> Each method&apos;s system prompt is concatenated in order, separated by a divider. The AI follows all active method guidelines simultaneously. Some combos are complementary (BMAD + GTrack), others may conflict (BMAD + GSD) — you&apos;ll see a warning but can still run them. Changes take effect on your next message.
      </div>
    </div>
  )
}
