import Navigation from '../Navigation'

export default function MainLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Navigation />
      <main className="
        px-4 py-6
        sm:px-4 sm:py-6
        md:px-6 md:py-7
        lg:px-10 lg:py-8
        xl:px-16
        2xl:px-24
      ">
        {children}
      </main>
    </>
  )
}
