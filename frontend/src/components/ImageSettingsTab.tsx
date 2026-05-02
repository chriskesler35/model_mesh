'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { useState, useEffect, useCallback } from 'react'


interface SettingValue {
  key: string
  value: string
  updated_at: string | null
}

interface ComfyEndpoint {
  url: string
  status: 'online' | 'offline'
  queue_running: number
  queue_pending: number
  queue_total: number
}

interface ComfyEndpointsResponse {
  data: ComfyEndpoint[]
  active_url?: string | null
}

interface RuntimeCapabilities {
  image_providers?: {
    'comfyui-local'?: boolean
    'gemini-imagen'?: boolean
  }
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
    help: 'URL where ComfyUI API is reachable. You can also provide multiple URLs (comma-separated), e.g. http://127.0.0.1:8188,http://127.0.0.1:8189.',
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
    key: 'comfyui_launch_args',
    label: 'ComfyUI Launch Arguments',
    placeholder: '--listen 0.0.0.0',
    help: 'Optional arguments passed after "python main.py". Leave blank to use DevForgeAI defaults. For your batch file, use "--listen 0.0.0.0".',
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
  const [comfyEndpoints, setComfyEndpoints] = useState<ComfyEndpoint[]>([])
  const [activeComfyUrl, setActiveComfyUrl] = useState<string | null>(null)
  const [runtimeCapabilities, setRuntimeCapabilities] = useState<RuntimeCapabilities | null>(null)

  const fetchEndpoints = useCallback(async () => {
    try {
      const res: ComfyEndpointsResponse = await fetch(`${API_BASE}/v1/comfyui/endpoints`, { headers: AUTH_HEADERS })
        .then(r => r.json())
        .catch(() => ({ data: [], active_url: null } as ComfyEndpointsResponse))
      setComfyEndpoints(res.data || [])
      setActiveComfyUrl(res.active_url || null)
    } catch {
      // ignore
    }
  }, [])

  const fetchSettings = useCallback(async () => {
    try {
      const [settingsRes, statusRes, wfRes, endpointsRes, runtimeCapabilitiesRes] = await Promise.all([
        fetch(`${API_BASE}/v1/settings/app`, { headers: AUTH_HEADERS }).then(r => r.json()),
        fetch(`${API_BASE}/v1/comfyui/status`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ status: 'offline' })),
        fetch(`${API_BASE}/v1/workflows`, { headers: AUTH_HEADERS }).then(r => r.json()).catch(() => ({ data: [] })),
        fetch(`${API_BASE}/v1/comfyui/endpoints`, { headers: AUTH_HEADERS })
          .then(r => r.json())
          .catch(() => ({ data: [], active_url: null } as ComfyEndpointsResponse)),
        fetch(`${API_BASE}/v1/runtime/capabilities`, { headers: AUTH_HEADERS })
          .then(r => r.json())
          .catch(() => ({} as RuntimeCapabilities)),
      ])
      setSettings(settingsRes.data || {})
      setComfyStatus(statusRes.status === 'online' ? 'online' : 'offline')
      setWorkflows(wfRes.data || [])
      setComfyEndpoints(endpointsRes.data || [])
      setActiveComfyUrl(endpointsRes.active_url || null)
      setRuntimeCapabilities(runtimeCapabilitiesRes || null)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  const comfyImageProviderAvailable = runtimeCapabilities?.image_providers?.['comfyui-local'] ?? (comfyStatus === 'online')

  useEffect(() => {
    if (comfyImageProviderAvailable) return
    const persisted = settings['default_image_provider']?.value || ''
    const current = dirty['default_image_provider'] ?? persisted
    if (current === 'comfyui') {
      setDirty(prev => ({ ...prev, default_image_provider: 'gemini' }))
    }
  }, [comfyImageProviderAvailable, settings, dirty])

  useEffect(() => { fetchSettings() }, [fetchSettings])

  // Auto-refresh endpoint queue depth every 4 s while the tab is open
  useEffect(() => {
    const id = setInterval(() => { fetchEndpoints() }, 4000)
    return () => clearInterval(id)
  }, [fetchEndpoints])

  const saveSetting = async (key: string) => {
    const value = dirty[key]
    if (value === undefined) return
    setSaving(key)
    try {
      const res = await fetch(`${API_BASE}/v1/settings/app/${key}`, {
        method: 'PUT', headers: AUTH_HEADERS,
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
                        {field.options.map(opt => {
                          const isComfyOption = field.key === 'default_image_provider' && opt.value === 'comfyui'
                          const disabled = isComfyOption && !comfyImageProviderAvailable
                          return (
                            <option key={opt.value} value={opt.value} disabled={disabled}>
                              {disabled ? `${opt.label} (Unavailable)` : opt.label}
                            </option>
                          )
                        })}
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

      {/* ComfyUI endpoint health */}
      {comfyEndpoints.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div>
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">ComfyUI Endpoints</h3>
              <p className="text-xs text-gray-500 mt-0.5">Live queue depth and active routing target.</p>
            </div>
            <button
              onClick={fetchEndpoints}
              className="px-2.5 py-1 text-xs font-medium rounded-md border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
            >
              Refresh
            </button>
          </div>

          <div className="space-y-2">
            {comfyEndpoints.map((ep) => {
              const isActive = activeComfyUrl === ep.url
              return (
                <div
                  key={ep.url}
                  className={`rounded-lg border px-3 py-2 ${
                    isActive
                      ? 'border-orange-300 bg-orange-50/50 dark:border-orange-700 dark:bg-orange-900/20'
                      : 'border-gray-200 dark:border-gray-700'
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`inline-block w-2 h-2 rounded-full ${ep.status === 'online' ? 'bg-green-500' : 'bg-red-400'}`} />
                        <span className="text-xs font-mono text-gray-700 dark:text-gray-200 truncate">{ep.url}</span>
                        {isActive && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-orange-100 text-orange-700 dark:bg-orange-800/40 dark:text-orange-300">active</span>
                        )}
                      </div>
                    </div>
                    <span className={`text-[11px] px-1.5 py-0.5 rounded ${
                      ep.status === 'online'
                        ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                        : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                    }`}>{ep.status}</span>
                  </div>

                  <div className="mt-2 grid grid-cols-3 gap-2 text-[11px]">
                    <div className="rounded bg-gray-50 dark:bg-gray-700/40 px-2 py-1">
                      <span className="text-gray-500">Total</span>
                      <span className="ml-1 font-semibold text-gray-700 dark:text-gray-200">{ep.queue_total}</span>
                    </div>
                    <div className="rounded bg-gray-50 dark:bg-gray-700/40 px-2 py-1">
                      <span className="text-gray-500">Pending</span>
                      <span className="ml-1 font-semibold text-gray-700 dark:text-gray-200">{ep.queue_pending}</span>
                    </div>
                    <div className="rounded bg-gray-50 dark:bg-gray-700/40 px-2 py-1">
                      <span className="text-gray-500">Running</span>
                      <span className="ml-1 font-semibold text-gray-700 dark:text-gray-200">{ep.queue_running}</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

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
            Workflows from <code>data/workflows/</code> and your ComfyUI installation are shown automatically.
          </p>
        </div>
      )}
    </div>
  )
}
