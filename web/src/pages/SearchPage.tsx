import { useEffect, useState } from 'react'
import { Loader2, Search } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import PassportCard from '@/components/PassportCard'
import { fetchApi } from '@/lib/api'
import { usePageTitle } from '@/hooks/usePageTitle'
import type { Passport, PassportType } from '@/types'

export function SearchPage() {
  usePageTitle('Search Registry')
  const [searchParams, setSearchParams] = useSearchParams()
  const initialQuery = searchParams.get('q') || ''
  const initialType = (searchParams.get('type') as 'all' | PassportType | null) || 'all'

  const [query, setQuery] = useState(initialQuery)
  const [typeFilter, setTypeFilter] = useState<'all' | PassportType>(initialType)
  const [results, setResults] = useState<Passport[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setQuery(initialQuery)
    setTypeFilter(initialType)
  }, [initialQuery, initialType])

  useEffect(() => {
    const runSearch = async () => {
      setLoading(true)
      setError('')

      try {
        const params = new URLSearchParams()
        params.set('q', query)
        params.set('type', typeFilter)
        const data = await fetchApi<{ passports: Passport[] }>(
          `/v1/passports/search?${params.toString()}`,
        )
        setResults(data.passports ?? [])
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Search failed')
      } finally {
        setLoading(false)
      }
    }

    void runSearch()
  }, [query, typeFilter])

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    setSearchParams(
      query || typeFilter !== 'all'
        ? {
            ...(query ? { q: query } : {}),
            ...(typeFilter !== 'all' ? { type: typeFilter } : {}),
          }
        : {},
    )
  }

  return (
    <div className="mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight text-text">Search Registry</h1>
          <p className="mt-1 text-muted">
            Search and filter existing passports by Passport ID, name, version, creator, or task type.
          </p>
        </div>
        <div className="flex flex-wrap gap-4 text-sm font-semibold">
          <Link to="/registry" className="section-link">
            Browse full registry
          </Link>
          <Link to="/passports/create?type=model" className="section-link">
            Need a new record? Register Passport
          </Link>
        </div>
      </div>

      <form
        onSubmit={handleSubmit}
        className="rounded-[2rem] border border-border/80 p-6 waterdrop-glass"
      >
        <div className="mb-5 flex flex-col gap-4 border-b border-border/70 pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="eyebrow">Existing passports only</div>
            <p className="mt-2 max-w-2xl text-sm text-muted">
              This page only finds records already present in the mock registry. It does not
              create or change passports.
            </p>
          </div>
          <div className="rounded-full border border-border bg-surface-soft px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted">
            {typeFilter === 'all'
              ? 'Scope: all passports'
              : typeFilter === 'model'
                ? 'Scope: ModelPassport'
                : 'Scope: AgentPassport'}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1.5fr_0.8fr_auto] gap-4">
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
              <Search className="h-5 w-5 text-muted" />
            </div>
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search existing passports..."
              className="field-shell block w-full rounded-xl border py-3 pl-11 pr-4 text-sm leading-5 text-text placeholder:text-muted transition-all focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 sm:text-sm"
            />
          </div>

          <select
            value={typeFilter}
            onChange={(event) => setTypeFilter(event.target.value as 'all' | PassportType)}
            className="field-shell rounded-xl border px-4 py-3 text-text focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
          >
            <option value="all">All passports</option>
            <option value="model">ModelPassport</option>
            <option value="agent">AgentPassport</option>
          </select>

          <button
            type="submit"
            className="inline-flex items-center justify-center rounded-xl bg-accent px-5 py-3 font-semibold text-[#f1ebdf] shadow-[0_14px_26px_rgba(0,129,144,0.18)] transition-all hover:bg-accent-dark hover:shadow-[0_18px_30px_rgba(0,129,144,0.22)]"
          >
            Search
          </button>
        </div>
      </form>

      {!loading && !error ? (
        <div className="flex flex-col gap-3 rounded-[1.5rem] border border-border/80 bg-surface/78 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="eyebrow">Search results</div>
            <div className="mt-1 text-sm text-muted">
              {results.length} existing passport{results.length === 1 ? '' : 's'} matched the current query.
            </div>
          </div>
          <Link to="/registry" className="section-link text-sm font-semibold">
            Browse all passports instead
          </Link>
        </div>
      ) : null}

      {loading ? (
        <div className="flex items-center justify-center rounded-[2rem] border border-border/80 p-16 waterdrop-glass">
          <Loader2 className="w-8 h-8 animate-spin text-primary" />
        </div>
      ) : error ? (
        <div className="rounded-[2rem] border border-semantic-danger/20 bg-semantic-danger/8 p-8 text-semantic-danger">
          {error}
        </div>
      ) : results.length === 0 ? (
        <div className="rounded-[2rem] border border-border/80 p-16 text-center waterdrop-glass">
          <div className="text-xl font-semibold text-text">No search results</div>
          <div className="mt-2 text-muted">
            Try another query, broaden the passport type filter, or use Register Passport to create a new mock record.
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {results.map((passport) => (
            <PassportCard key={passport.id} passport={passport} />
          ))}
        </div>
      )}
    </div>
  )
}
