'use client'

/**
 * Runs a one-time backend port probe on app startup so the correct API base
 * URL is cached in sessionStorage before any API calls are made.
 *
 * Handles the scenario where a stale backend process occupies the primary port
 * (19001) but is missing newer routes — the probe finds the healthy port
 * (19000) and all subsequent getApiBase() calls return the correct URL.
 */

import { useEffect } from 'react'
import { probeAndCacheApiBase } from '@/lib/config'

export default function BackendProbe() {
  useEffect(() => {
    probeAndCacheApiBase().catch(() => { /* silent — fallback already set */ })
  }, [])
  return null
}
