'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { useState, useEffect, useRef } from 'react'
import { api } from '@/lib/api'

const AUTH_HEADERS = { 'Authorization': 'Bearer modelmesh_local_dev_key', 'Content-Type': 'application/json' }

interface ValidationResult {
  valid: boolean
  model_id: string
  display_name?: string
  provider: string
  litellm_model: string
  context_window?: number
  max_output_tokens?: number
  cost_per_1m_input?: number
  cost_per_1m_output?: number
  capabilities: Record<string, boolean>
  source: string
  warning?: string
}

interface Model {
  id: string
  model_id: string
  display_name?: string
  provider_id: string
  provider_name?: string
  is_active: boolean
  context_window?: number
  cost_per_1m_input: number
  cost_per_1m_output: number
  capabilities: Record<string, boolean>
}

interface Provider {
  id: string
  name: string
  display_name?: string
}

interface ModelSuggestion {
  model_id: string
  display_name?: string
  context_window?: number
  cost_per_1m_input?: number
  cost_per_1m_output?: number
  capabilities?: Record<string, boolean>
}

function formatCost(cost: number): string {
  if (cost === 0) return 'Free'
  return `$${cost.toFixed(4)}/1M`
}

function formatContext(tokens: number | undefined): string {
  if (!tokens) return 'N/A'
  if (tokens >= 1000000) return `${(tokens / 1000000).toFixed(1)}M`
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(0)}K`
  return tokens.toString()
}

interface SyncStatus {
  ollama: { reachable: boolean; model_count: number; in_db: number }
  providers: Record<string, { key_set: boolean; in_db: number }>
}

export default function ModelsPage() {
  const [models, setModels] = useState<Model[]>([])
  const [providers, setProviders] = useState<Provider[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingModel, setEditingModel] = useState<Model | null>(null)
  const [suggestions, setSuggestions] = useState<ModelSuggestion[]>([])
  const [lookingUp, setLookingUp] = useState(false)
  const [validating, setValidating] = useState(false)
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)
  const validateTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState<string | null>(null)
  const [formData, setFormData] = useState({
    model_id: '',
    display_name: '',
    provider_id: '',
    cost_per_1m_input: 0,
    cost_per_1m_output: 0,
    context_window: 8192,
    capabilities: { streaming: true },
    is_active: true
  })

  const fetchModels = async () => {
    try {
      const [modelsRes, providersRes] = await Promise.all([
        fetch(`${API_BASE}/v1/models`, { headers: AUTH_HEADERS }).then(r => r.json()),
        fetch(`${API_BASE}/v1/providers`, { headers: AUTH_HEADERS }).then(r => r.json()),
      ])
      setModels(modelsRes.data || [])
      setProviders(providersRes.data || [])
    } catch (e) {
      console.error('Failed to fetch models:', e)
    }
  }

  const fetchSyncStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/models/sync/status`, { headers: AUTH_HEADERS })
      if (res.ok) setSyncStatus(await res.json())
    } catch { /* non-fatal */ }
  }

  const runSync = async () => {
    setSyncing(true)
    setSyncResult(null)
    try {
      const res = await fetch(`${API_BASE}/v1/models/sync`, { method: 'POST', headers: AUTH_HEADERS })
      const data = await res.json()
      setSyncResult(data.message || 'Sync complete')
      await fetchModels()
      await fetchSyncStatus()
    } catch (e: any) {
      setSyncResult('Sync failed — check backend logs')
    } finally {
      setSyncing(false)
      setTimeout(() => setSyncResult(null), 5000)
    }
  }

  useEffect(() => {
    async function fetchData() {
      try {
        await fetchModels()
        await fetchSyncStatus()
      } catch (e) {
        console.error('Failed to fetch:', e)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  // Fetch model suggestions when provider changes
  useEffect(() => {
    async function fetchSuggestions() {
      if (!formData.provider_id) {
        setSuggestions([])
        return
      }
      try {
        const provider = providers.find(p => p.id === formData.provider_id)
        if (!provider) return
        
        const res = await fetch(`${API_BASE}/v1/model-lookup/suggestions/${provider.name}`, {
          headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
        })
        if (res.ok) {
          const data = await res.json()
          setSuggestions(data.suggestions || [])
        }
      } catch (e) {
        console.error('Failed to fetch suggestions:', e)
      }
    }
    fetchSuggestions()
  }, [formData.provider_id, providers])

  const handleLookupModel = async () => {
    if (!formData.model_id || !formData.provider_id) {
      alert('Please enter a model ID and select a provider first')
      return
    }
    
    setLookingUp(true)
    try {
      const provider = providers.find(p => p.id === formData.provider_id)
      const res = await fetch(`${API_BASE}/v1/model-lookup/lookup`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer modelmesh_local_dev_key'
        },
        body: JSON.stringify({
          model_id: formData.model_id,
          provider: provider?.name || ''
        })
      })
      
      if (res.ok) {
        const data = await res.json()
        if (data.source !== 'user_input_required') {
          setFormData({
            ...formData,
            display_name: data.display_name || formData.model_id,
            context_window: data.context_window || formData.context_window,
            cost_per_1m_input: data.cost_per_1m_input ?? formData.cost_per_1m_input,
            cost_per_1m_output: data.cost_per_1m_output ?? formData.cost_per_1m_output,
            capabilities: data.capabilities || formData.capabilities
          })
        } else {
          alert('Model not found in database. Please enter the details manually.')
        }
      }
    } catch (e) {
      console.error('Failed to lookup model:', e)
      alert('Failed to lookup model. Please enter details manually.')
    } finally {
      setLookingUp(false)
    }
  }

  const validateModel = async (modelId: string, providerId: string) => {
    const provider = providers.find(p => p.id === providerId)
    if (!modelId.trim() || !provider) {
      setValidation(null)
      setValidationError(null)
      return
    }
    setValidating(true)
    setValidation(null)
    setValidationError(null)
    try {
      const res = await fetch(`${API_BASE}/v1/models/validate`, {
        method: 'POST',
        headers: AUTH_HEADERS,
        body: JSON.stringify({ model_id: modelId.trim(), provider: provider.name }),
      })
      const data: ValidationResult = await res.json()
      setValidation(data)
      if (data.valid) {
        // Auto-fill fields from validated data
        setFormData(prev => ({
          ...prev,
          display_name: prev.display_name || data.display_name || modelId,
          context_window: data.context_window || prev.context_window,
          cost_per_1m_input: data.cost_per_1m_input ?? prev.cost_per_1m_input,
          cost_per_1m_output: data.cost_per_1m_output ?? prev.cost_per_1m_output,
          capabilities: Object.keys(data.capabilities).length > 0 ? data.capabilities : prev.capabilities,
        }))
      }
    } catch (e) {
      setValidationError('Validation request failed')
    } finally {
      setValidating(false)
    }
  }

  // Debounced validation on model_id / provider_id change
  const triggerValidation = (modelId: string, providerId: string) => {
    if (validateTimer.current) clearTimeout(validateTimer.current)
    if (!modelId.trim() || !providerId) { setValidation(null); return }
    validateTimer.current = setTimeout(() => validateModel(modelId, providerId), 600)
  }

  const handleSelectSuggestion = (suggestion: ModelSuggestion) => {
    setFormData({
      ...formData,
      model_id: suggestion.model_id,
      display_name: suggestion.display_name || suggestion.model_id,
      context_window: suggestion.context_window || 8192,
      cost_per_1m_input: suggestion.cost_per_1m_input ?? 0,
      cost_per_1m_output: suggestion.cost_per_1m_output ?? 0,
      capabilities: suggestion.capabilities || { streaming: true }
    })
    setSuggestions([])
  }

  const handleAddModel = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await fetch(`${API_BASE}/v1/models`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer modelmesh_local_dev_key'
        },
        body: JSON.stringify(formData)
      })
      if (res.ok) {
        const newModel = await res.json()
        setModels([...models, newModel])
        setShowAddModal(false)
        setFormData({
          model_id: '',
          display_name: '',
          provider_id: '',
          cost_per_1m_input: 0,
          cost_per_1m_output: 0,
          context_window: 8192,
          capabilities: { streaming: true },
          is_active: true
        })
      }
    } catch (e) {
      console.error('Failed to add model:', e)
    }
  }

  const handleDeleteModel = async (model: Model) => {
    // Check if model is used by personas
    const confirmMessage = model.is_active 
      ? 'Are you sure you want to delete this model? Any personas using it will be updated automatically.'
      : 'Are you sure you want to delete this model?'
    
    if (!confirm(confirmMessage)) return
    
    try {
      const res = await fetch(`${API_BASE}/v1/models/${model.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
      })
      if (res.ok) {
        const data = await res.json()
        setModels(models.filter(m => m.id !== model.id))
        
        // Show affected personas if any
        if (data.affected_personas && data.affected_personas.length > 0) {
          const personaNames = data.affected_personas.map((p: any) => p.name).join(', ')
          alert(`Model deleted. Updated personas: ${personaNames}`)
          
          // Optionally refresh personas list
          // This would require adding personas state and fetch
        }
      }
    } catch (e) {
      console.error('Failed to delete model:', e)
    }
  }

  const handleToggleActive = async (model: Model) => {
    try {
      const res = await fetch(`${API_BASE}/v1/models/${model.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer modelmesh_local_dev_key'
        },
        body: JSON.stringify({ is_active: !model.is_active })
      })
      if (res.ok) {
        setModels(models.map(m => m.id === model.id ? { ...m, is_active: !m.is_active } : m))
      }
    } catch (e) {
      console.error('Failed to toggle model:', e)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-gray-500">Loading...</div>
      </div>
    )
  }

  // Group models by provider
  const grouped = models.reduce((acc, model) => {
    const provider = model.provider_name || 'Unknown'
    if (!acc[provider]) acc[provider] = []
    acc[provider].push(model)
    return acc
  }, {} as Record<string, Model[]>)

  return (
    <div>
      <div className="sm:flex sm:items-center sm:justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Models</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Available AI models from all providers
          </p>
        </div>
        <div className="flex items-center gap-3 mt-4 sm:mt-0">
          <button
            onClick={runSync}
            disabled={syncing}
            className="inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
          >
            <svg className={`-ml-1 mr-2 h-4 w-4 ${syncing ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {syncing ? 'Syncing…' : 'Sync Models'}
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-orange-600 hover:bg-orange-700"
          >
            <svg className="-ml-1 mr-2 h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add Model
          </button>
        </div>
      </div>

      {/* Sync result toast */}
      {syncResult && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700 text-sm text-green-800 dark:text-green-300">
          ✓ {syncResult}
        </div>
      )}

      {/* Sync status banner */}
      {syncStatus && (
        <div className="mb-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {/* Ollama card */}
          <div className={`rounded-lg border p-3 text-sm flex items-start gap-3 ${
            syncStatus.ollama.reachable
              ? 'bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-700'
              : 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
          }`}>
            <span className="text-lg mt-0.5">{syncStatus.ollama.reachable ? '🟢' : '⚪'}</span>
            <div className="flex-1">
              <p className="font-medium text-gray-900 dark:text-white">Ollama</p>
              <p className="text-gray-500 dark:text-gray-400 text-xs">
                {syncStatus.ollama.reachable
                  ? `${syncStatus.ollama.model_count} local models · ${syncStatus.ollama.in_db} in DB`
                  : 'Not running — install Ollama to use local models'}
              </p>
            </div>
          </div>

          {/* Paid provider cards */}
          {Object.entries(syncStatus.providers).map(([name, info]) => (
            <div key={name} className={`rounded-lg border p-3 text-sm flex items-start gap-3 ${
              info.key_set
                ? 'bg-blue-50 dark:bg-blue-900/10 border-blue-200 dark:border-blue-700'
                : 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700 opacity-60'
            }`}>
              <span className="text-lg mt-0.5">{info.key_set ? '🔑' : '🔒'}</span>
              <div className="flex-1">
                <p className="font-medium text-gray-900 dark:text-white capitalize">{name}</p>
                <p className="text-gray-500 dark:text-gray-400 text-xs">
                  {info.key_set
                    ? `API key set · ${info.in_db} models in DB`
                    : 'No API key — add one in Settings → API Keys'}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {Object.entries(grouped).map(([provider, providerModels]) => (
        <div key={provider} className="mb-8">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4 capitalize">{provider}</h2>
          <div className="bg-white dark:bg-gray-800 shadow overflow-hidden sm:rounded-lg">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Model
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Context
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Input Cost
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Output Cost
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Capabilities
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {providerModels.map((model) => (
                  <tr key={model.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-gray-900 dark:text-white">
                        {model.display_name || model.model_id}
                      </div>
                      <div className="text-sm text-gray-500 dark:text-gray-400">{model.model_id}</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="text-sm text-gray-900 dark:text-white">
                        {formatContext(model.context_window)} tokens
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                      {formatCost(model.cost_per_1m_input)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                      {formatCost(model.cost_per_1m_output)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(model.capabilities || {}).map(([key, value]) => (
                          value && (
                            <span
                              key={key}
                              className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200"
                            >
                              {key}
                            </span>
                          )
                        ))}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <button
                        onClick={() => handleToggleActive(model)}
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          model.is_active
                            ? 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200'
                            : 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200'
                        }`}
                      >
                        {model.is_active ? 'Active' : 'Inactive'}
                      </button>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <button
                        onClick={() => handleDeleteModel(model)}
                        className="text-red-600 hover:text-red-900 dark:text-red-400 dark:hover:text-red-300"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {models.length === 0 && (
        <div className="text-center py-12">
          <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 15v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
          </svg>
          <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-white">No models</h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Add models to get started.
          </p>
        </div>
      )}

      {/* Add Model Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-gray-500 bg-opacity-75 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-lg w-full max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Add Model</h3>
            <form onSubmit={handleAddModel} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Provider *</label>
                <select
                  required
                  value={formData.provider_id}
                  onChange={(e) => {
                    const newProviderId = e.target.value
                    setFormData(prev => ({ ...prev, provider_id: newProviderId }))
                    setValidation(null)
                    triggerValidation(formData.model_id, newProviderId)
                  }}
                  className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-orange-500 focus:ring-orange-500 sm:text-sm"
                >
                  <option value="">Select a provider</option>
                  {providers.map((p) => (
                    <option key={p.id} value={p.id}>{p.display_name || p.name}</option>
                  ))}
                </select>
              </div>
              
              {suggestions.length > 0 && (
                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Quick Add</label>
                  <div className="flex flex-wrap gap-2">
                    {suggestions.map((s) => (
                      <button
                        key={s.model_id}
                        type="button"
                        onClick={() => handleSelectSuggestion(s)}
                        className="px-3 py-1.5 text-xs bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600"
                      >
                        {s.display_name || s.model_id}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Model ID *</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    required
                    value={formData.model_id}
                    onChange={(e) => {
                      const newId = e.target.value
                      setFormData(prev => ({ ...prev, model_id: newId }))
                      triggerValidation(newId, formData.provider_id)
                    }}
                    className={`mt-1 flex-1 block w-full rounded-md shadow-sm focus:ring-orange-500 sm:text-sm
                      ${validation
                        ? validation.valid
                          ? 'border-green-400 focus:border-green-500'
                          : 'border-red-400 focus:border-red-500'
                        : 'border-gray-300 dark:border-gray-600 focus:border-orange-500'
                      } dark:bg-gray-700 dark:text-white`}
                    placeholder="e.g., claude-3-5-haiku-20241022"
                  />
                  <button
                    type="button"
                    onClick={() => validateModel(formData.model_id, formData.provider_id)}
                    disabled={validating || !formData.model_id || !formData.provider_id}
                    className="mt-1 px-3 py-2 text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                  >
                    {validating ? '⟳ Checking…' : 'Validate'}
                  </button>
                </div>

                {/* Validation status */}
                {validating && (
                  <p className="mt-1 text-xs text-gray-400 animate-pulse">Validating model with provider…</p>
                )}
                {validationError && (
                  <p className="mt-1 text-xs text-red-500">{validationError}</p>
                )}
                {validation && (
                  <div className={`mt-2 rounded-md p-3 text-sm border ${
                    validation.valid
                      ? 'bg-green-50 border-green-200 dark:bg-green-900/20 dark:border-green-700'
                      : 'bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-700'
                  }`}>
                    <div className="flex items-center gap-2 font-medium">
                      <span>{validation.valid ? '✅' : '❌'}</span>
                      <span className={validation.valid ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}>
                        {validation.valid ? 'Valid model' : 'Model not found'}
                      </span>
                      <span className="text-xs font-normal text-gray-400">via {validation.source}</span>
                    </div>
                    {validation.valid && (
                      <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-600 dark:text-gray-300">
                        {validation.context_window && (
                          <span>Context: <strong>{(validation.context_window / 1000).toFixed(0)}K tokens</strong></span>
                        )}
                        {validation.cost_per_1m_input !== undefined && (
                          <span>Input: <strong>${validation.cost_per_1m_input}/1M</strong></span>
                        )}
                        {validation.max_output_tokens && (
                          <span>Max output: <strong>{(validation.max_output_tokens / 1000).toFixed(0)}K</strong></span>
                        )}
                        {validation.cost_per_1m_output !== undefined && (
                          <span>Output: <strong>${validation.cost_per_1m_output}/1M</strong></span>
                        )}
                        {Object.keys(validation.capabilities).length > 0 && (
                          <span className="col-span-2">
                            Caps: <strong>{Object.keys(validation.capabilities).join(', ')}</strong>
                          </span>
                        )}
                        <span className="col-span-2 text-gray-400 italic">↑ Fields auto-filled above</span>
                      </div>
                    )}
                    {validation.warning && (
                      <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">⚠ {validation.warning}</p>
                    )}
                    {!validation.valid && (
                      <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                        This model ID was not recognized by {validation.provider}. Check the ID and try again.
                      </p>
                    )}
                  </div>
                )}
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Display Name</label>
                <input
                  type="text"
                  value={formData.display_name}
                  onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                  className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-orange-500 focus:ring-orange-500 sm:text-sm"
                  placeholder="e.g., GPT-4 Turbo"
                />
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Input Cost ($/1M)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={formData.cost_per_1m_input}
                    onChange={(e) => setFormData({ ...formData, cost_per_1m_input: parseFloat(e.target.value) || 0 })}
                    className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-orange-500 focus:ring-orange-500 sm:text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Output Cost ($/1M)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={formData.cost_per_1m_output}
                    onChange={(e) => setFormData({ ...formData, cost_per_1m_output: parseFloat(e.target.value) || 0 })}
                    className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-orange-500 focus:ring-orange-500 sm:text-sm"
                  />
                </div>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Context Window (tokens)</label>
                <input
                  type="number"
                  value={formData.context_window}
                  onChange={(e) => setFormData({ ...formData, context_window: parseInt(e.target.value) || 8192 })}
                    className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-orange-500 focus:ring-orange-500 sm:text-sm"
                />
              </div>
              
              <div className="flex justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => { setShowAddModal(false); setValidation(null); setValidationError(null) }}
                  className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-orange-600 hover:bg-orange-700"
                >
                  Add Model
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}