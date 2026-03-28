'use client'

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { api } from '@/lib/api'
import { Agent, AGENT_TYPES, AGENT_TOOLS } from '@/lib/types'

const AGENT_TYPE_DESCRIPTIONS: Record<string, string> = {
  coder: 'Expert Python architect. Writes, reviews, and refactors code.',
  researcher: 'Searches web, summarizes documents, fact-checks information.',
  designer: 'Creates images, logos, banners, and visual assets.',
  reviewer: 'Quality checks work, suggests improvements, validates output.',
  planner: 'Breaks down complex tasks into steps, designs workflows.',
  executor: 'Runs tools, makes API calls, performs file operations.',
  writer: 'Creates content, documentation, summaries, and copy.'
}

const TOOL_DESCRIPTIONS: Record<string, string> = {
  read_file: 'Read file contents',
  write_file: 'Create or modify files',
  run_tests: 'Execute test suites',
  git_commit: 'Commit changes to git',
  shell_execute: 'Run shell commands',
  http_request: 'Make HTTP requests',
  web_search: 'Search the web',
  generate_image: 'Generate images',
  image_variation: 'Create image variations'
}

export default function AgentDetailPage() {
  const params = useParams()
  const router = useRouter()
  const agentId = params.id as string
  
  const [agent, setAgent] = useState<Agent | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({
    name: '',
    description: '',
    system_prompt: '',
    agent_type: 'coder',
    tools: [] as string[],
    memory_enabled: true,
    max_iterations: 10,
    timeout_seconds: 300
  })

  useEffect(() => {
    if (agentId === 'new') {
      setLoading(false)
      setEditing(true)
    } else {
      loadAgent()
    }
  }, [agentId])

  const loadAgent = async () => {
    try {
      const data = await api.getAgent(agentId)
      setAgent(data)
      setForm({
        name: data.name,
        description: data.description || '',
        system_prompt: data.system_prompt,
        agent_type: data.agent_type,
        tools: data.tools,
        memory_enabled: data.memory_enabled,
        max_iterations: data.max_iterations,
        timeout_seconds: data.timeout_seconds
      })
    } catch (err) {
      console.error('Failed to load agent:', err)
    } finally {
      setLoading(false)
    }
  }

  const saveAgent = async () => {
    setSaving(true)
    try {
      if (agentId === 'new') {
        const data = await api.createAgent(form)
        router.push(`/agents/${data.id}`)
      } else {
        await api.updateAgent(agentId, form)
        await loadAgent()
        setEditing(false)
      }
    } catch (err) {
      console.error('Failed to save agent:', err)
      alert('Failed to save agent')
    } finally {
      setSaving(false)
    }
  }

  const toggleTool = (tool: string) => {
    setForm(prev => ({
      ...prev,
      tools: prev.tools.includes(tool)
        ? prev.tools.filter(t => t !== tool)
        : [...prev.tools, tool]
    }))
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-gray-500 dark:text-gray-400">Loading...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            href="/agents"
            className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            ← Back to Agents
          </Link>
        </div>
        <div className="flex gap-2">
          {agent && !editing && (
            <button
              onClick={() => setEditing(true)}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600"
            >
              Edit
            </button>
          )}
          {editing && (
            <>
              <button
                onClick={() => agentId === 'new' ? router.push('/agents') : setEditing(false)}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600"
              >
                Cancel
              </button>
              <button
                onClick={saveAgent}
                disabled={saving}
                className="px-4 py-2 text-sm font-medium text-white bg-orange-600 rounded-lg hover:bg-orange-700 disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </>
          )}
        </div>
      </div>

      {editing ? (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
              Agent Name
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm(prev => ({ ...prev, name: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              placeholder="My Custom Agent"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
              Agent Type
            </label>
            <select
              value={form.agent_type}
              onChange={(e) => setForm(prev => ({ ...prev, agent_type: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            >
              {AGENT_TYPES.map(type => (
                <option key={type} value={type}>{type.charAt(0).toUpperCase() + type.slice(1)}</option>
              ))}
            </select>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {AGENT_TYPE_DESCRIPTIONS[form.agent_type]}
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
              Description
            </label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm(prev => ({ ...prev, description: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              placeholder="Brief description of what this agent does"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
              System Prompt
            </label>
            <textarea
              value={form.system_prompt}
              onChange={(e) => setForm(prev => ({ ...prev, system_prompt: e.target.value }))}
              rows={6}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white font-mono text-sm"
              placeholder="You are a helpful assistant..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-2">
              Tools
            </label>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {AGENT_TOOLS.map(tool => (
                <label
                  key={tool}
                  className="flex items-center gap-2 p-2 border border-gray-200 dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  <input
                    type="checkbox"
                    checked={form.tools.includes(tool)}
                    onChange={() => toggleTool(tool)}
                    className="rounded border-gray-300 dark:border-gray-600"
                  />
                  <div>
                    <span className="text-sm font-medium text-gray-900 dark:text-white">{tool}</span>
                    {TOOL_DESCRIPTIONS[tool] && (
                      <p className="text-xs text-gray-500 dark:text-gray-400">{TOOL_DESCRIPTIONS[tool]}</p>
                    )}
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                Max Iterations
              </label>
              <input
                type="number"
                value={form.max_iterations}
                onChange={(e) => setForm(prev => ({ ...prev, max_iterations: parseInt(e.target.value) || 10 }))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                Timeout (seconds)
              </label>
              <input
                type="number"
                value={form.timeout_seconds}
                onChange={(e) => setForm(prev => ({ ...prev, timeout_seconds: parseInt(e.target.value) || 300 }))}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="memory_enabled"
              checked={form.memory_enabled}
              onChange={(e) => setForm(prev => ({ ...prev, memory_enabled: e.target.checked }))}
              className="rounded border-gray-300 dark:border-gray-600"
            />
            <label htmlFor="memory_enabled" className="text-sm text-gray-700 dark:text-gray-200">
              Enable memory (agent remembers context between turns)
            </label>
          </div>
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{agent?.name}</h1>
              <span className="inline-block mt-1 px-2 py-0.5 text-xs rounded-full bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200">
                {agent?.agent_type}
              </span>
            </div>
            <span className={`px-2 py-1 text-xs rounded ${agent?.is_active ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'}`}>
              {agent?.is_active ? 'Active' : 'Inactive'}
            </span>
          </div>

          {agent?.description && (
            <p className="text-gray-600 dark:text-gray-400 mb-4">{agent.description}</p>
          )}

          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">System Prompt</h3>
              <pre className="text-sm text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-900 p-3 rounded-lg overflow-x-auto whitespace-pre-wrap">
                {agent?.system_prompt}
              </pre>
            </div>

            <div>
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Tools</h3>
              <div className="flex flex-wrap gap-2">
                {agent?.tools.map(tool => (
                  <span key={tool} className="px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 rounded">
                    {tool}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <div>
                <span className="text-sm text-gray-500 dark:text-gray-400">Max Iterations</span>
                <p className="text-gray-900 dark:text-white font-medium">{agent?.max_iterations}</p>
              </div>
              <div>
                <span className="text-sm text-gray-500 dark:text-gray-400">Timeout</span>
                <p className="text-gray-900 dark:text-white font-medium">{agent?.timeout_seconds}s</p>
              </div>
              <div>
                <span className="text-sm text-gray-500 dark:text-gray-400">Memory</span>
                <p className="text-gray-900 dark:text-white font-medium">{agent?.memory_enabled ? 'Enabled' : 'Disabled'}</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}