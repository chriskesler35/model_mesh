/**
 * Dynamic API configuration for DevForgeAI.
 *
 * Auto-detects backend URL from the browser's current hostname and the
 * known backend port. This avoids relying on Next.js rewrites for auth'd API
 * calls, because some runtime modes do not preserve Authorization headers.
 *
 * Override: set NEXT_PUBLIC_API_URL in .env.local
 *
 * Port detection: tries BACKEND_PORTS in order; uses the first that responds
 * with a 200 from /v1/health. Result is cached in sessionStorage so only one
 * probe per page session. This gracefully handles stale processes occupying
 * the primary port without the capabilities or other routes.
 */

const BACKEND_PORTS = ['19001']
const SESSION_KEY_DETECTED_BASE = 'devforge_detected_api_base'

function trimTrailingSlash(url: string): string {
  return url.replace(/\/+$/, '')
}

function buildBaseForPort(port: string): string {
  if (typeof window === 'undefined') return `http://localhost:${port}`
  const { protocol, hostname } = window.location
  return `${protocol}//${hostname}:${port}`
}

/**
 * Returns the backend API base URL. Always call this — don't cache the result
 * at module scope, or Next.js will inline the SSR value.
 */
export function getApiBase(): string {
  const envApiUrl = process.env.NEXT_PUBLIC_API_URL?.trim()
  if (envApiUrl) return trimTrailingSlash(envApiUrl)

  if (typeof window !== 'undefined') {
    // Use a probed URL if we've already detected a working port this session
    const cached = window.sessionStorage.getItem(SESSION_KEY_DETECTED_BASE)
    if (cached) return cached

    const { port } = window.location
    if (BACKEND_PORTS.includes(port)) return window.location.origin
    // Return primary port synchronously; async probe will update for next call
    return buildBaseForPort(BACKEND_PORTS[0])
  }
  return `http://localhost:${BACKEND_PORTS[0]}`
}

/**
 * Probes each backend port in order and caches the first healthy one in
 * sessionStorage. Subsequent getApiBase() calls return the cached URL.
 *
 * Call once near app startup (e.g. in a layout or root component useEffect).
 * Safe to call multiple times — exits early if a cached result exists.
 */
export async function probeAndCacheApiBase(): Promise<string> {
  const envApiUrl = process.env.NEXT_PUBLIC_API_URL?.trim()
  if (envApiUrl) return trimTrailingSlash(envApiUrl)

  if (typeof window === 'undefined') return `http://localhost:${BACKEND_PORTS[0]}`

  // Don't probe if the page is already served from a backend port
  const { port } = window.location
  if (BACKEND_PORTS.includes(port)) {
    window.sessionStorage.setItem(SESSION_KEY_DETECTED_BASE, window.location.origin)
    return window.location.origin
  }

  // Use cached result only if the capabilities route still responds on that port
  // (a stale process may answer /v1/health but lack newer routes).
  const cached = window.sessionStorage.getItem(SESSION_KEY_DETECTED_BASE)
  if (cached) {
    try {
      const parsed = new URL(cached)
      if (!BACKEND_PORTS.includes(parsed.port)) {
        window.sessionStorage.removeItem(SESSION_KEY_DETECTED_BASE)
      } else {
        const capRes = await fetch(`${cached}/v1/runtime/capabilities`, {
          signal: AbortSignal.timeout(2000),
          headers: { Authorization: `Bearer ${OWNER_API_KEY}` },
        })
        if (capRes.ok) return cached
        // Cached port is stale — clear it and fall through to full probe below
        window.sessionStorage.removeItem(SESSION_KEY_DETECTED_BASE)
      }
    } catch {
      window.sessionStorage.removeItem(SESSION_KEY_DETECTED_BASE)
    }
  }

  for (const p of BACKEND_PORTS) {
    const base = buildBaseForPort(p)
    try {
      const healthRes = await fetch(`${base}/v1/health`, { signal: AbortSignal.timeout(3000) })
      if (!healthRes.ok) continue
      // Also verify this process has the capabilities route (stale processes may
      // respond to /v1/health but are missing newer routes like /v1/runtime/capabilities).
      const capRes = await fetch(`${base}/v1/runtime/capabilities`, {
        signal: AbortSignal.timeout(3000),
        headers: { Authorization: `Bearer ${OWNER_API_KEY}` },
      })
      if (capRes.ok) {
        window.sessionStorage.setItem(SESSION_KEY_DETECTED_BASE, base)
        return base
      }
    } catch {
      // try next port
    }
  }

  // All probes failed — fall back to primary port
  const fallback = buildBaseForPort(BACKEND_PORTS[0])
  window.sessionStorage.setItem(SESSION_KEY_DETECTED_BASE, fallback)
  return fallback
}

/** Master owner key — used as fallback when no user JWT is stored. */
export const OWNER_API_KEY = 'modelmesh_local_dev_key'

/** localStorage key where we persist the user's JWT after login. */
export const TOKEN_KEY = 'devforge_auth_token'

/** Get the active auth token: user JWT if logged in, else master key. */
export function getAuthToken(): string {
  if (typeof window !== 'undefined') {
    const stored = window.localStorage.getItem(TOKEN_KEY)
    if (stored) return stored
  }
  return OWNER_API_KEY
}

/** @deprecated legacy alias — prefer getAuthToken() */
export const API_KEY = OWNER_API_KEY

/** Build auth headers dynamically at request time. */
export function getAuthHeaders(): Record<string, string> {
  return {
    'Authorization': `Bearer ${getAuthToken()}`,
    'Content-Type': 'application/json',
  }
}

// Legacy compat — evaluated at import time. In 'use client' components,
// window exists so they work. In SSR, they fall back to localhost.
export const API_BASE = typeof window !== 'undefined'
  ? getApiBase()
  : trimTrailingSlash(process.env.NEXT_PUBLIC_API_URL?.trim() || `http://localhost:${BACKEND_PORTS[0]}`)

/**
 * AUTH_HEADERS — computed dynamically via a Proxy so the Authorization
 * header always reflects the currently-stored token (JWT after login,
 * master key before login).
 */
export const AUTH_HEADERS: Record<string, string> = new Proxy({} as any, {
  get(_target, prop: string) {
    if (prop === 'Authorization') return `Bearer ${getAuthToken()}`
    if (prop === 'Content-Type') return 'application/json'
    return undefined
  },
  ownKeys() {
    return ['Authorization', 'Content-Type']
  },
  getOwnPropertyDescriptor() {
    return { enumerable: true, configurable: true }
  },
})
