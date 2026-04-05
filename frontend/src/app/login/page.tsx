'use client'

import { getApiBase, TOKEN_KEY } from '@/lib/config'
import { useState, useEffect } from 'react'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [githubConfigured, setGithubConfigured] = useState(false)

  useEffect(() => {
    fetch(`${getApiBase()}/v1/auth/github/status`)
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setGithubConfigured(!!d.configured))
      .catch(() => {})
  }, [])

  const startGithubLogin = async () => {
    try {
      const res = await fetch(`${getApiBase()}/v1/auth/github/authorize`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const { authorize_url, state } = await res.json()
      sessionStorage.setItem('github_oauth_state', state)
      // Remember where the user wanted to go after login
      const redirect = new URLSearchParams(window.location.search).get('redirect') || '/'
      sessionStorage.setItem('github_oauth_redirect', redirect)
      window.location.href = authorize_url
    } catch (e: any) {
      setError(`GitHub sign-in failed to start: ${e.message}`)
    }
  }

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) return
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${getApiBase()}/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data?.detail || `Login failed (${res.status})`)
      }
      const { token, user } = await res.json()
      localStorage.setItem(TOKEN_KEY, token)
      localStorage.setItem('devforge_user', JSON.stringify(user))
      // Redirect to where they were heading, or home
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
              Username
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
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !username.trim() || !password}
            className="w-full py-2.5 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-300 text-white font-medium rounded-lg transition-colors"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>

          {githubConfigured && (
            <>
              <div className="flex items-center gap-3 py-1">
                <div className="flex-1 border-t border-gray-200 dark:border-gray-700" />
                <span className="text-xs text-gray-400">or</span>
                <div className="flex-1 border-t border-gray-200 dark:border-gray-700" />
              </div>
              <button
                type="button"
                onClick={startGithubLogin}
                className="w-full py-2.5 bg-gray-900 hover:bg-black dark:bg-gray-700 dark:hover:bg-gray-600 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
                </svg>
                Sign in with GitHub
              </button>
            </>
          )}

          <p className="text-xs text-gray-500 text-center pt-2">
            No account? Ask the instance owner to create one in Settings → Collaboration.
          </p>
        </form>

        <p className="text-center text-xs text-gray-400 mt-6">
          Hosting this instance yourself? You can keep using the owner key without signing in.
        </p>
      </div>
    </div>
  )
}
