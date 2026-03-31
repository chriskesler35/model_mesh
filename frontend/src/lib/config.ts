/**
 * Dynamic API base URL — auto-detects backend from browser hostname.
 *
 * When accessing DevForgeAI locally:    http://localhost:3001  → http://localhost:19000
 * When accessing via Tailscale/LAN:     http://100.106.217.99:3001 → http://100.106.217.99:19000
 * When accessing via custom domain:     http://forge.example.com:3001 → http://forge.example.com:19000
 *
 * Override with NEXT_PUBLIC_API_URL env var if needed.
 */

function getApiBase(): string {
  // Allow explicit override via env
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL
  }

  // Server-side rendering — use localhost
  if (typeof window === 'undefined') {
    return 'http://localhost:19000'
  }

  // Client-side — derive from current hostname
  const { protocol, hostname } = window.location
  return `${protocol}//${hostname}:19000`
}

export const API_BASE = getApiBase()
export const API_KEY = process.env.NEXT_PUBLIC_MODELMESH_API_KEY || 'modelmesh_local_dev_key'
export const AUTH_HEADERS = {
  'Authorization': `Bearer ${API_KEY}`,
  'Content-Type': 'application/json',
}
