'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'

const AUTH = { 'Authorization': 'Bearer modelmesh_local_dev_key', 'Content-Type': 'application/json' }

interface Project {
  id: string; name: string; path: string; template: string
  description: string; agents: string[]; created_at: string
  updated_at: string; path_exists: boolean; file_count: number; scaffolded: boolean
  sandbox_mode?: 'restricted' | 'full'
}
interface Template { id: string; name: string; description: string }

const TEMPLATE_ICONS: Record<string, string> = {
  blank: '📄', 'python-api': '🐍', 'next-app': '⚡', 'cli-tool': '🔧'
}

export default function ProjectsPage() {
  const router = useRouter()
  const [projects, setProjects] = useState<Project[]>([])
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [form, setForm] = useState({ name: '', path: '', template: 'blank', description: '', sandbox_mode: 'restricted' })
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  const fetchData = useCallback(async () => {
    const [proj, tmpl] = await Promise.all([
      fetch(`${API_BASE}/v1/projects/`, { headers: AUTH }).then(r => r.json()).catch(() => ({ data: [] })),
      fetch(`${API_BASE}/v1/projects/templates`, { headers: AUTH }).then(r => r.json()).catch(() => ({ data: [] })),
    ])
    setProjects(proj.data || [])
    setTemplates(tmpl.data || [])
    setLoading(false)
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const createProject = async () => {
    if (!form.name.trim() || !form.path.trim() || creating) return
    setCreating(true); setError('')
    try {
      const res = await fetch(`${API_BASE}/v1/projects/`, {
        method: 'POST', headers: AUTH, body: JSON.stringify(form)
      })
      if (!res.ok) throw new Error((await res.json()).detail || 'Failed')
      const p = await res.json()
      setProjects(prev => [p, ...prev])
      setShowNew(false)
      setForm({ name: '', path: '', template: 'blank', description: '', sandbox_mode: 'restricted' })
      router.push(`/projects/${p.id}`)
    } catch (e: any) { setError(e.message) }
    finally { setCreating(false) }
  }

  const deleteProject = async (id: string, deleteFiles: boolean) => {
    await fetch(`${API_BASE}/v1/projects/${id}?delete_files=${deleteFiles}`, { method: 'DELETE', headers: AUTH })
    setProjects(prev => prev.filter(p => p.id !== id))
  }

  if (loading) return (
    <div className="flex justify-center py-16">
      <div className="flex gap-1.5">{[0,1,2].map(i => <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />)}</div>
    </div>
  )

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Projects</h1>
          <p className="mt-1 text-sm text-gray-500">Manage your development projects — point agents at any folder on your machine</p>
        </div>
        <button onClick={() => setShowNew(true)}
          className="flex items-center gap-2 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium rounded-lg transition-colors">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" /></svg>
          New Project
        </button>
      </div>

      {projects.length === 0 ? (
        <div className="text-center py-20">
          <div className="text-5xl mb-4">🗂️</div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">No projects yet</h3>
          <p className="text-sm text-gray-500 mb-6">Create a project to start directing agents at specific directories.</p>
          <button onClick={() => setShowNew(true)}
            className="px-5 py-2.5 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium rounded-lg">
            Create First Project
          </button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map(p => (
            <div key={p.id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden hover:border-orange-300 hover:shadow-md transition-all group">
              <div className="p-5 cursor-pointer" onClick={() => router.push(`/projects/${p.id}`)}>
                <div className="flex items-start justify-between mb-3">
                  <span className="text-2xl">{TEMPLATE_ICONS[p.template] || '📁'}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${p.path_exists ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'}`}>
                    {p.path_exists ? '✓ found' : '✗ missing'}
                  </span>
                </div>
                <h3 className="font-semibold text-gray-900 dark:text-white mb-1">{p.name}</h3>
                {p.description && <p className="text-sm text-gray-500 mb-2 line-clamp-2">{p.description}</p>}
                <p className="text-xs font-mono text-gray-400 truncate">{p.path}</p>
                <div className="flex items-center gap-3 mt-3 text-xs text-gray-400">
                  <span>{p.file_count} files</span>
                  <span>{p.template}</span>
                  {p.agents?.length > 0 && <span>{p.agents.length} agents</span>}
                  <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${p.sandbox_mode === 'full' ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700'}`}>
                    {p.sandbox_mode === 'full' ? '🔓 Full Access' : '🔒 Restricted'}
                  </span>
                </div>
              </div>
              <div className="border-t border-gray-100 dark:border-gray-700 px-4 py-2.5 flex items-center gap-3 bg-gray-50 dark:bg-gray-900/50 opacity-0 group-hover:opacity-100 transition-opacity">
                <button onClick={() => router.push(`/projects/${p.id}`)}
                  className="text-xs text-indigo-600 hover:text-indigo-800 font-medium">Open</button>
                <button onClick={() => router.push(`/workbench?project=${p.id}`)}
                  className="text-xs text-orange-600 hover:text-orange-800 font-medium">Launch Workbench</button>
                <button onClick={() => {
                  if (confirm(`Delete project "${p.name}"?\n\nChoose OK to also delete files on disk, or Cancel to keep files.`)) {
                    deleteProject(p.id, false)
                  }
                }} className="text-xs text-red-500 hover:text-red-700 ml-auto">Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* New project modal */}
      {showNew && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-white dark:bg-gray-900 rounded-2xl shadow-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">New Project</h2>
              <button onClick={() => { setShowNew(false); setError('') }} className="text-gray-400 hover:text-gray-600">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Project Name</label>
                <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="My Awesome App"
                  className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Path on Disk</label>
                <input value={form.path} onChange={e => setForm(f => ({ ...f, path: e.target.value }))}
                  placeholder="C:\Projects\my-app  or  G:\Work\project"
                  className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-orange-400" />
                <p className="text-xs text-gray-400 mt-1">Existing directory (just register it) or new path (will be created + scaffolded)</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Template</label>
                <div className="grid grid-cols-2 gap-2">
                  {templates.map(t => (
                    <button key={t.id} onClick={() => setForm(f => ({ ...f, template: t.id }))}
                      className={`flex items-start gap-2 p-3 rounded-lg border text-left transition-colors ${
                        form.template === t.id
                          ? 'border-orange-400 bg-orange-50 dark:bg-orange-900/20'
                          : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                      }`}>
                      <span className="text-xl">{TEMPLATE_ICONS[t.id] || '📁'}</span>
                      <div>
                        <p className="text-xs font-semibold text-gray-800 dark:text-white">{t.name}</p>
                        <p className="text-xs text-gray-400">{t.description}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Description <span className="text-gray-400 font-normal">(optional)</span>
                </label>
                <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  placeholder="What is this project about?"
                  className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400" />
              </div>

              {/* Sandbox mode */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Access Mode</label>
                <div className="grid grid-cols-2 gap-3">
                  <button type="button"
                    onClick={() => setForm(f => ({ ...f, sandbox_mode: 'restricted' }))}
                    className={`p-3 rounded-lg border-2 text-left transition-colors ${form.sandbox_mode === 'restricted' ? 'border-green-400 bg-green-50 dark:bg-green-900/20' : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'}`}>
                    <p className="text-sm font-semibold text-gray-800 dark:text-white">🔒 Restricted</p>
                    <p className="text-xs text-gray-500 mt-0.5">Agent confined to project folder. No shell commands or outside file access.</p>
                  </button>
                  <button type="button"
                    onClick={() => setForm(f => ({ ...f, sandbox_mode: 'full' }))}
                    className={`p-3 rounded-lg border-2 text-left transition-colors ${form.sandbox_mode === 'full' ? 'border-amber-400 bg-amber-50 dark:bg-amber-900/20' : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'}`}>
                    <p className="text-sm font-semibold text-gray-800 dark:text-white">🔓 Full Access</p>
                    <p className="text-xs text-gray-500 mt-0.5">Agent has full system read/write/execute. Use for trusted projects only.</p>
                  </button>
                </div>
              </div>
              {error && <p className="text-sm text-red-500">{error}</p>}
            </div>
            <div className="px-6 py-4 border-t border-gray-100 dark:border-gray-800 flex gap-3 justify-end">
              <button onClick={() => { setShowNew(false); setError('') }}
                className="px-4 py-2 text-sm font-medium rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50">Cancel</button>
              <button onClick={createProject} disabled={!form.name.trim() || !form.path.trim() || creating}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-orange-500 hover:bg-orange-600 disabled:bg-gray-200 text-white disabled:text-gray-400 transition-colors">
                {creating ? 'Creating...' : 'Create Project'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
