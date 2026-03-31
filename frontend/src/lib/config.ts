/**
 * Dynamic API base URL - auto-detects backend from browser hostname.
 *
 * When accessing DevForgeAI locally:    http://localhost:3001  → http://localhost:19000
 * When accessing via Tailscale/LAN:     http://100.106.217.99:3001 → http://100.106.217.99:19000
 * When accessing via custom domain:     http://forge.example.com:3001 → http://forge.example.com:19000
 *
 * Override with NEXT_PUBLIC_API_URL env var if needed.
 */

/**
 * Lazy getter — recomputes on every access so it always reflects
 * the current browser hostname (important for remote/Tailscale access).
 * On the server side (SSR), falls back to localhost.
 */
export function getApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL
  }
  if (typeof window === 'undefined') {
    return 'http://localhost:19000'
  }
  const { protocol, hostname } = window.location
  return `${protocol}//${hostname}:19000`
}

// For backward compat — most files import API_BASE as a const.
// This is fine for client components (window exists at import time).
// For SSR-sensitive code, call getApiBase() directly.
export const API_BASE = typeof window !== 'undefined'
  ? getApiBase()
  : 'http://localhost:19000'

export const API_KEY = process.env.NEXT_PUBLIC_MODELMESH_API_KEY || 'modelmesh_local_dev_key'
export const AUTH_HEADERS = {
  'Authorization': `Bearer ${API_KEY}`,
  'Content-Type': 'application/json',
}
