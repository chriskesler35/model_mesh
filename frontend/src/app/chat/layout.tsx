import Navigation from '../Navigation'

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full w-full overflow-hidden">
      <Navigation />
      <div className="flex-1 min-w-0 min-h-0 overflow-hidden p-3 bg-gray-50 dark:bg-gray-900">
        <div className="h-full w-full overflow-hidden bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-md">
          {children}
        </div>
      </div>
    </div>
  )
}
