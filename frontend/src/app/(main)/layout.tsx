'use client'

import Navigation from '../Navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useEffect } from 'react'
import { usePathname } from 'next/navigation'

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth()
  const pathname = usePathname()

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      const redirect = encodeURIComponent(pathname || '/')
      window.location.href = `/auth/login?redirect=${redirect}`
    }
  }, [isAuthenticated, isLoading, pathname])

  if (isLoading) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="animate-pulse text-gray-400">Loading...</div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  return (
    <div className="flex h-full w-full overflow-hidden">
      <Navigation />
      <main className="flex-1 overflow-y-auto min-w-0 bg-gray-50 dark:bg-gray-900">
        <div className="px-6 py-6 md:px-8 md:py-7 lg:px-10 lg:py-8 max-w-7xl mx-auto">
          {children}
        </div>
      </main>
    </div>
  )
}
