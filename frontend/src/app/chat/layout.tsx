import Navigation from '../Navigation'

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col overflow-hidden" style={{ height: '100dvh' }}>
      {/* Full nav bar — same as every other page */}
      <Navigation />

      {/*
        Responsive side + vertical margins:
          mobile  <640px  → flush, no margin (scrollbar at screen edge)
          sm      640+    → px-4,  pt-3 pb-4
          md      768+    → px-6
          lg      1024+   → px-10, pt-4 pb-6
          xl      1280+   → px-16
          2xl     1536+   → px-24
      */}
      <div className="flex-1 min-h-0
        pt-0 pb-0
        sm:pt-3 sm:pb-4 sm:px-4
        md:px-6
        lg:px-10 lg:pt-4 lg:pb-6
        xl:px-16
        2xl:px-24">
        <div className="h-full w-full overflow-hidden bg-white dark:bg-gray-900
          sm:rounded-2xl sm:border sm:border-gray-200 sm:dark:border-gray-700 sm:shadow-md">
          {children}
        </div>
      </div>
    </div>
  )
}
