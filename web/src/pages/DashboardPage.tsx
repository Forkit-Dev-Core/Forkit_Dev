import { useEffect, useState } from 'react'
import { Database, Fingerprint, GitBranch, Loader2, Search, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import PassportCard from '@/components/PassportCard'
import { fetchApi } from '@/lib/api'
import { usePageTitle } from '@/hooks/usePageTitle'
import type { Passport, RegistryStats } from '@/types'

export function DashboardPage() {
  usePageTitle('Dashboard')
  const [passports, setPassports] = useState<Passport[]>([])
  const [stats, setStats] = useState<RegistryStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        const [passportData, statsData] = await Promise.all([
          fetchApi<{ passports: Passport[] }>('/v1/passports'),
          fetchApi<RegistryStats>('/v1/registry/stats'),
        ])

        setPassports(passportData.passports ?? [])
        setStats(statsData)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load the dashboard')
      } finally {
        setLoading(false)
      }
    }

    void loadDashboard()
  }, [])

  const latestPassports = [...passports].sort((left, right) => {
    return Date.parse(right.updatedAt) - Date.parse(left.updatedAt)
  })
  const lineageLinked = passports.filter((passport) => passport.baseModelId || passport.modelId)
  const statCards = [
    {
      label: 'Registry',
      value: stats?.registryPath ?? 'Not available',
      tone: 'text-primary',
      mono: true,
    },
    {
      label: 'Passports',
      value: String(stats?.totalPassports ?? 0),
      tone: 'text-text',
    },
    {
      label: 'Verified',
      value: String(stats?.verifiedPassports ?? 0),
      tone: 'text-semantic-success',
    },
    {
      label: 'Lineage Links',
      value: String(stats?.lineageLinks ?? 0),
      tone: 'text-accent',
    },
  ]

  return (
    <div className="mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-text">Forkit Core Dashboard</h1>
          <p className="mt-1 text-muted">
            Open source overview for the local registry, recent passports, and lineage links.
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <Link
            to="/passports/create?type=model"
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-accent px-5 py-2.5 font-semibold text-[#f1ebdf] shadow-[0_14px_28px_rgba(0,129,144,0.18)] transition-all hover:bg-accent-dark hover:shadow-[0_18px_30px_rgba(0,129,144,0.22)]"
          >
            Register ModelPassport
          </Link>
          <Link
            to="/passports/create?type=agent"
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-white/80 px-5 py-2.5 font-semibold text-text transition-colors hover:border-accent/30 hover:bg-accent/5 hover:text-accent-dark"
          >
            Register AgentPassport
          </Link>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center rounded-[2rem] border border-border/80 p-16 waterdrop-glass">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
        </div>
      ) : error ? (
        <div className="rounded-[2rem] border border-semantic-danger/20 bg-semantic-danger/8 p-8 text-semantic-danger">
          {error}
        </div>
      ) : (
        <>
          <section className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {statCards.map((item) => (
              <div key={item.label} className="rounded-[1.5rem] border border-border/80 p-5 waterdrop-glass">
                <div className="eyebrow">{item.label}</div>
                <div
                  className={`mt-2 ${item.mono ? 'font-mono text-sm sm:text-base break-all' : 'text-3xl'} font-bold ${item.tone}`}
                >
                  {item.value}
                </div>
              </div>
            ))}
          </section>

          <div className="grid grid-cols-1 xl:grid-cols-[1.25fr_0.9fr] gap-6">
            <div className="space-y-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h2 className="text-2xl font-bold text-text">Recent passports</h2>
                  <p className="mt-1 text-muted">
                    Latest records available for inspect, verify, and lineage tracing.
                  </p>
                </div>
                <Link
                  to="/registry"
                  className="section-link font-semibold"
                >
                  Open registry
                </Link>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {latestPassports.slice(0, 4).map((passport) => (
                  <PassportCard key={passport.id} passport={passport} />
                ))}
              </div>
            </div>

            <div className="space-y-6">
              <div className="rounded-[2rem] border border-border/80 p-6 waterdrop-glass">
                <div className="flex items-center gap-3 mb-5">
                  <Search className="w-5 h-5 text-primary" />
                  <h2 className="text-lg font-semibold text-text">Open source actions</h2>
                </div>
                <div className="space-y-3">
                  <Link
                    to="/search"
                    className="block rounded-2xl border border-border bg-surface-soft p-4 transition-all hover:border-accent/25 hover:bg-accent/5 hover:shadow-[0_14px_28px_rgba(0,129,144,0.08)]"
                  >
                    <div className="flex items-center gap-2 text-sm font-semibold text-text">
                      <Search className="w-4 h-4 text-primary" />
                      Search passports
                    </div>
                    <div className="mt-1 text-xs text-muted">
                      Matches the `forkit search` workflow in the README.
                    </div>
                  </Link>
                  <Link
                    to="/verify"
                    className="block rounded-2xl border border-border bg-surface-soft p-4 transition-all hover:border-accent/25 hover:bg-accent/5 hover:shadow-[0_14px_28px_rgba(0,129,144,0.08)]"
                  >
                    <div className="flex items-center gap-2 text-sm font-semibold text-text">
                      <ShieldCheck className="w-4 h-4 text-primary" />
                      Verify integrity
                    </div>
                    <div className="mt-1 text-xs text-muted">
                      Inspect stored checks for a single Passport ID.
                    </div>
                  </Link>
                  <Link
                    to="/registry/stats"
                    className="block rounded-2xl border border-border bg-surface-soft p-4 transition-all hover:border-accent/25 hover:bg-accent/5 hover:shadow-[0_14px_28px_rgba(0,129,144,0.08)]"
                  >
                    <div className="flex items-center gap-2 text-sm font-semibold text-text">
                      <Database className="w-4 h-4 text-primary" />
                      Registry stats
                    </div>
                    <div className="mt-1 text-xs text-muted">
                      Local registry counts and storage layout.
                    </div>
                  </Link>
                </div>
              </div>

              <div className="rounded-[2rem] border border-border/80 p-6 waterdrop-glass">
                <div className="flex items-center gap-3 mb-5">
                  <GitBranch className="w-5 h-5 text-brand" />
                  <h2 className="text-lg font-semibold text-text">Lineage-linked passports</h2>
                </div>
                <div className="space-y-3">
                  {lineageLinked.map((passport) => (
                    <Link
                      key={passport.id}
                      to={`/lineage?id=${passport.id}`}
                      className="block rounded-2xl border border-border bg-surface-soft p-4 transition-all hover:border-brand/30 hover:bg-highlight/35 hover:shadow-[0_14px_28px_rgba(244,147,85,0.10)]"
                    >
                      <div className="text-sm font-semibold text-text">{passport.name}</div>
                      <div className="mt-1 break-all font-mono text-xs text-muted">
                        {passport.id}
                      </div>
                    </Link>
                  ))}
                </div>
              </div>

              <div className="rounded-[2rem] border border-border/80 p-6 waterdrop-glass">
                <div className="flex items-center gap-3 mb-5">
                  <Fingerprint className="w-5 h-5 text-accent" />
                  <h2 className="text-lg font-semibold text-text">Registry contents</h2>
                </div>
                <div className="space-y-3 text-sm text-muted">
                  {(stats?.storage ?? []).map((item) => (
                    <div
                      key={item}
                      className="rounded-2xl border border-border bg-surface-soft p-4 font-mono text-xs text-text"
                    >
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
