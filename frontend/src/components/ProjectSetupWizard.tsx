'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'
import { useState, useEffect, useRef } from 'react'

interface Template {
  id: string
  name: string
  description: string
}

interface Agent {
  id: string
  name: string
  agent_type: string
  description?: string
}

interface Project {
  id: string
  name: string
  path: string
}

interface ProjectSetupWizardProps {
  templates: Template[]
  onComplete: (project: Project) => void
  onDismiss: () => void
}

const TEMPLATE_ICONS: Record<string, string> = {
  blank: '📄',
  'python-api': '🐍',
  'next-app': '⚡',
  'cli-tool': '🔧',
}

const AGENT_ICONS: Record<string, string> = {
  coder: '💻',
  researcher: '🔍',
  designer: '🎨',
  reviewer: '👀',
  planner: '📋',
  executor: '⚙️',
  writer: '✍️',
}

type Step = 'intro' | 'name' | 'template' | 'location' | 'agents' | 'sandbox' | 'review' | 'success'

const STEP_ORDER: Step[] = ['intro', 'name', 'template', 'location', 'agents', 'sandbox', 'review', 'success']

export default function ProjectSetupWizard({ templates, onComplete, onDismiss }: ProjectSetupWizardProps) {
  const [step, setStep] = useState<Step>('intro')
  const [form, setForm] = useState({
    name: '',
    description: '',
    template: 'blank',
    path: '',
    agents: [] as string[],
    sandbox_mode: 'restricted' as 'restricted' | 'full',
  })
  const [availableAgents, setAvailableAgents] = useState<Agent[]>([])
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [createdProject, setCreatedProject] = useState<Project | null>(null)
  const nameInputRef = useRef<HTMLInputElement>(null)
  const pathInputRef = useRef<HTMLInputElement>(null)

  // Load available agents when wizard opens
  useEffect(() => {
    fetch(`${API_BASE}/v1/agents`, { headers: AUTH_HEADERS })
      .then(r => r.json())
      .then(d => setAvailableAgents(d.data || []))
      .catch(() => { /* agents optional */ })
  }, [])

  // Auto-focus inputs on step change
  useEffect(() => {
    if (step === 'name') setTimeout(() => nameInputRef.current?.focus(), 100)
    if (step === 'location') setTimeout(() => pathInputRef.current?.focus(), 100)
  }, [step])

  // Auto-suggest path based on name
  useEffect(() => {
    if (step === 'location' && !form.path && form.name) {
      const slug = form.name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
      // Default to a sensible Windows path; user can change
      setForm(f => ({ ...f, path: `C:\\Projects\\${slug}` }))
    }
  }, [step, form.name, form.path])

  const currentStepIdx = STEP_ORDER.indexOf(step)
  const totalSteps = STEP_ORDER.length - 2 // exclude intro + success
  const progressIdx = Math.max(0, currentStepIdx - 1) // 0-indexed within progress bar

  const goNext = () => {
    const next = STEP_ORDER[currentStepIdx + 1]
    if (next) setStep(next)
  }
  const goBack = () => {
    const prev = STEP_ORDER[currentStepIdx - 1]
    if (prev && prev !== 'intro') setStep(prev)
  }

  const createProject = async () => {
    if (creating) return
    setCreating(true)
    setError('')
    try {
      const res = await fetch(`${API_BASE}/v1/projects/`, {
        method: 'POST',
        headers: AUTH_HEADERS,
        body: JSON.stringify(form),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Failed to create project')
      }
      const project = await res.json()
      setCreatedProject(project)
      setStep('success')
    } catch (e: any) {
      setError(e.message || 'Something went wrong')
    } finally {
      setCreating(false)
    }
  }

  const toggleAgent = (id: string) => {
    setForm(f => ({
      ...f,
      agents: f.agents.includes(id) ? f.agents.filter(a => a !== id) : [...f.agents, id],
    }))
  }

  const canProceed = () => {
    switch (step) {
      case 'name': return form.name.trim().length > 0
      case 'template': return !!form.template
      case 'location': return form.path.trim().length > 0
      case 'agents': return true // optional
      case 'sandbox': return true
      case 'review': return true
      default: return true
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between flex-shrink-0">
          <div>
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">Project Setup</h2>
            {step !== 'intro' && step !== 'success' && (
              <p className="text-xs text-gray-400 mt-0.5">Step {progressIdx + 1} of {totalSteps}</p>
            )}
          </div>
          <button onClick={onDismiss} className="text-gray-400 hover:text-gray-600 p-1 rounded">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Progress bar */}
        {step !== 'intro' && step !== 'success' && (
          <div className="h-1 bg-gray-100 dark:bg-gray-800 flex-shrink-0">
            <div
              className="h-full bg-orange-500 transition-all duration-300"
              style={{ width: `${((progressIdx + 1) / totalSteps) * 100}%` }}
            />
          </div>
        )}

        {/* Body */}
        <div className="px-6 py-6 overflow-y-auto flex-1">
          {step === 'intro' && (
            <div className="text-center py-6">
              <div className="text-5xl mb-4">🗂️</div>
              <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Let's set up a new project</h3>
              <p className="text-sm text-gray-500 mb-6 max-w-md mx-auto">
                I'll walk you through naming, picking a template, choosing a location, and configuring how agents interact with it.
                Should take about a minute.
              </p>
              <div className="grid grid-cols-2 gap-2 max-w-md mx-auto text-left text-xs text-gray-500 mb-2">
                <div className="flex items-center gap-2"><span className="text-orange-500">1.</span> Name & description</div>
                <div className="flex items-center gap-2"><span className="text-orange-500">2.</span> Pick a template</div>
                <div className="flex items-center gap-2"><span className="text-orange-500">3.</span> Choose location</div>
                <div className="flex items-center gap-2"><span className="text-orange-500">4.</span> Assign agents</div>
                <div className="flex items-center gap-2"><span className="text-orange-500">5.</span> Set access mode</div>
                <div className="flex items-center gap-2"><span className="text-orange-500">6.</span> Review & create</div>
              </div>
            </div>
          )}

          {step === 'name' && (
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">What do you want to call it?</h3>
                <p className="text-sm text-gray-500">A short descriptive name helps you find it later.</p>
              </div>
              <input
                ref={nameInputRef}
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                onKeyDown={e => e.key === 'Enter' && canProceed() && goNext()}
                placeholder="My Awesome App"
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-4 py-3 text-base focus:outline-none focus:ring-2 focus:ring-orange-400"
              />
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                  Description <span className="text-gray-400">(optional)</span>
                </label>
                <input
                  value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && canProceed() && goNext()}
                  placeholder="One-line summary of what this project does"
                  className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
                />
              </div>
            </div>
          )}

          {step === 'template' && (
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">Pick a starting template</h3>
                <p className="text-sm text-gray-500">
                  Choose <strong>Blank</strong> to register an existing directory, or pick a template to scaffold a new project.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                {templates.map(t => (
                  <button
                    key={t.id}
                    onClick={() => setForm(f => ({ ...f, template: t.id }))}
                    className={`flex items-start gap-3 p-4 rounded-xl border-2 text-left transition-all ${
                      form.template === t.id
                        ? 'border-orange-400 bg-orange-50 dark:bg-orange-900/20'
                        : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                    }`}
                  >
                    <span className="text-2xl flex-shrink-0">{TEMPLATE_ICONS[t.id] || '📁'}</span>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">{t.name}</p>
                      <p className="text-xs text-gray-500 mt-0.5">{t.description}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 'location' && (
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">Where should it live on disk?</h3>
                <p className="text-sm text-gray-500">
                  Full path to the project folder. If it exists, we'll just register it.
                  If it doesn't, we'll create it and scaffold the template files.
                </p>
              </div>
              <input
                ref={pathInputRef}
                value={form.path}
                onChange={e => setForm(f => ({ ...f, path: e.target.value }))}
                onKeyDown={e => e.key === 'Enter' && canProceed() && goNext()}
                placeholder="C:\Projects\my-app"
                className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-4 py-3 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-orange-400"
              />
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 text-xs text-blue-800 dark:text-blue-300">
                <strong>Tip:</strong> Use forward slashes or escaped backslashes. Examples:
                <ul className="mt-1 ml-4 font-mono">
                  <li>• <code>C:\Projects\my-app</code></li>
                  <li>• <code>G:/Work/project-name</code></li>
                  <li>• <code>E:\Dev\client-site</code></li>
                </ul>
              </div>
            </div>
          )}

          {step === 'agents' && (
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">Which agents should work on this?</h3>
                <p className="text-sm text-gray-500">
                  Pick any that fit — you can always change this later. Skip if you're not sure.
                </p>
              </div>
              {availableAgents.length === 0 ? (
                <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4 text-sm text-gray-500 text-center">
                  No agents configured yet. You can add agents later from the Agents page.
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2 max-h-80 overflow-y-auto">
                  {availableAgents.map(a => {
                    const selected = form.agents.includes(a.id)
                    return (
                      <button
                        key={a.id}
                        onClick={() => toggleAgent(a.id)}
                        className={`flex items-start gap-2 p-3 rounded-lg border-2 text-left transition-all ${
                          selected
                            ? 'border-orange-400 bg-orange-50 dark:bg-orange-900/20'
                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                        }`}
                      >
                        <span className="text-lg flex-shrink-0">{AGENT_ICONS[a.agent_type] || '🤖'}</span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{a.name}</p>
                          <p className="text-xs text-gray-500 capitalize">{a.agent_type}</p>
                        </div>
                        {selected && <span className="text-orange-500 text-sm flex-shrink-0">✓</span>}
                      </button>
                    )
                  })}
                </div>
              )}
              <p className="text-xs text-gray-400 text-center">
                {form.agents.length === 0 ? 'None selected — skip or pick some above' : `${form.agents.length} agent${form.agents.length > 1 ? 's' : ''} selected`}
              </p>
            </div>
          )}

          {step === 'sandbox' && (
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">How much access should agents have?</h3>
                <p className="text-sm text-gray-500">
                  This controls what agents can do in this project. You can change it anytime.
                </p>
              </div>
              <div className="space-y-3">
                <button
                  onClick={() => setForm(f => ({ ...f, sandbox_mode: 'restricted' }))}
                  className={`w-full p-4 rounded-xl border-2 text-left transition-all ${
                    form.sandbox_mode === 'restricted'
                      ? 'border-green-400 bg-green-50 dark:bg-green-900/20'
                      : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <span className="text-2xl flex-shrink-0">🔒</span>
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">Restricted (Recommended)</p>
                      <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">
                        Agent is confined to this project folder. Can read/write files within the project,
                        run tests, and commit to git — but cannot execute arbitrary shell commands or touch
                        files outside the project.
                      </p>
                    </div>
                  </div>
                </button>
                <button
                  onClick={() => setForm(f => ({ ...f, sandbox_mode: 'full' }))}
                  className={`w-full p-4 rounded-xl border-2 text-left transition-all ${
                    form.sandbox_mode === 'full'
                      ? 'border-amber-400 bg-amber-50 dark:bg-amber-900/20'
                      : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <span className="text-2xl flex-shrink-0">🔓</span>
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">Full Access</p>
                      <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">
                        Agent can execute any shell command, access any file on your machine, and make
                        network requests. Only use this if you fully trust what the agent will do.
                      </p>
                    </div>
                  </div>
                </button>
              </div>
            </div>
          )}

          {step === 'review' && (
            <div className="space-y-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1">Ready to create?</h3>
                <p className="text-sm text-gray-500">Review your settings below, then click Create.</p>
              </div>
              <div className="bg-gray-50 dark:bg-gray-800/50 rounded-xl border border-gray-200 dark:border-gray-700 divide-y divide-gray-200 dark:divide-gray-700">
                <ReviewRow label="Name" value={form.name} />
                {form.description && <ReviewRow label="Description" value={form.description} />}
                <ReviewRow label="Template" value={`${TEMPLATE_ICONS[form.template] || '📁'} ${templates.find(t => t.id === form.template)?.name || form.template}`} />
                <ReviewRow label="Location" value={form.path} mono />
                <ReviewRow label="Agents" value={form.agents.length === 0 ? 'None' : `${form.agents.length} selected`} />
                <ReviewRow label="Access" value={form.sandbox_mode === 'restricted' ? '🔒 Restricted' : '🔓 Full Access'} />
              </div>
              {error && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
                  {error}
                </div>
              )}
            </div>
          )}

          {step === 'success' && createdProject && (
            <div className="text-center py-4">
              <div className="text-5xl mb-4">✅</div>
              <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">Project created!</h3>
              <p className="text-sm text-gray-500 mb-6">
                <strong>{createdProject.name}</strong> is ready at <code className="text-xs font-mono">{createdProject.path}</code>
              </p>
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 text-sm text-blue-900 dark:text-blue-200 text-left">
                <p className="font-semibold mb-2">What's next?</p>
                <ul className="space-y-1.5 text-xs">
                  <li>• <strong>Open the project</strong> to browse files and view details</li>
                  <li>• <strong>Launch Workbench</strong> to have an agent work on a task</li>
                  <li>• Add or change agents anytime from the project detail page</li>
                  <li>• Change access mode (Restricted ↔ Full) from the project settings</li>
                </ul>
              </div>
            </div>
          )}
        </div>

        {/* Footer — Navigation buttons */}
        <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-800 flex items-center justify-between gap-3 flex-shrink-0">
          {step === 'intro' ? (
            <>
              <button onClick={onDismiss} className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50">
                Skip wizard
              </button>
              <button onClick={goNext} className="px-6 py-2 text-sm font-medium rounded-lg bg-orange-500 hover:bg-orange-600 text-white">
                Let's go →
              </button>
            </>
          ) : step === 'success' ? (
            <>
              <button onClick={onDismiss} className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50">
                Close
              </button>
              <button
                onClick={() => createdProject && onComplete(createdProject)}
                className="px-6 py-2 text-sm font-medium rounded-lg bg-orange-500 hover:bg-orange-600 text-white"
              >
                Open Project →
              </button>
            </>
          ) : (
            <>
              <button
                onClick={goBack}
                disabled={currentStepIdx <= 1}
                className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                ← Back
              </button>
              <div className="flex items-center gap-2">
                {step !== 'review' && (
                  <button
                    onClick={onDismiss}
                    className="px-3 py-2 text-xs text-gray-500 hover:text-gray-700"
                  >
                    I'll finish manually
                  </button>
                )}
                {step === 'review' ? (
                  <button
                    onClick={createProject}
                    disabled={creating}
                    className="px-6 py-2 text-sm font-medium rounded-lg bg-orange-500 hover:bg-orange-600 text-white disabled:bg-gray-300"
                  >
                    {creating ? 'Creating...' : 'Create Project'}
                  </button>
                ) : (
                  <button
                    onClick={goNext}
                    disabled={!canProceed()}
                    className="px-6 py-2 text-sm font-medium rounded-lg bg-orange-500 hover:bg-orange-600 text-white disabled:bg-gray-300"
                  >
                    Next →
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function ReviewRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5 gap-3">
      <span className="text-xs text-gray-500 flex-shrink-0">{label}</span>
      <span className={`text-sm text-gray-900 dark:text-white text-right truncate ${mono ? 'font-mono text-xs' : ''}`}>
        {value}
      </span>
    </div>
  )
}
