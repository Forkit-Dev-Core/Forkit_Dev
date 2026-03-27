import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import PassportCard from '@/components/PassportCard'
import { fetchApi } from '@/lib/api'
import { usePageTitle } from '@/hooks/usePageTitle'
import type { Passport } from '@/types'

export function PassportListPage() {
  usePageTitle('Registry')
  const [passports, setPassports] = useState<Passport[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchApi<{ passports: Passport[] }>('/v1/passports')
        setPassports(data.passports ?? [])
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load the registry')
      } finally {
        setLoading(false)
      }
    }

    void load()
  }, [])
  const modelCount = passports.filter((passport) => passport.passportType === 'model').length
  const agentCount = passports.filter((passport) => passport.passportType === 'agent').length
  const verifiedCount = passports.filter(
    (passport) => passport.verificationStatus === 'verified',
  ).length

  return (
    <div className="mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-text">Registry</h1>
          <p className="mt-1 text-muted">
            Browse every ModelPassport and AgentPassport currently present in the local registry.
          </p>
        </div>
        <div className="flex flex-wrap gap-4 text-sm font-semibold">
          <Link to="/search" className="section-link">
            Search and filter registry
          </Link>
          <Link to="/registry/stats" className="section-link">
            Open registry stats
          </Link>
        </div>
      </div>

      <div className="rounded-[2rem] border border-border/80 p-6 waterdrop-glass">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <div className="rounded-[1.5rem] border border-border bg-surface-soft px-5 py-4">
            <div className="eyebrow">Total</div>
            <div className="mt-2 text-3xl font-bold text-text">{passports.length}</div>
          </div>
          <div className="rounded-[1.5rem] border border-border bg-surface-soft px-5 py-4">
            <div className="eyebrow">Models</div>
            <div className="mt-2 text-3xl font-bold text-primary">{modelCount}</div>
          </div>
          <div className="rounded-[1.5rem] border border-border bg-surface-soft px-5 py-4">
            <div className="eyebrow">Agents</div>
            <div className="mt-2 text-3xl font-bold text-text">{agentCount}</div>
          </div>
          <div className="rounded-[1.5rem] border border-border bg-surface-soft px-5 py-4">
            <div className="eyebrow">Verified</div>
            <div className="mt-2 text-3xl font-bold text-accent">{verifiedCount}</div>
          </div>
        </div>

        <div className="mt-5 flex flex-col gap-3 border-t border-border/70 pt-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm text-muted">
            Registry is the browse view for all current passports. Use Search when you need
            query or filter controls.
          </div>
          <Link to="/search" className="section-link text-sm font-semibold">
            Open Search
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
      ) : passports.length === 0 ? (
        <div className="rounded-[2rem] border border-border/80 p-16 text-center waterdrop-glass">
          <div className="text-xl font-semibold text-text">No passports are in the registry yet.</div>
          <div className="mt-2 text-muted">
            Register a passport to create the first mock-backed record.
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {passports.map((passport) => (
            <PassportCard key={passport.id} passport={passport} />
          ))}
        </div>
      )}
    </div>
  )
}
