import Navbar from "./components/Navbar"

export default function Loading() {
  return (
    <div className="min-h-screen" aria-busy="true">
      <Navbar />
      <main className="mx-auto w-full max-w-[var(--max-width)] px-6 pb-12 pt-[112px]">
        <div role="status" aria-live="polite">
          <span className="sr-only">Loading page content</span>
          <div className="eyebrow">OPENING WORKSPACE</div>
          <div className="skeleton mt-4 h-8 w-64" />
          <div className="skeleton mt-3 h-3 w-96 max-w-full" />
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="skeleton h-32 rounded-xl" />
            <div className="skeleton h-32 rounded-xl" />
            <div className="skeleton h-32 rounded-xl" />
          </div>
          <div className="skeleton mt-6 h-64 rounded-xl" />
        </div>
      </main>
    </div>
  )
}
