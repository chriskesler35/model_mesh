'use client'

import { getApiBase, TOKEN_KEY } from '@/lib/config'
import { useEffect, useState } from 'react'

export default function GitHubCallbackPage() {
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('Finishing sign-in…')

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const state = params.get('state')
    const error = params.get('error')

    if (error) {
      setStatus('error')
      setMessage(`GitHub returned: ${error}`)
      return
    }
    if (!code) {
      setStatus('error')
      setMessage('No authorization code in the callback URL.')
      return
    }

    // Verify state token matches what we stored before redirect
    const expectedState = sessionStorage.getItem('github_oauth_state')
    if (expectedState && state !== expectedState) {
      setStatus('error')
      setMessage('State token mismatch — possible CSRF attempt. Try signing in again.')
      return
    }

    fetch(`${getApiBase()}/v1/auth/github/callback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, state }),
    })
      .then(async r => {
        if (!r.ok) {
          const d = await r.json().catch(() => ({}))
          throw new Error(d?.detail || `HTTP ${r.status}`)
        }
        return r.json()
      })
      .then(({ token, user }) => {
        localStorage.setItem(TOKEN_KEY, token)
        localStorage.setItem('devforge_user', JSON.stringify(user))
        sessionStorage.removeItem('github_oauth_state')
        const redirect = sessionStorage.getItem('github_oauth_redirect') || '/'
        sessionStorage.removeItem('github_oauth_redirect')
        setStatus('success')
        setMessage(`Welcome, ${user.display_name || user.username}! Redirecting…`)
        setTimeout(() => { window.location.href = redirect }, 800)
      })
      .catch(e => {
        setStatus('error')
        setMessage(e.message || 'Sign-in failed')
      })
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="w-full max-w-md bg-white dark:bg-gray-800 rounded-2xl shadow-lg p-8 text-center">
        <div className="text-5xl mb-4">
          {status === 'loading' && '⏳'}
          {status === 'success' && '✓'}
          {status === 'error' && '⚠'}
        </div>
        <h1 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
          {status === 'loading' && 'Signing you in with GitHub'}
          {status === 'success' && 'Signed in'}
          {status === 'error' && 'Sign-in failed'}
        </h1>
        <p className={`text-sm ${status === 'error' ? 'text-red-600' : 'text-gray-500 dark:text-gray-400'}`}>
          {message}
        </p>
        {status === 'error' && (
          <a href="/login" className="inline-block mt-4 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium rounded-lg">
            Try again
          </a>
        )}
      </div>
    </div>
  )
}
