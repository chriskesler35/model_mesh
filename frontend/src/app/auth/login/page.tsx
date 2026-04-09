'use client'

import { getApiBase, TOKEN_KEY } from '@/lib/config'
import { useState, useEffect } from 'react'
import { useAuth } from '@/contexts/AuthContext'

interface OAuthProvider {
  name: string
  display_name: string
  login_url: string
}

const OAUTH_ICONS: Record<string, React.ReactNode> = {
  github: (
    <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  ),
  google: (
    <svg className="w-5 h-5" viewBox="0 0 24 24">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  ),
  openrouter: (
    <span className="text-lg">🔀</span>
  ),
}

const OAUTH_STYLES: Record<string, string> = {
  github: 'bg-gray-900 hover:bg-black dark:bg-gray-700 dark:hover:bg-gray-600 text-white',
  google: 'bg-white hover:bg-gray-50 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-white border border-gray-300 dark:border-gray-600',
  openrouter: 'bg-indigo-600 hover:bg-indigo-700 text-white',
}

export default function AuthLoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [providers, setProviders] = useState<OAuthProvider[]>([])

  useEffect(() => {
    // Fetch configured OAuth providers
    const api = getApiBase()
    fetch(`${api}/v1/auth/providers`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.providers) setProviders(d.providers)
      })
      .catch(() => {})

    // Also check GitHub-specific config (it has its own route)
    fetch(`${api}/v1/auth/github/status`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.configured) {
          setProviders(prev => {
            if (prev.some(p => p.name === 'github')) return prev
            return [...prev, { name: 'github', display_name: 'GitHub', login_url: '/v1/auth/github' }]
          })
        }
      })
      .catch(() => {})
  }, [])

  const startOAuth = async (provider: OAuthProvider) => {
    try {
      if (provider.name === 'github') {
        // GitHub uses its own authorize endpoint — pass origin so redirect works remotely
        const res = await fetch(`${getApiBase()}/v1/auth/github/authorize?origin=${encodeURIComponent(window.location.origin)}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const { authorize_url, state } = await res.json()
        sessionStorage.setItem('github_oauth_state', state)
        const redirect = new URLSearchParams(window.location.search).get('redirect') || '/'
        sessionStorage.setItem('github_oauth_redirect', redirect)
        window.location.href = authorize_url
      } else {
        // Generic OAuth — redirect to the backend login_url which returns a redirect
        window.location.href = `${getApiBase()}${provider.login_url}`
      }
    } catch (e: any) {
      setError(`Failed to start ${provider.display_name} sign-in: ${e.message}`)
    }
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) return
    setLoading(true)
    setError('')
    try {
      await login(username.trim(), password)
      const redirect = new URLSearchParams(window.location.search).get('redirect') || '/'
      window.location.href = redirect
    } catch (e: any) {
      setError(e.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">⚡</div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">DevForgeAI</h1>
          <p className="text-sm text-gray-500 mt-2">Sign in to your account</p>
        </div>

        <form onSubmit={handleLogin} className="bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-8 space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Username or Email
            </label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
              placeholder="yourname"
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-white px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoComplete="current-password"
              placeholder="••••••••"
              className="w-full rounded-lg border border-gray-300 dark:border-gray-600 dark:bg-gray-900 dark:text-white px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
              required
            />
          </div>

          {error && (
            <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm text-red-700 dark:text-red-300">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !username.trim() || !password}
            className="w-full py-2.5 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-300 dark:disabled:bg-gray-700 text-white font-medium rounded-lg transition-colors"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>

          {providers.length > 0 && (
            <>
              <div className="flex items-center gap-3 py-1">
                <div className="flex-1 border-t border-gray-200 dark:border-gray-700" />
                <span className="text-xs text-gray-400">or continue with</span>
                <div className="flex-1 border-t border-gray-200 dark:border-gray-700" />
              </div>
              <div className="space-y-2">
                {providers.map(provider => (
                  <button
                    key={provider.name}
                    type="button"
                    onClick={() => startOAuth(provider)}
                    className={`w-full py-2.5 font-medium rounded-lg transition-colors flex items-center justify-center gap-2 ${
                      OAUTH_STYLES[provider.name] || 'bg-gray-600 hover:bg-gray-700 text-white'
                    }`}
                  >
                    {OAUTH_ICONS[provider.name] || <span>🔑</span>}
                    Continue with {provider.display_name}
                  </button>
                ))}
              </div>
            </>
          )}

          <p className="text-xs text-gray-500 dark:text-gray-400 text-center pt-2">
            Don&apos;t have an account?{' '}
            <a href="/auth/register" className="text-orange-500 hover:text-orange-600 font-medium">
              Register
            </a>
          </p>
        </form>

        <p className="text-center text-xs text-gray-400 mt-6">
          Hosting this instance yourself? You can keep using the owner key without signing in.
        </p>
      </div>
    </div>
  )
}
