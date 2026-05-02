'use client'

import { useEffect } from 'react'

const FLAG_KEY = 'devforgeai_chunk_reload_once'
const LAST_RELOAD_AT_KEY = 'devforgeai_chunk_reload_last_at'
const MAX_AUTO_RELOADS_KEY = 'devforgeai_chunk_reload_count'
const RELOAD_COOLDOWN_MS = 5 * 60 * 1000
const MAX_AUTO_RELOADS_PER_TAB = 2

function isChunkLoadErrorMessage(message: string): boolean {
  const m = (message || '').toLowerCase()
  return (
    m.includes('chunkloaderror') ||
    (m.includes('loading chunk') && m.includes('failed')) ||
    (m.includes('/_next/static/chunks/') && m.includes('timeout'))
  )
}

export default function ChunkErrorRecovery() {
  useEffect(() => {
    // In development, Next.js HMR and transient chunk rebuilds are expected.
    // Auto-reloading here can create a perpetual refresh loop.
    if (process.env.NODE_ENV !== 'production') return

    const maybeReload = (message: string) => {
      if (!isChunkLoadErrorMessage(message)) return
      if (sessionStorage.getItem(FLAG_KEY) === '1') return
      const now = Date.now()
      const lastReloadAt = Number(sessionStorage.getItem(LAST_RELOAD_AT_KEY) || 0)
      if (Number.isFinite(lastReloadAt) && lastReloadAt > 0 && (now - lastReloadAt) < RELOAD_COOLDOWN_MS) return
      const priorCount = Number(sessionStorage.getItem(MAX_AUTO_RELOADS_KEY) || 0)
      if (Number.isFinite(priorCount) && priorCount >= MAX_AUTO_RELOADS_PER_TAB) return
      sessionStorage.setItem(FLAG_KEY, '1')
      sessionStorage.setItem(LAST_RELOAD_AT_KEY, String(now))
      sessionStorage.setItem(MAX_AUTO_RELOADS_KEY, String((Number.isFinite(priorCount) ? priorCount : 0) + 1))
      window.location.reload()
    }

    const onError = (event: ErrorEvent) => {
      maybeReload(event?.message || '')
    }

    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      const reason: any = event?.reason
      const msg =
        (typeof reason === 'string' && reason) ||
        reason?.message ||
        String(reason || '')
      maybeReload(msg)
    }

    window.addEventListener('error', onError)
    window.addEventListener('unhandledrejection', onUnhandledRejection)

    return () => {
      window.removeEventListener('error', onError)
      window.removeEventListener('unhandledrejection', onUnhandledRejection)
      // Intentionally keep guard flags in sessionStorage to avoid reload loops
      // across unmount/mount cycles in the same browser tab.
    }
  }, [])

  return null
}
