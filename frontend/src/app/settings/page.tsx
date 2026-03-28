'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api'

interface MemoryFile {
  id: string
  name: string
  content: string
  description?: string
  created_at: string
  updated_at: string
}

interface UserProfile {
  id: string
  name: string
  email?: string
  preferences: Record<string, any>
}

export default function SettingsPage() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [memoryFiles, setMemoryFiles] = useState<MemoryFile[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'profile' | 'memory' | 'preferences'>('profile')
  const [editingFile, setEditingFile] = useState<MemoryFile | null>(null)
  const [newFileName, setNewFileName] = useState('')

  useEffect(() => {
    async function fetchData() {
      try {
        const [profileRes, memoryRes] = await Promise.all([
          fetch('http://localhost:19000/v1/user', {
            headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
          }).then(r => r.json()),
          fetch('http://localhost:19000/v1/memory', {
            headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
          }).then(r => r.json())
        ])
        setProfile(profileRes)
        setMemoryFiles(memoryRes.data || [])
      } catch (e) {
        console.error('Failed to fetch:', e)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  const createMemoryFile = async (name: string) => {
    try {
      const res = await fetch('http://localhost:19000/v1/memory', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer modelmesh_local_dev_key'
        },
        body: JSON.stringify({ name, content: '# ' + name + '\n\nAdd your content here...' })
      })
      const newFile = await res.json()
      setMemoryFiles([...memoryFiles, newFile])
      setNewFileName('')
    } catch (e) {
      console.error('Failed to create:', e)
    }
  }

  const updateMemoryFile = async (file: MemoryFile) => {
    try {
      await fetch(`http://localhost:19000/v1/memory/${file.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer modelmesh_local_dev_key'
        },
        body: JSON.stringify({ content: file.content })
      })
      setEditingFile(null)
    } catch (e) {
      console.error('Failed to update:', e)
    }
  }

  const deleteMemoryFile = async (fileId: string) => {
    try {
      await fetch(`http://localhost:19000/v1/memory/${fileId}`, {
        method: 'DELETE',
        headers: { 'Authorization': 'Bearer modelmesh_local_dev_key' }
      })
      setMemoryFiles(memoryFiles.filter(f => f.id !== fileId))
    } catch (e) {
      console.error('Failed to delete:', e)
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
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage your profile, memory files, and preferences
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('profile')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'profile'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Profile
          </button>
          <button
            onClick={() => setActiveTab('memory')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'memory'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Memory Files
          </button>
          <button
            onClick={() => setActiveTab('preferences')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'preferences'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Preferences
          </button>
        </nav>
      </div>

      {/* Profile Tab */}
      {activeTab === 'profile' && (
        <div className="bg-white shadow sm:rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <h3 className="text-lg font-medium text-gray-900">User Profile</h3>
            <p className="mt-1 text-sm text-gray-500">
              This information helps personalize your AI interactions.
            </p>
            <div className="mt-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">Name</label>
                <input
                  type="text"
                  value={profile?.name || ''}
                  onChange={(e) => setProfile({ ...profile!, name: e.target.value })}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">Email</label>
                <input
                  type="email"
                  value={profile?.email || ''}
                  onChange={(e) => setProfile({ ...profile!, email: e.target.value })}
                  className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                />
              </div>
              <button
                type="button"
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700"
              >
                Save Profile
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Memory Files Tab */}
      {activeTab === 'memory' && (
        <div className="space-y-6">
          <div className="bg-white shadow sm:rounded-lg">
            <div className="px-4 py-5 sm:p-6">
              <h3 className="text-lg font-medium text-gray-900">Memory Files</h3>
              <p className="mt-1 text-sm text-gray-500">
                Memory files are injected into AI system prompts to provide context and personalization.
              </p>

              {/* Create new file */}
              <div className="mt-4 flex gap-2">
                <input
                  type="text"
                  placeholder="New file name (e.g., USER.md, CONTEXT.md)"
                  value={newFileName}
                  onChange={(e) => setNewFileName(e.target.value)}
                  className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
                />
                <button
                  onClick={() => newFileName && createMemoryFile(newFileName)}
                  disabled={!newFileName}
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300"
                >
                  Create
                </button>
              </div>
            </div>
          </div>

          {/* Memory files list */}
          {memoryFiles.map((file) => (
            <div key={file.id} className="bg-white shadow sm:rounded-lg">
              <div className="px-4 py-5 sm:p-6">
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="text-sm font-medium text-gray-900">{file.name}</h4>
                    {file.description && (
                      <p className="text-sm text-gray-500">{file.description}</p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setEditingFile(file)}
                      className="text-sm text-indigo-600 hover:text-indigo-500"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => deleteMemoryFile(file.id)}
                      className="text-sm text-red-600 hover:text-red-500"
                    >
                      Delete
                    </button>
                  </div>
                </div>

                {editingFile?.id === file.id ? (
                  <div className="mt-4">
                    <textarea
                      value={file.content}
                      onChange={(e) => {
                        const updated = memoryFiles.map(f => 
                          f.id === file.id ? { ...f, content: e.target.value } : f
                        )
                        setMemoryFiles(updated)
                      }}
                      rows={10}
                      className="block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 font-mono text-sm"
                    />
                    <div className="mt-2 flex gap-2">
                      <button
                        onClick={() => updateMemoryFile(file)}
                        className="inline-flex items-center px-3 py-1.5 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700"
                      >
                        Save
                      </button>
                      <button
                        onClick={() => setEditingFile(null)}
                        className="inline-flex items-center px-3 py-1.5 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <pre className="mt-2 text-sm text-gray-600 whitespace-pre-wrap line-clamp-3">
                    {file.content}
                  </pre>
                )}
              </div>
            </div>
          ))}

          {memoryFiles.length === 0 && (
            <div className="text-center py-8">
              <p className="text-sm text-gray-500">No memory files yet. Create one to personalize your AI interactions.</p>
            </div>
          )}
        </div>
      )}

      {/* Preferences Tab */}
      {activeTab === 'preferences' && (
        <div className="bg-white shadow sm:rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <h3 className="text-lg font-medium text-gray-900">Learned Preferences</h3>
            <p className="mt-1 text-sm text-gray-500">
              These preferences are learned from your chat interactions.
            </p>
            <div className="mt-4 text-sm text-gray-500">
              Preferences will appear here as you interact with the AI.
            </div>
          </div>
        </div>
      )}
    </div>
  )
}