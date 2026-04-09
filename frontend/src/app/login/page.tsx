'use client'

import { useEffect } from 'react'

/**
 * Legacy /login route — redirects to /auth/login.
 * Preserves any ?redirect= query param.
 */
export default function LoginRedirect() {
  useEffect(() => {
    const params = window.location.search
    window.location.replace(`/auth/login${params}`)
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <p className="text-gray-400">Redirecting to login...</p>
    </div>
  )
}
