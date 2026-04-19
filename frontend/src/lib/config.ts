/**
 * Dynamic API configuration for DevForgeAI.
 *
 * Auto-detects backend URL from the browser's current hostname and the
 * known backend port. This avoids relying on Next.js rewrites for auth'd API
 * calls, because some runtime modes do not preserve Authorization headers.
 *
 * Override: set NEXT_PUBLIC_API_URL in .env.local
 */

const BACKEND_PORT = '19000'

function trimTrailingSlash(url: string): string {
  return url.replace(/\/+$/, '')
}

/**
 * Returns the backend API base URL. Always call this — don't cache the result
 * at module scope, or Next.js will inline the SSR value.
 */
export function getApiBase(): string {
  const envApiUrl = process.env.NEXT_PUBLIC_API_URL?.trim()
  if (envApiUrl) return trimTrailingSlash(envApiUrl)

  if (typeof window !== 'undefined') {
    const { protocol, hostname, port } = window.location

    if (port === BACKEND_PORT) {
      return window.location.origin
    }

    return `${protocol}//${hostname}:${BACKEND_PORT}`
  }
  return `http://localhost:${BACKEND_PORT}`
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
  : trimTrailingSlash(process.env.NEXT_PUBLIC_API_URL?.trim() || `http://localhost:${BACKEND_PORT}`)

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
