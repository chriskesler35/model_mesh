'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { api } from '@/lib/api'

export default function NewPersonaPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    system_prompt: '',
    memory_enabled: true,
    max_memory_messages: 10,
    routing_rules: {
      max_cost: 0.01,
      prefer_local: false,
      max_tokens: 4096,
    },
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      await api.createPersona(formData)
      router.push('/personas')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create persona')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-8">
        <nav className="flex" aria-label="Breadcrumb">
          <ol className="flex items-center space-x-4">
            <li>
              <Link href="/personas" className="text-gray-500 hover:text-gray-700">
                Personas
              </Link>
            </li>
            <li>
              <span className="text-gray-400">/</span>
            </li>
            <li>
              <span className="text-gray-900">New</span>
            </li>
          </ol>
        </nav>
      </div>

      <div className="bg-white shadow sm:rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          <h1 className="text-2xl font-bold text-gray-900 mb-6">Create Persona</h1>

          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="name" className="block text-sm font-medium text-gray-700">
                Name
              </label>
              <input
                type="text"
                id="name"
                name="name"
                required
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                placeholder="e.g., python-architect"
              />
            </div>

            <div>
              <label htmlFor="description" className="block text-sm font-medium text-gray-700">
                Description
              </label>
              <input
                type="text"
                id="description"
                name="description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                placeholder="e.g., Expert Python code reviewer"
              />
            </div>

            <div>
              <label htmlFor="system_prompt" className="block text-sm font-medium text-gray-700">
                System Prompt
              </label>
              <textarea
                id="system_prompt"
                name="system_prompt"
                rows={4}
                value={formData.system_prompt}
                onChange={(e) => setFormData({ ...formData, system_prompt: e.target.value })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                placeholder="You are a helpful assistant..."
              />
            </div>

            <div className="border-t border-gray-200 pt-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Routing Rules</h3>
              
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="max_cost" className="block text-sm font-medium text-gray-700">
                    Max Cost ($)
                  </label>
                  <input
                    type="number"
                    id="max_cost"
                    name="max_cost"
                    step="0.001"
                    value={formData.routing_rules.max_cost}
                    onChange={(e) => setFormData({
                      ...formData,
                      routing_rules: { ...formData.routing_rules, max_cost: parseFloat(e.target.value) }
                    })}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                  />
                </div>

                <div>
                  <label htmlFor="max_tokens" className="block text-sm font-medium text-gray-700">
                    Max Tokens
                  </label>
                  <input
                    type="number"
                    id="max_tokens"
                    name="max_tokens"
                    value={formData.routing_rules.max_tokens}
                    onChange={(e) => setFormData({
                      ...formData,
                      routing_rules: { ...formData.routing_rules, max_tokens: parseInt(e.target.value) }
                    })}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                  />
                </div>
              </div>

              <div className="mt-4">
                <label htmlFor="prefer_local" className="flex items-center">
                  <input
                    type="checkbox"
                    id="prefer_local"
                    name="prefer_local"
                    checked={formData.routing_rules.prefer_local}
                    onChange={(e) => setFormData({
                      ...formData,
                      routing_rules: { ...formData.routing_rules, prefer_local: e.target.checked }
                    })}
                    className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                  />
                  <span className="ml-2 text-sm text-gray-700">Prefer local models</span>
                </label>
              </div>
            </div>

            <div className="border-t border-gray-200 pt-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Memory Settings</h3>
              
              <div className="flex items-center mb-4">
                <input
                  type="checkbox"
                  id="memory_enabled"
                  name="memory_enabled"
                  checked={formData.memory_enabled}
                  onChange={(e) => setFormData({ ...formData, memory_enabled: e.target.checked })}
                  className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                />
                <label htmlFor="memory_enabled" className="ml-2 text-sm text-gray-700">
                  Enable conversation memory
                </label>
              </div>

              <div>
                <label htmlFor="max_memory_messages" className="block text-sm font-medium text-gray-700">
                  Max Messages in Memory
                </label>
                <input
                  type="number"
                  id="max_memory_messages"
                  name="max_memory_messages"
                  value={formData.max_memory_messages}
                  onChange={(e) => setFormData({ ...formData, max_memory_messages: parseInt(e.target.value) })}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                />
              </div>
            </div>

            <div className="flex justify-end space-x-3 pt-6">
              <Link
                href="/personas"
                className="px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              >
                Cancel
              </Link>
              <button
                type="submit"
                disabled={loading}
                className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
              >
                {loading ? 'Creating...' : 'Create Persona'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}