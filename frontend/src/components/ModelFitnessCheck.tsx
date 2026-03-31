'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'

import { useState, useEffect, useCallback } from 'react'


interface FitnessResult {
  ok: boolean
  is_cloud: boolean
  verdict: string
  label: string
  detail: string
  vram_needed_mb: number
  vram_free_mb: number
  best_gpu_free_mb: number
  already_loaded: boolean
  recommendation: string | null
  gpus?: Array<{ name: string; vram_total: number; vram_free: number; utilization: number }>
}

const VERDICT_STYLES: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  cloud:      { bg: 'bg-blue-50 dark:bg-blue-900/20',   border: 'border-blue-200 dark:border-blue-700',   text: 'text-blue-700 dark:text-blue-300',   icon: '☁️' },
  loaded:     { bg: 'bg-green-50 dark:bg-green-900/20', border: 'border-green-200 dark:border-green-700', text: 'text-green-700 dark:text-green-300', icon: '✅' },
  fits:       { bg: 'bg-green-50 dark:bg-green-900/20', border: 'border-green-200 dark:border-green-700', text: 'text-green-700 dark:text-green-300', icon: '✅' },
  fits_split: { bg: 'bg-yellow-50 dark:bg-yellow-900/20', border: 'border-yellow-200 dark:border-yellow-700', text: 'text-yellow-700 dark:text-yellow-300', icon: '⚠️' },
  tight:      { bg: 'bg-orange-50 dark:bg-orange-900/20', border: 'border-orange-200 dark:border-orange-700', text: 'text-orange-700 dark:text-orange-300', icon: '⚠️' },
  too_large:  { bg: 'bg-red-50 dark:bg-red-900/20',     border: 'border-red-200 dark:border-red-700',     text: 'text-red-700 dark:text-red-300',     icon: '❌' },
  unknown:    { bg: 'bg-gray-50 dark:bg-gray-800',      border: 'border-gray-200 dark:border-gray-700',   text: 'text-gray-600 dark:text-gray-400',   icon: '❓' },
}

interface Props {
  modelId: string           // The Ollama model_id to check
  showGpuBar?: boolean      // Show VRAM bar
  compact?: boolean         // Compact single-line mode
}

