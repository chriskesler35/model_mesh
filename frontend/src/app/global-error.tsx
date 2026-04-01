'use client'

import { useEffect, useState } from 'react'

/**
 * Global error boundary — catches fatal React errors that crash the entire app.
 * Automatically attempts self-healing (cache clear + retry) before showing manual recovery UI.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  const [healing, setHealing] = useState(true)
  const [healResult, setHealResult] = useState<string | null>(null)

  // Auto-heal: clear cache and retry on first render
  useEffect(() => {
    let cancelled = false
    const selfHeal = async () => {
      try {
        // Try to clear the frontend cache via the health API
        await fetch('/api/health', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'clear-cache' }),
        })
        // Wait a beat for the server to settle
        await new Promise(r => setTimeout(r, 800))
        if (!cancelled) {
          // Try the reset first — if the error was transient, this fixes it
          reset()
        }
      } catch {
        // Health API not reachable — fall through to manual recovery
      }
      if (!cancelled) {
        setHealing(false)
        setHealResult('Auto-recovery attempted. If the page is still broken, try the buttons below.')
      }
    }
    selfHeal()
    return () => { cancelled = true }
  }, [reset])

  if (healing) {
    return (
      <html lang="en" className="h-full">
        <body className="bg-gray-50 dark:bg-gray-900 h-full flex items-center justify-center">
          <div className="text-center">
            <div className="inline-block w-8 h-8 border-3 border-orange-500 border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-sm text-gray-500 dark:text-gray-400">Auto-recovering...</p>
          </div>
        </body>
      </html>
    )
  }

  return (
    <html lang="en" className="h-full">
      <body className="bg-gray-50 dark:bg-gray-900 h-full flex items-center justify-center">
        <div className="max-w-md mx-auto text-center p-8">
          <div className="text-5xl mb-4">&#9888;&#65039;</div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
            Something went wrong
          </h1>
          {healResult && (
            <p className="text-xs text-amber-600 dark:text-amber-400 mb-3">{healResult}</p>
          )}
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
            The app hit an unexpected error.
          </p>
          <div className="flex gap-3 justify-center flex-wrap">
            <button
              onClick={reset}
              className="px-4 py-2 rounded-lg bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium transition-colors"
            >
              Try again
            </button>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              Hard reload
            </button>
            <button
              onClick={() => window.location.href = '/'}
              className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              Go to Dashboard
            </button>
          </div>
          <details className="mt-6 text-left">
            <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">
              Error details
            </summary>
            <pre className="mt-2 text-xs text-red-500 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg overflow-auto max-h-40">
              {error.message}
              {error.digest && `\nDigest: ${error.digest}`}
            </pre>
          </details>
        </div>
      </body>
    </html>
  )
}
