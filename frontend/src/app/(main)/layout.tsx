import Navigation from '../Navigation'

export default function MainLayout({ children }: { children: React.ReactNode }) {
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
