import type { Metadata } from 'next'
import './globals.css'
import Navigation from './Navigation'

export const metadata: Metadata = {
  title: 'DevForgeAI | Intelligent Development Platform',
  description: 'Forge intelligent solutions with multi-agent orchestration, image generation, and AI-powered development.',
  icons: {
    icon: '/favicon.svg',
    apple: '/logo.svg',
  },
  openGraph: {
    title: 'DevForgeAI',
    description: 'Forge intelligent solutions with AI',
    images: [
      {
        url: '/banner.svg',
        width: 1200,
        height: 400,
        alt: 'DevForgeAI - Intelligent Development Platform',
      },
    ],
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="h-full">
      <body className="bg-gray-50 dark:bg-gray-900 min-h-full">
        <Navigation />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>
      </body>
    </html>
  )
}