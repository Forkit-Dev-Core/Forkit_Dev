import { useEffect, useState } from 'react'
import { Database, Loader2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { fetchApi } from '@/lib/api'
import { usePageTitle } from '@/hooks/usePageTitle'
import type { RegistryStats } from '@/types'

export function RegistryStatsPage() {
  usePageTitle('Registry Stats')
  const [stats, setStats] = useState<RegistryStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const loadStats = async () => {
      try {
        const data = await fetchApi<RegistryStats>('/v1/registry/stats')
        setStats(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load registry stats')
      } finally {
        setLoading(false)
      }
    }

    void loadStats()
  }, [])

  return (
    <div className="mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-text">
            Registry Stats
          </h1>
          <p className="mt-1 text-muted">
            Local registry counts and storage layout aligned to the README registry contract.
          </p>
        </div>
        <Link
          to="/registry"
          className="section-link font-semibold"
        >
          Return to registry
        </Link>
      </div>

      {loading ? (
        <div className="flex items-center justify-center rounded-[2rem] border border-border/80 p-16 waterdrop-glass">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
        </div>
      ) : error || !stats ? (
        <div className="rounded-[2rem] border border-semantic-danger/20 bg-semantic-danger/8 p-8 text-semantic-danger">
          {error || 'No registry stats were returned.'}
        </div>
      ) : (
        <>
          <section className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <div className="rounded-[1.5rem] border border-border/80 p-5 waterdrop-glass">
              <div className="eyebrow">Total</div>
              <div className="mt-2 text-3xl font-bold text-primary">{stats.totalPassports}</div>
            </div>
            <div className="rounded-[1.5rem] border border-border/80 p-5 waterdrop-glass">
              <div className="eyebrow">Models</div>
              <div className="mt-2 text-3xl font-bold text-text">{stats.modelPassports}</div>
            </div>
            <div className="rounded-[1.5rem] border border-border/80 p-5 waterdrop-glass">
              <div className="eyebrow">Agents</div>
              <div className="mt-2 text-3xl font-bold text-text">{stats.agentPassports}</div>
            </div>
            <div className="rounded-[1.5rem] border border-border/80 p-5 waterdrop-glass">
              <div className="eyebrow">Verified</div>
              <div className="mt-2 text-3xl font-bold text-semantic-success">{stats.verifiedPassports}</div>
            </div>
            <div className="rounded-[1.5rem] border border-border/80 p-5 waterdrop-glass">
              <div className="eyebrow">Lineage Links</div>
              <div className="mt-2 text-3xl font-bold text-accent">{stats.lineageLinks}</div>
            </div>
          </section>

          <div className="grid grid-cols-1 xl:grid-cols-[1fr_1fr] gap-6">
            <div className="rounded-[2rem] border border-border/80 p-6 waterdrop-glass">
              <div className="flex items-center gap-3 mb-5">
                <Database className="w-5 h-5 text-primary" />
                <h2 className="text-lg font-semibold text-text">Registry Path</h2>
              </div>
              <div className="rounded-2xl border border-border bg-surface-soft p-4 font-mono text-sm text-text break-all">
                {stats.registryPath}
              </div>
            </div>

            <div className="rounded-[2rem] border border-border/80 p-6 waterdrop-glass">
              <div className="flex items-center gap-3 mb-5">
                <Database className="w-5 h-5 text-accent" />
                <h2 className="text-lg font-semibold text-text">Storage Layout</h2>
              </div>
              <div className="space-y-3">
                {stats.storage.map((item) => (
                  <div
                    key={item}
                    className="rounded-2xl border border-border bg-surface-soft p-4 font-mono text-sm text-text"
                  >
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
