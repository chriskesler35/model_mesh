'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { ModelFitnessCheck } from '@/components/ModelFitnessCheck'
import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'

function Toast({ message, type, onClose }: { message: string; type: 'success' | 'error'; onClose: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 3000)
    return () => clearTimeout(timer)
  }, [onClose])

  return (
    <div className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg text-white text-sm font-medium transition-all
      ${type === 'success' ? 'bg-green-600' : 'bg-red-600'}`}>
      {type === 'success' ? (
        <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      )}
      {message}
      <button onClick={onClose} className="ml-2 opacity-75 hover:opacity-100">✕</button>
    </div>
  )
}

interface Persona {
  id: string
  name: string
  description?: string
  system_prompt?: string
  primary_model_id?: string
  fallback_model_id?: string
  routing_rules?: {
    max_cost?: number
    prefer_local?: boolean
    auto_route?: boolean
  }
  memory_enabled?: boolean
  max_memory_messages?: number
  is_default?: boolean
}

interface Model {
  id: string
  model_id: string
  display_name?: string
  provider_name?: string
}

export default function PersonaDetailPage() {
  const router = useRouter()
  const params = useParams()
  const personaId = params?.id as string
  
  const [persona, setPersona] = useState<Persona | null>(null)
  const [models, setModels] = useState<Model[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  useEffect(() => {
    async function fetchData() {
      try {
        const [modelsRes] = await Promise.all([
          fetch(`${API_BASE}/v1/models`, {
            headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
          }).then(r => r.json())
        ])
        
        setModels(modelsRes.data || [])

        if (personaId) {
          const personaRes = await fetch(`${API_BASE}/v1/personas/${personaId}`, {
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

  const handleSave = async () => {
    if (!persona || !personaId) return
    setSaving(true)
    
    try {
      const res = await fetch(`${API_BASE}/v1/personas/${personaId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer modelmesh_local_dev_key'
        },
        body: JSON.stringify({
          name: persona.name,
          description: persona.description,
          system_prompt: persona.system_prompt,
          primary_model_id: persona.primary_model_id || null,
          fallback_model_id: persona.fallback_model_id || null,
          memory_enabled: persona.memory_enabled,
          max_memory_messages: persona.max_memory_messages,
          is_default: persona.is_default
        })
      })
      
      if (res.ok) {
        const updated = await res.json()
        setPersona(updated)
        setToast({ message: 'Persona saved successfully', type: 'success' })
      } else {
        const err = await res.text()
        console.error('Save failed:', err)
        setToast({ message: 'Failed to save persona', type: 'error' })
      }
    } catch (e) {
      console.error('Failed to save:', e)
      setToast({ message: 'Failed to save persona', type: 'error' })
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

  if (!persona) {
    return (
      <div className="text-center py-12">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Persona not found</h3>
        <Link href="/personas" className="mt-4 text-indigo-600 hover:text-indigo-500">
          Back to Personas
        </Link>
      </div>
    )
  }

  return (
    <div>
      {toast && (
        <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />
      )}
      <div className="mb-8">
        <Link href="/personas" className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400">
          ← Back to Personas
        </Link>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mt-2">{persona.name}</h1>
        {persona.description && (
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{persona.description}</p>
        )}
      </div>

      <div className="space-y-6">
        {/* Basic Info */}
        <div className="bg-white dark:bg-gray-800 shadow sm:rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Basic Information</h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Name</label>
              <input
                type="text"
                value={persona.name}
                onChange={(e) => setPersona({ ...persona, name: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Description</label>
              <input
                type="text"
                value={persona.description || ''}
                onChange={(e) => setPersona({ ...persona, description: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">System Prompt</label>
              <textarea
                rows={6}
                value={persona.system_prompt || ''}
                onChange={(e) => setPersona({ ...persona, system_prompt: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm font-mono"
              />
            </div>
          </div>
        </div>

        {/* Model Selection */}
        <div className="bg-white dark:bg-gray-800 shadow sm:rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Model Selection</h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Primary Model</label>
              <select
                value={persona.primary_model_id || ''}
                onChange={(e) => setPersona({ ...persona, primary_model_id: e.target.value || undefined })}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
              >
                <option value="">Select a model</option>
                {models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.display_name || model.model_id} ({model.provider_name})
                  </option>
                ))}
              </select>
              {/* VRAM / hardware fitness check */}
              {persona.primary_model_id && (() => {
                const m = models.find(x => x.id === persona.primary_model_id)
                return m ? <ModelFitnessCheck modelId={m.model_id} /> : null
              })()}
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Fallback Model</label>
              <select
                value={persona.fallback_model_id || ''}
                onChange={(e) => setPersona({ ...persona, fallback_model_id: e.target.value || undefined })}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
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

        {/* Memory Settings */}
        <div className="bg-white dark:bg-gray-800 shadow sm:rounded-lg p-6">
          <h2 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Memory Settings</h2>
          
          <div className="space-y-4">
            <div className="flex items-center">
              <input
                type="checkbox"
                id="memory_enabled"
                checked={persona.memory_enabled || false}
                onChange={(e) => setPersona({ ...persona, memory_enabled: e.target.checked })}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              <label htmlFor="memory_enabled" className="ml-2 block text-sm text-gray-700 dark:text-gray-300">
                Enable conversation memory
              </label>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Max Memory Messages</label>
              <input
                type="number"
                min="0"
                max="100"
                value={persona.max_memory_messages || 10}
                onChange={(e) => setPersona({ ...persona, max_memory_messages: parseInt(e.target.value) || 10 })}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
              />
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <Link
            href="/personas"
            className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600"
          >
            Cancel
          </Link>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-orange-600 hover:bg-orange-700 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  )
}