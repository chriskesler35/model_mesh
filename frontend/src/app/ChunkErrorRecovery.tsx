'use client'

import { useEffect } from 'react'

const FLAG_KEY = 'devforgeai_chunk_reload_once'

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
    const maybeReload = (message: string) => {
      if (!isChunkLoadErrorMessage(message)) return
      if (sessionStorage.getItem(FLAG_KEY) === '1') return
      sessionStorage.setItem(FLAG_KEY, '1')
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
      sessionStorage.removeItem(FLAG_KEY)
    }
  }, [])

  return null
}
