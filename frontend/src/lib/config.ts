/**
 * Dynamic API configuration for DevForgeAI.
 * 
 * Auto-detects backend URL from the browser's current hostname.
 * This means remote access (Tailscale, LAN) works automatically.
 *
 * Override: set NEXT_PUBLIC_API_URL in .env.local
 */

const BACKEND_PORT = '19000'

/**
 * Returns the backend API base URL. Always call this — don't cache the result
 * at module scope, or Next.js will inline the SSR value.
 */
export function getApiBase(): string {
  if (typeof window !== 'undefined') {
    return `${window.location.protocol}//${window.location.hostname}:${BACKEND_PORT}`
  }
  return `http://localhost:${BACKEND_PORT}`
}

/** Shorthand — use in 'use client' components. */
export const API_KEY = 'modelmesh_local_dev_key'

/** Build auth headers. Call at request time, not module scope. */
export function getAuthHeaders(): Record<string, string> {
  return {
    'Authorization': `Bearer ${API_KEY}`,
    'Content-Type': 'application/json',
  }
}

// Legacy compat — these are evaluated at import time.
// In 'use client' components, window exists so they work.
// In SSR, they fall back to localhost (but SSR doesn't make API calls).
export const API_BASE = typeof window !== 'undefined'
  ? `${window.location.protocol}//${window.location.hostname}:${BACKEND_PORT}`
  : `http://localhost:${BACKEND_PORT}`

export const AUTH_HEADERS = {
  'Authorization': `Bearer ${API_KEY}`,
  'Content-Type': 'application/json',
}
