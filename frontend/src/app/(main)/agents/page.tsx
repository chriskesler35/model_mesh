'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { Agent, AGENT_TYPES, MethodPhase } from '@/lib/types'

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
  const [phases, setPhases] = useState<MethodPhase[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadAgents()
    loadPhases()
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

  const loadPhases = async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/agents/method-phases`, { headers: AUTH_HEADERS })
      if (res.ok) {
        const data = await res.json()
        setPhases(data.data || [])
      }
    } catch (err) {
      console.error('Failed to load method phases', err)
    }
  }

  const bindAgentToPhase = async (agentId: string, phaseName: string | null) => {
    try {
      await api.updateAgent(agentId, { method_phase: phaseName } as any)
      setAgents(agents.map(a => a.id === agentId ? { ...a, method_phase: phaseName || undefined } : a))
    } catch (err) {
      console.error('Failed to bind phase:', err)
      alert('Failed to bind agent to phase')
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

  const deleteAgent = async (id: string, name: string) => {
    if (!confirm(`Delete agent "${name}"? This cannot be undone.`)) return
    try {
      await fetch(`${API_BASE}/v1/agents/${id}`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' },
      })
      setAgents(agents.filter(a => a.id !== id))
    } catch (err) {
      console.error('Failed to delete agent:', err)
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

      {/* Method Phase Bindings */}
      {phases.length > 0 && (
        <div className="bg-indigo-50 dark:bg-indigo-900/10 border border-indigo-200 dark:border-indigo-800 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-semibold text-indigo-900 dark:text-indigo-200">🎭 Method Phase Bindings</h2>
              <p className="text-xs text-indigo-700 dark:text-indigo-300 mt-0.5">
                Each development method (BMAD/GSD/SuperPowers) has phases. Bind one agent to each phase so pipelines use the right model + persona.
              </p>
            </div>
          </div>
          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
            {phases.map(phase => {
              const bound = agents.find(a => a.method_phase?.toLowerCase() === phase.name.toLowerCase())
              return (
                <div key={phase.name}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${
                    bound
                      ? 'bg-white dark:bg-gray-800 border-green-300 dark:border-green-700'
                      : 'bg-amber-50 dark:bg-amber-900/20 border-amber-300 dark:border-amber-700'
                  }`}>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-semibold text-gray-900 dark:text-white">{phase.name}</span>
                      <span className="text-[10px] text-gray-500 dark:text-gray-400">({phase.role})</span>
                    </div>
                    <div className="text-[10px] text-gray-500 dark:text-gray-400 flex items-center gap-1">
                      {phase.methods.map(m => (
                        <span key={m} className="px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-700 uppercase">{m}</span>
                      ))}
                    </div>
                  </div>
                  <select
                    value={bound?.id || ''}
                    onChange={(e) => {
                      const agentId = e.target.value
                      if (!agentId) {
                        // Unbind all agents currently bound to this phase
                        if (bound) bindAgentToPhase(bound.id, null)
                        return
                      }
                      // If a different agent is currently bound, unbind it first
                      if (bound && bound.id !== agentId) bindAgentToPhase(bound.id, null)
                      bindAgentToPhase(agentId, phase.name)
                    }}
                    className="text-[11px] px-1.5 py-1 rounded border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-white max-w-[140px]"
                  >
                    <option value="">— no agent —</option>
                    {agents.filter(a => a.is_active).map(a => (
                      <option key={a.id} value={a.id}>{a.name}</option>
                    ))}
                  </select>
                </div>
              )
            })}
          </div>
        </div>
      )}

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
                  <div className="flex items-center gap-1 flex-wrap">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${AGENT_TYPE_COLORS[agent.agent_type] || 'bg-gray-100 dark:bg-gray-700'}`}>
                      {agent.agent_type}
                    </span>
                    {agent.method_phase && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300 font-medium" title="Bound to this method phase">
                        🎭 {agent.method_phase}
                      </span>
                    )}
                  </div>
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

            <p className="text-sm text-gray-600 dark:text-gray-400 mb-2 line-clamp-2">
              {agent.description || 'No description'}
            </p>

            {(agent.persona_name || agent.resolved_model_name) && (
              <div className="text-[11px] text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1 flex-wrap">
                {agent.persona_name && (
                  <span className="px-1.5 py-0.5 rounded bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300">
                    🎭 {agent.persona_name}
                  </span>
                )}
                {agent.resolved_model_name && (
                  <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 font-mono">
                    {agent.resolved_model_name}
                  </span>
                )}
              </div>
            )}

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
              <div className="flex items-center gap-3">
                <Link
                  href={`/workbench?agent=${agent.id}&agent_type=${agent.agent_type}`}
                  className="flex items-center gap-1 px-2 py-1 bg-orange-500 hover:bg-orange-600 text-white rounded text-xs font-medium transition-colors"
                >
                  🚀 Launch
                </Link>
                <Link
                  href={`/agents/${agent.id}`}
                  className="text-orange-600 hover:text-orange-700 dark:text-orange-400"
                >
                  Configure →
                </Link>
                <button
                  onClick={() => deleteAgent(agent.id, agent.name)}
                  className="text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                >
                  Delete
                </button>
              </div>
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
