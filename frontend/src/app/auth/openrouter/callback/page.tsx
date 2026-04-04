'use client'

import { API_BASE, AUTH_HEADERS } from '@/lib/config'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'

export default function OpenRouterCallback() {
  const searchParams = useSearchParams()
  const [status, setStatus] = useState<'working' | 'success' | 'error'>('working')
  const [message, setMessage] = useState('Exchanging authorization code for API key…')

  useEffect(() => {
    const exchange = async () => {
      const code = searchParams?.get('code')
      if (!code) {
        setStatus('error')
        setMessage('No authorization code received from OpenRouter.')
        return
      }

      const codeVerifier = sessionStorage.getItem('openrouter_pkce_verifier')
      if (!codeVerifier) {
        setStatus('error')
        setMessage('PKCE verifier missing. Please start the connection flow again.')
        return
      }

      try {
        // Exchange the code for an API key via OpenRouter's endpoint
        const exchangeRes = await fetch('https://openrouter.ai/api/v1/auth/keys', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            code,
            code_verifier: codeVerifier,
            code_challenge_method: 'S256',
          }),
        })

        if (!exchangeRes.ok) {
          const err = await exchangeRes.text()
          throw new Error(`OpenRouter exchange failed: ${err}`)
        }

        const { key } = await exchangeRes.json()
        if (!key) {
          throw new Error('OpenRouter did not return an API key.')
        }

        // Store the key in DevForgeAI backend
        const storeRes = await fetch(`${API_BASE}/v1/api-keys/openrouter`, {
          method: 'PUT',
          headers: AUTH_HEADERS,
          body: JSON.stringify({ value: key }),
        })

        if (!storeRes.ok) {
          const err = await storeRes.json()
          throw new Error(err.detail || 'Failed to save key to backend')
        }

        sessionStorage.removeItem('openrouter_pkce_verifier')
        setStatus('success')
        setMessage('OpenRouter connected! Redirecting back to Settings…')
        setTimeout(() => { window.location.href = '/settings?tab=api-keys' }, 1500)
      } catch (e: any) {
        setStatus('error')
        setMessage(e.message || 'Connection failed.')
      }
    }
    exchange()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const iconColor = status === 'success' ? 'text-green-500' : status === 'error' ? 'text-red-500' : 'text-indigo-500'
  const icon = status === 'success' ? '✓' : status === 'error' ? '✗' : '⏳'

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="max-w-md w-full bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8 text-center">
        <div className={`text-5xl mb-4 ${iconColor}`}>{icon}</div>
        <h1 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
          {status === 'success' ? 'Connected!' : status === 'error' ? 'Connection Failed' : 'Connecting OpenRouter…'}
        </h1>
        <p className="text-sm text-gray-600 dark:text-gray-300">{message}</p>
        {status === 'error' && (
          <a
            href="/settings?tab=api-keys"
            className="mt-6 inline-block px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg"
          >
            Back to Settings
          </a>
        )}
      </div>
    </div>
  )
}
