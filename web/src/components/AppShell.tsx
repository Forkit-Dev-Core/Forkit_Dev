import { Link, NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/utils'

const navItems = [
  { label: 'Landing', path: '/' },
  { label: 'Dashboard', path: '/dashboard' },
  { label: 'Registry', path: '/registry' },
  { label: 'Search', path: '/search' },
  { label: 'Verify', path: '/verify' },
  { label: 'Lineage', path: '/lineage' },
  { label: 'Stats', path: '/registry/stats' },
]

export function AppShell() {
  return (
    <div className="min-h-screen bg-bg text-text flex flex-col relative overflow-hidden transition-colors duration-300">
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute inset-0 bg-grid-pattern opacity-28" />
        <div className="absolute left-[-10rem] top-[-12rem] h-[28rem] w-[28rem] rounded-full bg-primary/8 blur-[130px]" />
        <div className="absolute right-[-8rem] top-[10rem] h-[20rem] w-[20rem] rounded-full bg-accent/10 blur-[120px]" />
      </div>

      <header className="sticky top-0 z-50 border-b border-border/80 bg-surface/92 backdrop-blur-xl shadow-[0_14px_34px_rgba(42,31,85,0.08)]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col gap-4 py-4 lg:flex-row lg:items-center lg:justify-between">
            <Link to="/" className="group flex items-center gap-4">
              <div className="brand-panel rounded-[1.4rem] px-3.5 py-2.5 transition-transform group-hover:scale-[1.015]">
                <img
                  src="/forkit-dev-logo.svg"
                  alt="Forkit Dev"
                  className="h-11 w-auto object-contain"
                />
              </div>
              <div className="space-y-1">
                <div className="font-display text-[1.85rem] font-extrabold tracking-tight text-text">
                  Forkit Core
                </div>
                <div className="text-[11px] uppercase tracking-[0.26em] text-muted">
                  Open Source Passport Console
                </div>
              </div>
            </Link>

            <nav className="brand-panel flex flex-wrap items-center gap-1.5 rounded-full p-1.5">
              {navItems.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === '/'}
                  className={({ isActive }) =>
                    cn(
                      'rounded-full px-4 py-2 text-sm font-semibold transition-all',
                      isActive
                        ? 'bg-primary text-[#f1ebdf] shadow-[0_10px_22px_rgba(42,31,85,0.24)]'
                        : 'text-muted hover:bg-primary/7 hover:text-primary',
                    )
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>

            <div className="flex items-center gap-3">
              <Link
                to="/passports/create"
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-accent px-5 py-2.5 font-semibold text-[#f1ebdf] shadow-[0_14px_28px_rgba(0,129,144,0.18)] transition-all hover:bg-accent-dark hover:shadow-[0_18px_30px_rgba(0,129,144,0.22)]"
              >
                Register Passport
              </Link>
            </div>
          </div>
        </div>
      </header>

      <div className="relative z-40 border-b border-border/70 bg-surface-soft/75 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 py-3 text-xs text-muted sm:px-6 lg:px-8">
          Web UI note: included for exploration in this open source release. It uses mock in-memory data, while the persistent core already lives in the schemas, local registry, SDK, CLI, and examples.
        </div>
      </div>

      <main className="flex-1 w-full flex flex-col relative z-10">
        <Outlet />
      </main>
    </div>
  )
}