export function ModelFitnessCheck({ modelId, showGpuBar = true, compact = false }: Props) {
  const [result, setResult] = useState<FitnessResult | null>(null)
  const [loading, setLoading] = useState(false)

  const check = useCallback(async () => {
    if (!modelId) return
    setLoading(true)
    try {
      const res = await fetch(`${API_BASE}/v1/hardware/check/${encodeURIComponent(modelId)}`, { headers: AUTH_HEADERS })
        .then(r => r.json())
      setResult(res)
    } catch {
      setResult(null)
    } finally {
      setLoading(false)
    }
  }, [modelId])

  useEffect(() => {
    const timer = setTimeout(check, 400) // debounce
    return () => clearTimeout(timer)
  }, [check])

  if (!modelId) return null
  if (loading) return (
    <div className="flex items-center gap-2 text-xs text-gray-400 mt-1">
      <span className="w-3 h-3 border border-gray-300 border-t-orange-400 rounded-full animate-spin" />
      Checking hardware compatibility...
    </div>
  )
  if (!result) return null

  const style = VERDICT_STYLES[result.verdict] || VERDICT_STYLES.unknown

  if (compact) {
    return (
      <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border font-medium ${style.bg} ${style.border} ${style.text}`}>
        {style.icon} {result.label.replace(/^[✅⚠️❌☁️❓]\s*/, '')}
      </span>
    )
  }

  return (
    <div className={`mt-2 p-3 rounded-xl border ${style.bg} ${style.border}`}>
      <div className="flex items-start gap-2">
        <span className="text-base flex-shrink-0 mt-0.5">{style.icon}</span>
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-semibold ${style.text}`}>{result.label}</p>
          <p className={`text-xs mt-0.5 ${style.text} opacity-80`}>{result.detail}</p>

          {/* VRAM bar */}
          {showGpuBar && !result.is_cloud && result.gpus && result.gpus.length > 0 && (
            <div className="mt-2 space-y-1.5">
              {result.gpus.map((gpu, i) => {
                const usedPct = Math.round((gpu.vram_total - gpu.vram_free) / gpu.vram_total * 100)
                const neededPct = Math.min(100, Math.round(result.vram_needed_mb / gpu.vram_total * 100))
                return (
                  <div key={i}>
                    <div className="flex justify-between text-xs opacity-70 mb-0.5">
                      <span>{gpu.name} (GPU {i})</span>
                      <span>{Math.round(gpu.vram_free / 1024)}GB free / {Math.round(gpu.vram_total / 1024)}GB total</span>
                    </div>
                    <div className="relative h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                      {/* Used VRAM */}
                      <div className="absolute left-0 top-0 h-full bg-blue-400 dark:bg-blue-500 rounded-full transition-all"
                        style={{ width: `${usedPct}%` }} />
                      {/* Model would need this much */}
                      {result.vram_needed_mb > 0 && (
                        <div className={`absolute top-0 h-full rounded-full opacity-60 transition-all ${result.ok ? 'bg-green-400' : 'bg-red-400'}`}
                          style={{ left: `${usedPct}%`, width: `${Math.min(neededPct, 100 - usedPct)}%` }} />
                      )}
                    </div>
                  </div>
                )
              })}
              <div className="flex items-center gap-3 text-xs opacity-60 mt-1">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-blue-400 inline-block" /> In use</span>
                {result.vram_needed_mb > 0 && (
                  <span className={`flex items-center gap-1`}>
                    <span className={`w-2 h-2 rounded inline-block ${result.ok ? 'bg-green-400' : 'bg-red-400'}`} />
                    This model (~{Math.round(result.vram_needed_mb / 1024)}GB)
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Recommendation */}
          {result.recommendation && (
            <p className="text-xs mt-2 text-red-700 dark:text-red-300 font-medium">
              💡 {result.recommendation}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}


// ─── GPU Status Dashboard Widget ──────────────────────────────────────────────
interface HardwareStatus {
  gpus: Array<{ index: number; name: string; vram_total: number; vram_used: number; vram_free: number; utilization: number; temperature: number }>
  total_vram_mb: number
  total_free_mb: number
  ollama_loaded: string[]
}

export function GpuStatusWidget() {
  const [hw, setHw] = useState<HardwareStatus | null>(null)

  useEffect(() => {
    const fetch_ = async () => {
      try {
        const res = await fetch(`${API_BASE}/v1/hardware/status`, { headers: AUTH_HEADERS }).then(r => r.json())
        setHw(res)
      } catch { /* silent */ }
    }
    fetch_()
    const interval = setInterval(fetch_, 10000)
    return () => clearInterval(interval)
  }, [])

  if (!hw || hw.gpus.length === 0) return null

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">GPU / VRAM</h3>
        {hw.ollama_loaded.length > 0 && (
          <span className="text-xs text-gray-400">{hw.ollama_loaded.length} model{hw.ollama_loaded.length > 1 ? 's' : ''} loaded</span>
        )}
      </div>
      <div className="space-y-3">
        {hw.gpus.map(gpu => {
          const usedPct = Math.round(gpu.vram_used / gpu.vram_total * 100)
          const freePct = 100 - usedPct
          const hot = gpu.temperature > 80
          return (
            <div key={gpu.index}>
              <div className="flex justify-between items-center mb-1">
                <span className="text-xs font-medium text-gray-600 dark:text-gray-300 truncate">{gpu.name}</span>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {gpu.temperature > 0 && (
                    <span className={`text-xs ${hot ? 'text-red-500' : 'text-gray-400'}`}>{gpu.temperature}°C</span>
                  )}
                  <span className="text-xs text-gray-400">{Math.round(gpu.vram_free / 1024)}GB free</span>
                </div>
              </div>
              <div className="h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all ${usedPct > 90 ? 'bg-red-500' : usedPct > 70 ? 'bg-yellow-500' : 'bg-blue-500'}`}
                  style={{ width: `${usedPct}%` }} />
              </div>
              <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                <span>{Math.round(gpu.vram_used / 1024)}GB used</span>
                <span>{Math.round(gpu.vram_total / 1024)}GB total · {gpu.utilization}% util</span>
              </div>
            </div>
          )
        })}
        {hw.ollama_loaded.length > 0 && (
          <div className="pt-2 border-t border-gray-100 dark:border-gray-700">
            <p className="text-xs text-gray-400 mb-1">Loaded in Ollama:</p>
            <div className="flex flex-wrap gap-1">
              {hw.ollama_loaded.map(m => (
                <span key={m} className="text-xs px-2 py-0.5 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded-full font-mono">{m}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}