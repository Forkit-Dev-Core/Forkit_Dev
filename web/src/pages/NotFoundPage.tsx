import { Link } from 'react-router-dom'
import { usePageTitle } from '@/hooks/usePageTitle'

export function NotFoundPage() {
  usePageTitle('Not Found')
  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-20 sm:px-6 lg:px-8">
      <div className="rounded-[2rem] border border-border/80 p-12 text-center waterdrop-glass">
        <h1 className="font-display text-4xl font-bold text-text">Route not found</h1>
        <p className="mt-4 text-muted">
          This route is outside the README-defined open source frontend scope.
        </p>
        <Link
          to="/"
          className="mt-8 inline-flex items-center gap-2 rounded-xl bg-accent px-6 py-3 font-semibold text-[#f1ebdf] shadow-[0_14px_28px_rgba(0,129,144,0.18)] transition-all hover:bg-accent-dark hover:shadow-[0_18px_30px_rgba(0,129,144,0.22)]"
        >
          Return to Landing
        </Link>
      </div>
    </div>
  )
}
