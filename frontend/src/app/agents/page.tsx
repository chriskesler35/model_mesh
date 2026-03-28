'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { Agent, AGENT_TYPES } from '@/lib/types'

const AGENT_TYPE_ICONS: Record<string, string> = {
  coder: '💻',
  researcher: '🔍',
  designer: '🎨',
  reviewer: '👀',
  planner: '📋',
  executor: '⚡',
  writer: '✍️'
}

const AGENT_TYPE_COLORS: Record<string, string> = {
  coder: 'bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200',
  researcher: 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200',
  designer: 'bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200',
  reviewer: 'bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200',
  planner: 'bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200',
  executor: 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200',
  writer: 'bg-pink-100 dark:bg-pink-900 text-pink-800 dark:text-pink-200'
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadAgents()
  }, [])

  const loadAgents = async () => {
    try {
      setLoading(true)
      const response = await api.getAgents()
      setAgents(response.data)
      setError(null)
    } catch (err) {
      setError('Failed to load agents')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const toggleAgent = async (id: string, isActive: boolean) => {
    try {
      await api.updateAgent(id, { is_active: !isActive })
      setAgents(agents.map(a => a.id === id ? { ...a, is_active: !isActive } : a))
    } catch (err) {
      console.error('Failed to toggle agent:', err)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-gray-500 dark:text-gray-400">Loading agents...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-red-500">{error}</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Agents</h1>
        <Link
          href="/agents/new"
          className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors"
        >
          Create Agent
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {agents.map(agent => (
          <div
            key={agent.id}
            className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 shadow-sm"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <span className="text-2xl">{AGENT_TYPE_ICONS[agent.agent_type] || '🤖'}</span>
                <div>
                  <h3 className="font-semibold text-gray-900 dark:text-white">{agent.name}</h3>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${AGENT_TYPE_COLORS[agent.agent_type] || 'bg-gray-100 dark:bg-gray-700'}`}>
                    {agent.agent_type}
                  </span>
                </div>
              </div>
              <button
                onClick={() => toggleAgent(agent.id, agent.is_active)}
                className={`px-2 py-1 text-xs rounded ${
                  agent.is_active
                    ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                    : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                }`}
              >
                {agent.is_active ? 'Active' : 'Inactive'}
              </button>
            </div>

            <p className="text-sm text-gray-600 dark:text-gray-400 mb-3 line-clamp-2">
              {agent.description || 'No description'}
            </p>

            <div className="flex flex-wrap gap-1 mb-3">
              {agent.tools.slice(0, 4).map(tool => (
                <span key={tool} className="text-xs bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
                  {tool}
                </span>
              ))}
              {agent.tools.length > 4 && (
                <span className="text-xs bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">
                  +{agent.tools.length - 4} more
                </span>
              )}
            </div>

            <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
              <span>Max: {agent.max_iterations} iterations</span>
              <Link
                href={`/agents/${agent.id}`}
                className="text-orange-600 hover:text-orange-700 dark:text-orange-400"
              >
                Configure →
              </Link>
            </div>
          </div>
        ))}
      </div>

      {agents.length === 0 && (
        <div className="text-center py-12">
          <p className="text-gray-500 dark:text-gray-400 mb-4">No agents configured yet</p>
          <button className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors">
            Create First Agent
          </button>
        </div>
      )}

      {/* Default Agent Types Reference */}
      <div className="mt-8 border-t border-gray-200 dark:border-gray-700 pt-8">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Available Agent Types</h2>
        <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-4">
          {AGENT_TYPES.map(type => (
            <div
              key={type}
              className="flex items-center gap-2 px-3 py-2 bg-gray-50 dark:bg-gray-800 rounded-lg"
            >
              <span>{AGENT_TYPE_ICONS[type] || '🤖'}</span>
              <span className="capitalize text-sm font-medium text-gray-700 dark:text-gray-300">{type}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}