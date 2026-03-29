'use client'

import { usePathname } from 'next/navigation'
import Navigation from './Navigation'

export default function NavigationWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isChat = pathname?.startsWith('/chat')

  if (isChat) {
    // Chat gets full viewport — no nav, no padding wrapper
    return <>{children}</>
  }

  return (
    <>
      <Navigation />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </>
  )
}
