'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

/**
 * Chat-level error boundary — catches crashes in the chat page without
 * taking down the rest of the app. Attempts auto-recovery first.
 */
export default function ChatError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  const [autoRetried, setAutoRetried] = useState(false)

  // Auto-retry once on mount — transient errors (stale cache, race conditions) often
  // resolve on a simple re-render
  useEffect(() => {
    if (!autoRetried) {
      setAutoRetried(true)
      const timer = setTimeout(() => reset(), 500)
      return () => clearTimeout(timer)
    }
  }, [autoRetried, reset])

  // While auto-retrying, show a subtle loading state
  if (!autoRetried) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex gap-1.5">
          {[0, 1, 2].map(i => (
            <div key={i} className="w-2 h-2 bg-orange-400 rounded-full animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-center h-full p-8">
      <div className="max-w-sm text-center">
        <div className="text-4xl mb-3">&#128268;</div>
        <h2 className="text-lg font-semibold text-gray-800 dark:text-white mb-2">
          Chat hit an error
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-5">
          Auto-recovery didn&apos;t work. You can retry or head back to the dashboard.
        </p>
        <div className="flex gap-3 justify-center">
          <button
            onClick={reset}
            className="px-4 py-2 rounded-lg bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium transition-colors"
          >
            Retry
          </button>
          <Link
            href="/"
            className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            Dashboard
          </Link>
        </div>
        <details className="mt-5 text-left">
          <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">
            Error details
          </summary>
          <pre className="mt-2 text-xs text-red-500 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg overflow-auto max-h-32">
            {error.message}
          </pre>
        </details>
      </div>
    </div>
  )
}
