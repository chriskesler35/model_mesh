'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'

// SandboxPanel stub — sandbox.tsx not yet implemented
const SandboxPanel = ({ projectId }: { projectId: string }) => (
  <div className="text-sm text-gray-500 py-8 text-center">Sandbox coming soon.</div>
)

const API_BASE = 'http://localhost:19000'
const AUTH = { 'Authorization': 'Bearer modelmesh_local_dev_key', 'Content-Type': 'application/json' }

interface FileNode { name: string; path: string; type: 'file' | 'dir'; size: number; children?: FileNode[] }

const FILE_ICONS: Record<string, string> = {
  py: '🐍', ts: '🔷', tsx: '🔷', js: '🟨', jsx: '🟨', json: '📋',
  md: '📝', txt: '📄', html: '🌐', css: '🎨', env: '🔒',
  gitignore: '🚫', toml: '⚙️', yaml: '⚙️', yml: '⚙️',
}

function fileIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() || ''
  return FILE_ICONS[ext] || '📄'
}

function FileTree({ nodes, onSelect, selected, depth = 0 }: {
  nodes: FileNode[]; onSelect: (n: FileNode) => void
  selected: string | null; depth?: number
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({})
  return (
    <div>
      {nodes.map(n => (
        <div key={n.path}>
          {n.type === 'dir' ? (
            <div>
              <button onClick={() => setOpen(o => ({ ...o, [n.path]: !o[n.path] }))}
                className="w-full flex items-center gap-1.5 px-2 py-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded text-left transition-colors"
                style={{ paddingLeft: `${8 + depth * 12}px` }}>
                <span className="text-gray-400 text-xs">{open[n.path] ? '▼' : '▶'}</span>
                <span className="text-sm">📁</span>
                <span className="text-sm text-gray-700 dark:text-gray-300">{n.name}</span>
              </button>
              {open[n.path] && n.children && (
                <FileTree nodes={n.children} onSelect={onSelect} selected={selected} depth={depth + 1} />
              )}
            </div>
          ) : (
            <button onClick={() => onSelect(n)}
              className={`w-full flex items-center gap-1.5 px-2 py-1 rounded text-left transition-colors ${
                selected === n.path
                  ? 'bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300'
                  : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400'
              }`}
              style={{ paddingLeft: `${8 + depth * 12}px` }}>
              <span className="text-sm">{fileIcon(n.name)}</span>
              <span className="text-sm truncate">{n.name}</span>
              <span className="ml-auto text-xs text-gray-300">{n.size > 1024 ? `${(n.size/1024).toFixed(1)}k` : `${n.size}b`}</span>
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

export default function ProjectDetailPage() {
  const { id } = useParams() as { id: string }
  const router = useRouter()

  const [project, setProject] = useState<any>(null)
  const [tree, setTree] = useState<FileNode[]>([])
  const [selectedFile, setSelectedFile] = useState<FileNode | null>(null)
  const [fileContent, setFileContent] = useState<string | null>(null)
  const [loadingFile, setLoadingFile] = useState(false)
  const [activeTab, setActiveTab] = useState<'files' | 'sandbox'>('files')
  const [sandboxSaving, setSandboxSaving] = useState(false)

  const setSandboxMode = async (mode: 'restricted' | 'full') => {
    setSandboxSaving(true)
    try {
      await fetch(`${API_BASE}/v1/projects/${id}/sandbox`, {
        method: 'POST', headers: AUTH, body: JSON.stringify({ mode })
      })
      setProject((p: any) => ({ ...p, sandbox_mode: mode }))
    } finally {
      setSandboxSaving(false)
    }
  }
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [saving, setSaving] = useState(false)

  const fetchProject = useCallback(async () => {
    const [proj, files] = await Promise.all([
      fetch(`${API_BASE}/v1/projects/${id}`, { headers: AUTH }).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/v1/projects/${id}/files`, { headers: AUTH }).then(r => r.json()).catch(() => ({ tree: [] })),
    ])
    if (!proj || proj.detail) { router.push('/projects'); return }
    setProject(proj)
    setEditName(proj.name)
    setEditDesc(proj.description || '')
    setTree(files.tree || [])
    setLoading(false)
  }, [id, router])

  useEffect(() => { fetchProject() }, [fetchProject])

  // Auto-refresh file tree when a Workbench session for this project completes
  useEffect(() => {
    let lastStatus: string | null = null
    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/v1/workbench/sessions`, { headers: AUTH })
        const data = await res.json()
        const mine = (data.data || []).find((s: any) => s.project_id === id)
        if (!mine) return
        const isActive = mine.status === 'running' || mine.status === 'pending'
        // When a session transitions from active -> done/failed, refresh the tree
        if (lastStatus && ['running', 'pending'].includes(lastStatus) && !isActive) {
          fetchProject()
        }
        lastStatus = mine.status
      } catch { /* ignore */ }
    }
    const timer = setInterval(poll, 4000)
    return () => clearInterval(timer)
  }, [id, fetchProject])

  // Auto-refresh file tree when a Workbench session for this project is active
  useEffect(() => {
    let lastStatus: string | null = null
    const poll = async () => {
      try {
        const res = await fetch(\/v1/workbench/sessions\, { headers: AUTH })
        const data = await res.json()
        const mine = (data.data || []).find((s: any) => s.project_id === id)
        if (!mine) return
        const isActive = mine.status === \'running\' || mine.status === \'pending\'
        // When a session transitions from active -> completed/failed, refresh the tree
        if (lastStatus && [\'running\', \'pending\'].includes(lastStatus) && !isActive) {
          fetchProject()
        }
        lastStatus = mine.status
      } catch { /* ignore */ }
    }
    const timer = setInterval(poll, 4000)
    return () => clearInterval(timer)
  }, [id, fetchProject])

  const openFile = async (node: FileNode) => {
    setSelectedFile(node)
    setFileContent(null)
    setLoadingFile(true)
    const res = await fetch(`${API_BASE}/v1/projects/${id}/files/read?file_path=${encodeURIComponent(node.path)}`, { headers: AUTH })
      .then(r => r.json()).catch(() => ({ content: 'Failed to load file.' }))
    setFileContent(res.content || '')
    setLoadingFile(false)
  }

  const saveProject = async () => {
    setSaving(true)
    await fetch(`${API_BASE}/v1/projects/${id}`, {
      method: 'PATCH', headers: AUTH,
      body: JSON.stringify({ name: editName, description: editDesc })
    })
    setProject((p: any) => ({ ...p, name: editName, description: editDesc }))
    setEditing(false)
    setSaving(false)
  }

  if (loading) return (
    <div className="flex justify-center py-16">
      <div className="flex gap-1.5">{[0,1,2].map(i => <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />)}</div>
    </div>
  )

  return (
    <div className="flex flex-col h-full -m-6 lg:-m-10">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-3 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
        <button onClick={() => router.push('/projects')}
          className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 transition-colors">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
        </button>
        <div className="flex-1 min-w-0">
          {editing ? (
            <div className="flex items-center gap-2">
              <input value={editName} onChange={e => setEditName(e.target.value)}
                className="text-sm font-semibold rounded border border-orange-400 px-2 py-0.5 dark:bg-gray-800 dark:text-white" />
              <input value={editDesc} onChange={e => setEditDesc(e.target.value)}
                placeholder="Description"
                className="text-sm rounded border border-gray-300 px-2 py-0.5 dark:bg-gray-800 dark:text-white flex-1" />
              <button onClick={saveProject} disabled={saving}
                className="px-2 py-1 text-xs bg-orange-500 text-white rounded">{saving ? '...' : 'Save'}</button>
              <button onClick={() => setEditing(false)} className="px-2 py-1 text-xs border border-gray-300 rounded text-gray-600">Cancel</button>
            </div>
          ) : (
            <div>
              <button onClick={() => setEditing(true)} className="text-sm font-semibold text-gray-900 dark:text-white hover:text-orange-600 transition-colors">
                {project.name}
              </button>
              <p className="text-xs text-gray-400 font-mono truncate">{project.path}</p>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`text-xs px-2 py-0.5 rounded-full ${project.path_exists ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'}`}>
            {project.path_exists ? '✓ path found' : '✗ path missing'}
          </span>

          {/* Sandbox mode toggle */}
          <div className="flex items-center gap-1 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
            <button
              onClick={() => setSandboxMode('restricted')}
              disabled={sandboxSaving}
              title="Restricted: agent confined to project folder"
              className={`px-2 py-1 text-xs font-medium transition-colors ${
                project.sandbox_mode !== 'full'
                  ? 'bg-green-100 text-green-700 dark:bg-green-900/40'
                  : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >🔒 Restricted</button>
            <button
              onClick={() => setSandboxMode('full')}
              disabled={sandboxSaving}
              title="Full Access: agent has unrestricted system access"
              className={`px-2 py-1 text-xs font-medium transition-colors ${
                project.sandbox_mode === 'full'
                  ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40'
                  : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >🔓 Full</button>
          </div>

          <button onClick={() => router.push(`/workbench?project=${id}`)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-500 hover:bg-orange-600 text-white text-xs font-medium rounded-lg transition-colors">
            🚀 Open in Workbench
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 px-6 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 flex-shrink-0">
        {([['files', '📁 Files'], ['sandbox', '🔒 Sandbox']] as const).map(([tab, label]) => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${activeTab === tab ? 'border-orange-500 text-orange-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {activeTab === 'sandbox' && (
          <div className="flex-1 overflow-y-auto p-4"><SandboxPanel projectId={id} /></div>
        )}
        {activeTab === 'files' && (
        <>
        {/* File tree */}
        <div className="w-56 flex-shrink-0 border-r border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 flex flex-col">
          <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Files</p>
            <button onClick={fetchProject} className="text-xs text-gray-400 hover:text-gray-600">↻</button>
          </div>
          <div className="flex-1 overflow-y-auto p-1">
            {tree.length === 0 ? (
              <div className="text-center py-8 text-xs text-gray-400">
                {project.path_exists ? 'Empty directory' : 'Path not found'}
              </div>
            ) : (
              <FileTree nodes={tree} onSelect={openFile} selected={selectedFile?.path || null} />
            )}
          </div>
        </div>

        {/* File content */}
        <div className="flex-1 flex flex-col min-w-0 bg-white dark:bg-gray-950">
          {!selectedFile ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center text-gray-400">
                <div className="text-5xl mb-3">📂</div>
                <p className="text-sm font-medium text-gray-600 dark:text-gray-300">{project.name}</p>
                <p className="text-xs mt-1">{project.description || 'Click a file to preview it'}</p>
                <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-left max-w-xs">
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                    <p className="font-medium text-gray-700 dark:text-gray-300">Template</p>
                    <p className="text-gray-500">{project.template}</p>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                    <p className="font-medium text-gray-700 dark:text-gray-300">Created</p>
                    <p className="text-gray-500">{new Date(project.created_at).toLocaleDateString()}</p>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 flex-shrink-0">
                <span className="text-sm">{fileIcon(selectedFile.name)}</span>
                <span className="text-sm font-mono text-gray-700 dark:text-gray-300">{selectedFile.path}</span>
                <span className="ml-auto text-xs text-gray-400">{selectedFile.size} bytes</span>
                <button onClick={() => { setSelectedFile(null); setFileContent(null) }} className="text-gray-400 hover:text-gray-600 ml-1">✕</button>
              </div>
              <div className="flex-1 overflow-auto p-4">
                {loadingFile ? (
                  <div className="flex justify-center py-12">
                    <div className="flex gap-1">{[0,1,2].map(i => <div key={i} className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.1}s` }} />)}</div>
                  </div>
                ) : (
                  <pre className="text-xs font-mono text-gray-700 dark:text-gray-200 whitespace-pre-wrap break-words leading-relaxed">
                    {fileContent}
                  </pre>
                )}
              </div>
            </>
          )}
        </div>
        </>
        )}
      </div>
    </div>
  )
}
