'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { useState, useEffect, useCallback } from 'react'

const AUTH = { 'Authorization': 'Bearer modelmesh_local_dev_key', 'Content-Type': 'application/json' }

interface SettingValue {
  key: string
  value: string
  updated_at: string | null
}

const SETTING_FIELDS = [
  {
    key: 'comfyui_dir',
    label: 'ComfyUI Directory',
    placeholder: 'E:\\AI_Models\\ComfyUI',
    help: 'Full path to your ComfyUI installation. Leave blank to disable auto-launch.',
    type: 'path',
  },
  {
    key: 'comfyui_python',
    label: 'Python Executable',
    placeholder: 'C:\\Python313\\python.exe',
    help: 'Python used to run ComfyUI. Leave blank to use system python.',
    type: 'path',
  },
  {
    key: 'comfyui_url',
    label: 'ComfyUI URL',
    placeholder: 'http://localhost:8188',
    help: 'URL where ComfyUI API is reachable. Can also be set via COMFYUI_URL in .env.',
    type: 'url',
  },
  {
    key: 'comfyui_gpu_devices',
    label: 'GPU Devices (CUDA_VISIBLE_DEVICES)',
    placeholder: '0',
    help: 'Comma-separated GPU indices. "0" = first GPU, "1,0" = both GPUs with second preferred.',
    type: 'text',
  },
  {
    key: 'default_image_provider',
    label: 'Default Image Provider',
    placeholder: 'gemini',
    help: 'Which provider to default to: "gemini" (cloud) or "comfyui" (local).',
    type: 'select',
    options: [
      { value: 'gemini', label: 'Gemini (Cloud)' },
      { value: 'comfyui', label: 'ComfyUI (Local)' },
    ],
  },
  {
    key: 'default_workflow',
    label: 'Default Workflow',
    placeholder: 'sdxl-standard',
    help: 'Default ComfyUI workflow template when generating locally.',
    type: 'text',
  },
]

export default function ImageSettingsTab() {
  const [settings, setSettings] = useState<Record<string, SettingValue>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)
  const [comfyStatus, setComfyStatus] = useState<'online' | 'offline' | 'checking'>('checking')
  const [dirty, setDirty] = useState<Record<string, string>>({})
  const [workflows, setWorkflows] = useState<any[]>([])

  const fetchSettings = useCallback(async () => {
    try {
      const [settingsRes, statusRes, wfRes] = await Promise.all([
        fetch(`${API_BASE}/v1/settings/app`, { headers: AUTH }).then(r => r.json()),
        fetch(`${API_BASE}/v1/comfyui/status`, { headers: AUTH }).then(r => r.json()).catch(() => ({ status: 'offline' })),
        fetch(`${API_BASE}/v1/workflows`, { headers: AUTH }).then(r => r.json()).catch(() => ({ data: [] })),
      ])
      setSettings(settingsRes.data || {})
      setComfyStatus(statusRes.status === 'online' ? 'online' : 'offline')
      setWorkflows(wfRes.data || [])
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchSettings() }, [fetchSettings])

  const saveSetting = async (key: string) => {
    const value = dirty[key]
    if (value === undefined) return
    setSaving(key)
    try {
      const res = await fetch(`${API_BASE}/v1/settings/app/${key}`, {
        method: 'PUT', headers: AUTH,
        body: JSON.stringify({ value }),
      })
      const updated = await res.json()
      setSettings(prev => ({ ...prev, [key]: updated }))
      setDirty(prev => { const n = { ...prev }; delete n[key]; return n })
    } finally {
      setSaving(null)
    }
  }

  const getValue = (key: string) => {
    if (key in dirty) return dirty[key]
    return settings[key]?.value || ''
  }

  const setDirtyValue = (key: string, value: string) => {
    setDirty(prev => ({ ...prev, [key]: value }))
  }

  const hasDirty = Object.keys(dirty).length > 0

  const saveAll = async () => {
    for (const key of Object.keys(dirty)) {
      await saveSetting(key)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="flex gap-1.5">
          {[0, 1, 2].map(i => (
            <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Image Generation</h2>
          <p className="text-sm text-gray-500 mt-1">
            Configure ComfyUI for local image generation, or use Gemini cloud.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* ComfyUI status */}
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border ${
            comfyStatus === 'online'
              ? 'bg-green-50 border-green-200 text-green-700'
              : comfyStatus === 'checking'
              ? 'bg-yellow-50 border-yellow-200 text-yellow-700'
              : 'bg-red-50 border-red-200 text-red-600'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${
              comfyStatus === 'online' ? 'bg-green-500' : comfyStatus === 'checking' ? 'bg-yellow-400 animate-pulse' : 'bg-red-400'
            }`} />
            ComfyUI {comfyStatus}
          </div>
          {hasDirty && (
            <button
              onClick={saveAll}
              className="px-4 py-1.5 bg-orange-500 hover:bg-orange-600 text-white text-xs font-medium rounded-lg transition-colors"
            >
              Save All
            </button>
          )}
        </div>
      </div>

      {/* Settings form */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 divide-y divide-gray-200 dark:divide-gray-700">
        {SETTING_FIELDS.map(field => {
          const value = getValue(field.key)
          const isDirty = field.key in dirty

          return (
            <div key={field.key} className="px-5 py-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <label className="text-sm font-medium text-gray-900 dark:text-white">{field.label}</label>
                  <p className="text-xs text-gray-500 mt-0.5">{field.help}</p>
                  <div className="mt-2 flex items-center gap-2">
                    {field.type === 'select' && field.options ? (
                      <select
                        value={value}
                        onChange={e => setDirtyValue(field.key, e.target.value)}
                        className="flex-1 rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white px-3 py-2 text-sm focus:ring-orange-400 focus:border-orange-400"
                      >
                        {field.options.map(opt => (
                          <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type="text"
                        value={value}
                        onChange={e => setDirtyValue(field.key, e.target.value)}
                        placeholder={field.placeholder}
                        className={`flex-1 rounded-lg border px-3 py-2 text-sm font-mono focus:ring-orange-400 focus:border-orange-400 dark:bg-gray-700 dark:text-white ${
                          isDirty ? 'border-orange-300 dark:border-orange-600' : 'border-gray-300 dark:border-gray-600'
                        }`}
                      />
                    )}
                    <button
                      onClick={() => saveSetting(field.key)}
                      disabled={!isDirty || saving === field.key}
                      className="px-3 py-2 text-xs font-medium rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-30 transition-colors"
                    >
                      {saving === field.key ? '...' : 'Save'}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Available workflows */}
      {workflows.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Available Workflows</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {workflows.map((wf: any) => (
              <div key={wf.id} className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-900 dark:text-white">{wf.name}</span>
                  <span className="text-xs px-1.5 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-500 rounded">{wf.category}</span>
                </div>
                <p className="text-xs text-gray-500 mt-1">{wf.description}</p>
                <div className="flex items-center gap-2 mt-2 text-xs text-gray-400">
                  <span>Default: <code className="text-gray-600 dark:text-gray-300">{wf.default_checkpoint}</code></span>
                </div>
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {wf.sizes?.map((s: string) => (
                    <span key={s} className="text-xs px-1.5 py-0.5 bg-gray-50 dark:bg-gray-700 text-gray-500 rounded">{s}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-400 mt-2">
            💡 Add custom workflows by placing .json files in <code>data/workflows/</code>. They appear here automatically.
          </p>
        </div>
      )}
    </div>
  )
}
