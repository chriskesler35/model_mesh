'use client'

import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'

interface Model {
  id: string
  model_id: string
  display_name?: string
  provider_name?: string
}

interface Persona {
  id?: string
  name: string
  description?: string
  system_prompt?: string
  primary_model_id?: string
  fallback_model_id?: string
  routing_rules?: {
    max_cost?: number
    prefer_local?: boolean
    auto_route?: boolean
    classifier_persona_id?: string
  }
  memory_enabled?: boolean
  max_memory_messages?: number
  is_default?: boolean
}

export default function PersonaForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const personaId = searchParams.get('id')
  const [models, setModels] = useState<Model[]>([])
  const [persona, setPersona] = useState<Persona>({
    name: '',
    description: '',
    system_prompt: 'You are a helpful AI assistant.',
    memory_enabled: true,
    max_memory_messages: 10,
    routing_rules: {
      max_cost: 0.10,
      prefer_local: false,
      auto_route: false
    }
  })
  const [loading, setLoading] = useState(!!personaId)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    async function fetchData() {
      try {
        const modelsRes = await fetch('http://localhost:19000/v1/models', {
          headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
        })
        const modelsData = await modelsRes.json()
        setModels(modelsData.data || [])

        if (personaId) {
          const personaRes = await fetch(`http://localhost:19000/v1/personas/${personaId}`, {
            headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
          })
          const personaData = await personaRes.json()
          setPersona(personaData)
        }
      } catch (e) {
        console.error('Failed to fetch:', e)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [personaId])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)

    try {
      const url = personaId 
        ? `http://localhost:19000/v1/personas/${personaId}`
        : 'http://localhost:19000/v1/personas'
      const method = personaId ? 'PATCH' : 'POST'

      const res = await fetch(url, {
        method,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer modelmesh_local_dev_key'
        },
        body: JSON.stringify(persona)
      })

      if (res.ok) {
        router.push('/personas')
      } else {
        console.error('Failed to save:', await res.text())
      }
    } catch (e) {
      console.error('Failed to save:', e)
    } finally {
      setSaving(false)
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
    <form onSubmit={handleSubmit} className="space-y-8">
      {/* Basic Info */}
      <div className="bg-white shadow sm:rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-lg font-medium text-gray-900">Basic Information</h3>
          <div className="mt-4 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Name *</label>
              <input
                type="text"
                required
                value={persona.name}
                onChange={(e) => setPersona({ ...persona, name: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                placeholder="e.g., python-architect"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Description</label>
              <input
                type="text"
                value={persona.description || ''}
                onChange={(e) => setPersona({ ...persona, description: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                placeholder="Short description of this persona"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">System Prompt</label>
              <textarea
                rows={4}
                value={persona.system_prompt || ''}
                onChange={(e) => setPersona({ ...persona, system_prompt: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm font-mono"
                placeholder="You are a helpful assistant..."
              />
            </div>
          </div>
        </div>
      </div>

      {/* Model Selection */}
      <div className="bg-white shadow sm:rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-lg font-medium text-gray-900">Model Selection</h3>
          <div className="mt-4 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Primary Model</label>
              <select
                value={persona.primary_model_id || ''}
                onChange={(e) => setPersona({ ...persona, primary_model_id: e.target.value || undefined })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
              >
                <option value="">Select a model</option>
                {models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.display_name || model.model_id} ({model.provider_name})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Fallback Model</label>
              <select
                value={persona.fallback_model_id || ''}
                onChange={(e) => setPersona({ ...persona, fallback_model_id: e.target.value || undefined })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
              >
                <option value="">No fallback</option>
                {models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.display_name || model.model_id} ({model.provider_name})
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Routing Rules */}
      <div className="bg-white shadow sm:rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-lg font-medium text-gray-900">Routing Rules</h3>
          <div className="mt-4 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">Max Cost per Request ($)</label>
              <input
                type="number"
                step="0.01"
                value={persona.routing_rules?.max_cost || ''}
                onChange={(e) => setPersona({
                  ...persona,
                  routing_rules: {
                    ...persona.routing_rules,
                    max_cost: parseFloat(e.target.value) || undefined
                  }
                })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                placeholder="0.10"
              />
            </div>
            <div className="flex items-center">
              <input
                type="checkbox"
                id="prefer_local"
                checked={persona.routing_rules?.prefer_local || false}
                onChange={(e) => setPersona({
                  ...persona,
                  routing_rules: {
                    ...persona.routing_rules,
                    prefer_local: e.target.checked
                  }
                })}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              <label htmlFor="prefer_local" className="ml-2 block text-sm text-gray-700">
                Prefer local models (free)
              </label>
            </div>
            <div className="flex items-center">
              <input
                type="checkbox"
                id="auto_route"
                checked={persona.routing_rules?.auto_route || false}
                onChange={(e) => setPersona({
                  ...persona,
                  routing_rules: {
                    ...persona.routing_rules,
                    auto_route: e.target.checked
                  }
                })}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              <label htmlFor="auto_route" className="ml-2 block text-sm text-gray-700">
                Auto-route requests (classify before sending)
              </label>
            </div>
          </div>
        </div>
      </div>

      {/* Memory Settings */}
      <div className="bg-white shadow sm:rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-lg font-medium text-gray-900">Memory Settings</h3>
          <div className="mt-4 space-y-4">
            <div className="flex items-center">
              <input
                type="checkbox"
                id="memory_enabled"
                checked={persona.memory_enabled || false}
                onChange={(e) => setPersona({ ...persona, memory_enabled: e.target.checked })}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              <label htmlFor="memory_enabled" className="ml-2 block text-sm text-gray-700">
                Enable conversation memory
              </label>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Max Memory Messages</label>
              <input
                type="number"
                min="0"
                max="100"
                value={persona.max_memory_messages || 10}
                onChange={(e) => setPersona({ ...persona, max_memory_messages: parseInt(e.target.value) || 10 })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
              />
              <p className="mt-1 text-sm text-gray-500">
                Number of previous messages to include as context
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3">
        <Link
          href="/personas"
          className="inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
        >
          Cancel
        </Link>
        <button
          type="submit"
          disabled={saving || !persona.name}
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300"
        >
          {saving ? 'Saving...' : 'Save Persona'}
        </button>
      </div>
    </form>
  )
}