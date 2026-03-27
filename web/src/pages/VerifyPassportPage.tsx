import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle,
  Clock,
  Fingerprint,
  Search,
  Shield,
} from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { fetchApi } from '@/lib/api'
import { usePageTitle } from '@/hooks/usePageTitle'
import { getPassports } from '@/lib/mockApi'
import type { VerifyPassportResult } from '@/types'

function getBadgeVariant(verified: boolean) {
  return verified ? 'success' : 'warning'
}

const infoRowClass =
  'flex items-center justify-between rounded-xl border border-border bg-surface-soft px-4 py-3'

export function VerifyPassportPage() {
  usePageTitle('Verify Passport')
  const location = useLocation()
  const queryParams = new URLSearchParams(location.search)
  const initialId = queryParams.get('id') || ''

  const [searchId, setSearchId] = useState(initialId)
  const [isSearching, setIsSearching] = useState(false)
  const [result, setResult] = useState<VerifyPassportResult | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!initialId) {
      return
    }

    void performSearch(initialId)
  }, [initialId])

  async function performSearch(idToSearch: string) {
    if (!idToSearch.trim()) {
      return
    }

    setIsSearching(true)
    setError('')
    setResult(null)

    try {
      const data = await fetchApi<VerifyPassportResult>(`/v1/passports/${idToSearch.trim()}/verify`)
      setResult(data)
    } catch {
      setError('No passport found with that Passport ID.')
    } finally {
      setIsSearching(false)
    }
  }

  const handleSearch = async (event: React.FormEvent) => {
    event.preventDefault()
    await performSearch(searchId)
  }

  const quickPicks = getPassports()

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 py-12 sm:px-6 lg:px-8">
      <div className="relative mx-auto mt-6 flex w-full max-w-5xl flex-col gap-8">
        <Link
          to="/"
          className="inline-flex items-center gap-2 self-start rounded-full border border-border bg-white/80 px-4 py-2 text-sm font-medium text-muted transition-colors hover:border-accent/30 hover:bg-accent/5 hover:text-accent-dark"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Landing
        </Link>

        <div className="space-y-4 text-center">
          <div className="mx-auto mb-2 flex h-16 w-16 items-center justify-center rounded-3xl bg-accent text-white shadow-[0_16px_30px_rgba(0,129,144,0.18)]">
            <Shield className="h-8 w-8" />
          </div>
          <h1 className="font-display text-4xl font-bold tracking-tight text-text">
            Verify Passport
          </h1>
          <p className="mx-auto max-w-2xl text-lg text-muted">
            Run the open source integrity view for a single Passport ID and inspect the
            stored verification checks.
          </p>
        </div>

        <Card>
          <CardContent className="pt-6">
            <form onSubmit={handleSearch} className="flex flex-col gap-4 md:flex-row">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted" />
                <Input
                  value={searchId}
                  onChange={(event) => setSearchId(event.target.value)}
                  placeholder="Enter a Passport ID"
                  className="h-12 pl-10 text-base"
                />
              </div>
              <Button
                type="submit"
                disabled={isSearching || !searchId.trim()}
                className="h-12 px-8 text-base"
              >
                {isSearching ? 'Verifying...' : 'Verify'}
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-6">
            {error ? (
              <div className="rounded-[1.5rem] border border-semantic-danger/20 bg-semantic-danger/8 p-6 text-center">
                <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-semantic-danger" />
                <h3 className="mb-1 text-lg font-medium text-semantic-danger">
                  Verification failed
                </h3>
                <p className="text-semantic-danger/80">{error}</p>
              </div>
            ) : null}

            {result ? (
              <Card className="relative overflow-hidden">
                <div className="pointer-events-none absolute right-0 top-0 h-56 w-56 rounded-full bg-primary/7 blur-[100px]" />
                <CardHeader className="border-b border-border/70 pb-6">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="mb-2 flex flex-wrap items-center gap-3">
                        <CardTitle className="text-2xl">{result.passport.name}</CardTitle>
                        <Badge variant={getBadgeVariant(result.verified)}>
                          {result.verified ? 'verified' : 'warnings present'}
                        </Badge>
                      </div>
                      <p className="text-muted">{result.summary}</p>
                    </div>
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-border bg-surface-soft">
                      <Fingerprint className="h-6 w-6 text-primary" />
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-6 pt-6">
                  <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                    <div className="space-y-4">
                      <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-muted">
                        Passport Identity
                      </h4>
                      <div className="space-y-3">
                        <div className={infoRowClass}>
                          <span className="flex items-center gap-2 text-sm text-muted">
                            <Fingerprint className="h-4 w-4" />
                            Passport ID
                          </span>
                          <span className="break-all text-right font-mono text-sm text-text">
                            {result.passport.id}
                          </span>
                        </div>
                        <div className={infoRowClass}>
                          <span className="text-sm text-muted">Type</span>
                          <span className="text-sm text-text">
                            {result.passport.passportType === 'model'
                              ? 'ModelPassport'
                              : 'AgentPassport'}
                          </span>
                        </div>
                        <div className={infoRowClass}>
                          <span className="text-sm text-muted">Version</span>
                          <span className="text-sm text-text">{result.passport.version}</span>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-muted">
                        Verification Summary
                      </h4>
                      <div className="space-y-3">
                        <div className={infoRowClass}>
                          <span className="flex items-center gap-2 text-sm text-muted">
                            <CheckCircle className="h-4 w-4" />
                            Status
                          </span>
                          <Badge variant={getBadgeVariant(result.verified)}>
                            {result.passport.verificationStatus}
                          </Badge>
                        </div>
                        <div className={infoRowClass}>
                          <span className="flex items-center gap-2 text-sm text-muted">
                            <Clock className="h-4 w-4" />
                            Last Updated
                          </span>
                          <span className="text-sm text-text">
                            {new Date(result.passport.updatedAt).toLocaleDateString()}
                          </span>
                        </div>
                        <div className={infoRowClass}>
                          <span className="text-sm text-muted">Registry Record</span>
                          <span className="text-sm text-text">
                            {result.passport.recordPath.includes('/agents/') ? 'agents/' : 'models/'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-muted">
                      Verification Checks
                    </h4>
                    {result.passport.verificationChecks.map((check) => (
                      <div
                        key={check.label}
                        className="rounded-xl border border-border bg-surface-soft p-4"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-sm font-semibold text-text">{check.label}</div>
                          <Badge
                            variant={
                              check.status === 'pass'
                                ? 'success'
                                : check.status === 'warn'
                                  ? 'warning'
                                  : 'outline'
                            }
                          >
                            {check.status}
                          </Badge>
                        </div>
                        <div className="mt-2 text-sm text-muted">{check.detail}</div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ) : null}
          </div>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Example passports</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {quickPicks.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setSearchId(item.id)
                      void performSearch(item.id)
                    }}
                    className="w-full rounded-xl border border-border bg-surface-soft p-3 text-left transition-all hover:border-accent/25 hover:bg-accent/5 hover:shadow-[0_14px_28px_rgba(0,129,144,0.08)]"
                  >
                    <div className="text-sm font-semibold text-text">{item.name}</div>
                    <div className="mt-1 break-all font-mono text-xs text-muted">{item.id}</div>
                  </button>
                ))}
              </CardContent>
            </Card>

            {result ? (
              <Card>
                <CardHeader>
                  <CardTitle>Related actions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Link
                    to={`/passports/${result.passport.id}`}
                    className="block rounded-xl border border-border bg-surface-soft p-3 transition-all hover:border-accent/25 hover:bg-accent/5 hover:shadow-[0_14px_28px_rgba(0,129,144,0.08)]"
                  >
                    Inspect passport
                  </Link>
                  <Link
                    to={`/lineage?id=${result.passport.id}`}
                    className="block rounded-xl border border-border bg-surface-soft p-3 transition-all hover:border-accent/25 hover:bg-accent/5 hover:shadow-[0_14px_28px_rgba(0,129,144,0.08)]"
                  >
                    View lineage
                  </Link>
                </CardContent>
              </Card>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
