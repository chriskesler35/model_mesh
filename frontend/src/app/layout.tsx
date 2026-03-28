import type { Metadata } from 'next'
import './globals.css'
import Navigation from './Navigation'

export const metadata: Metadata = {
  title: 'ModelMesh | Intelligent AI Gateway',
  description: 'Intelligent AI gateway that routes requests to optimal models based on cost, capability, and persona configuration.',
  icons: {
    icon: '/favicon.svg',
    apple: '/icon.svg',
  },
  openGraph: {
    title: 'ModelMesh',
    description: 'Intelligent AI Gateway',
    images: [
      {
        url: '/banner.svg',
        width: 1200,
        height: 400,
        alt: 'ModelMesh',
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