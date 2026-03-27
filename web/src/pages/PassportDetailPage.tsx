import { useEffect, useState } from 'react'
import {
  ArrowRight,
  Fingerprint,
  GitBranch,
  Loader2,
  ShieldCheck,
  Wrench,
} from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { LineageGraph } from '@/components/LineageGraph'
import PassportCard from '@/components/PassportCard'
import { fetchApi } from '@/lib/api'
import { usePageTitle } from '@/hooks/usePageTitle'
import type { Passport, PassportEdge } from '@/types'

function getStatusVariant(status: Passport['verificationStatus']) {
  if (status === 'verified') {
    return 'success'
  }

  if (status === 'warning') {
    return 'warning'
  }

  return 'outline'
}

const fieldPanelClass = 'rounded-2xl border border-border bg-surface-soft p-4'

export function PassportDetailPage() {
  usePageTitle('Inspect Passport')
  const { passportId } = useParams()
  const [passport, setPassport] = useState<Passport | null>(null)
  const [family, setFamily] = useState<Passport[]>([])
  const [edges, setEdges] = useState<PassportEdge[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const load = async () => {
      if (!passportId) {
        setError('Missing Passport ID.')
        setLoading(false)
        return
      }

      try {
        const [passportData, lineageData] = await Promise.all([
          fetchApi<Passport>(`/v1/passports/${passportId}`),
          fetchApi<{ focus: Passport; family: Passport[]; edges: PassportEdge[] }>(
            `/v1/passports/${passportId}/lineage`,
          ),
        ])

        setPassport(passportData)
        setFamily(lineageData.family ?? [])
        setEdges(lineageData.edges ?? [])
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to inspect passport.')
      } finally {
        setLoading(false)
      }
    }

    void load()
  }, [passportId])

  if (loading) {
    return (
      <div className="mx-auto flex w-full max-w-7xl items-center justify-center px-4 py-16 sm:px-6 lg:px-8">
        <Loader2 className="h-10 w-10 animate-spin text-primary" />
      </div>
    )
  }

  if (error || !passport) {
    return (
      <div className="mx-auto w-full max-w-4xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="rounded-[2rem] border border-border/80 p-10 text-center waterdrop-glass">
          <h1 className="font-display text-3xl font-bold text-text">Passport not found</h1>
          <p className="mt-3 text-muted">{error || 'No passport data returned.'}</p>
          <Link
            to="/registry"
            className="mt-6 inline-flex items-center gap-2 rounded-xl bg-accent px-6 py-3 font-semibold text-[#f1ebdf] shadow-[0_14px_28px_rgba(0,129,144,0.18)] transition-all hover:bg-accent-dark hover:shadow-[0_18px_30px_rgba(0,129,144,0.22)]"
          >
            Return to Registry
          </Link>
        </div>
      </div>
    )
  }

  const relatedPassports = family.filter((candidate) => candidate.id !== passport.id)
  const summaryCards = [
    { label: 'Creator', value: passport.creator.name },
    { label: 'License', value: passport.license },
    { label: 'Updated', value: new Date(passport.updatedAt).toLocaleString() },
    { label: 'Record Path', value: passport.recordPath, mono: true },
  ]

  const integrityFields = [
    { label: 'artifact_hash', value: passport.artifactHash },
    { label: 'parent_hash', value: passport.parentHash },
    { label: 'base_model_id', value: passport.baseModelId },
    { label: 'model_id', value: passport.modelId },
    { label: 'system_prompt_hash', value: passport.systemPromptHash },
    { label: 'endpoint_hash', value: passport.endpointHash },
  ].filter((item) => item.value)

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-4 py-8 sm:px-6 lg:px-8">
      <section className="overflow-hidden rounded-[2rem] border border-border/80 waterdrop-glass">
        <div className="h-1.5 w-full bg-gradient-to-r from-accent via-primary to-brand" />
        <div className="space-y-8 p-8">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-3">
                <Badge variant="outline">
                  {passport.passportType === 'model' ? 'ModelPassport' : 'AgentPassport'}
                </Badge>
                <Badge variant={getStatusVariant(passport.verificationStatus)}>
                  {passport.verificationStatus}
                </Badge>
              </div>
              <div>
                <h1 className="font-display text-4xl font-bold tracking-tight text-text">
                  Inspect Passport
                </h1>
                <p className="mt-3 max-w-3xl text-lg leading-relaxed text-text">
                  {passport.name} v{passport.version}
                </p>
                <p className="mt-2 max-w-3xl text-muted">{passport.description}</p>
              </div>
              <div className="flex flex-wrap gap-4">
                <Link
                  to={`/verify?id=${passport.id}`}
                  className="inline-flex items-center gap-2 rounded-xl bg-accent px-6 py-3 font-semibold text-[#f1ebdf] shadow-[0_14px_28px_rgba(0,129,144,0.18)] transition-all hover:bg-accent-dark hover:shadow-[0_18px_30px_rgba(0,129,144,0.22)]"
                >
                  Verify
                  <ShieldCheck className="h-4 w-4" />
                </Link>
                <Link
                  to={`/lineage?id=${passport.id}`}
                  className="inline-flex items-center gap-2 rounded-xl border border-border bg-white/80 px-6 py-3 font-semibold text-text transition-colors hover:border-accent/30 hover:bg-accent/5 hover:text-accent-dark"
                >
                  Lineage
                  <GitBranch className="h-4 w-4" />
                </Link>
              </div>
            </div>

            <div className="grid min-w-full grid-cols-2 gap-4 xl:min-w-[360px] xl:max-w-[420px]">
              {summaryCards.map((item) => (
                <div key={item.label} className={fieldPanelClass}>
                  <div className="text-xs uppercase tracking-[0.2em] text-muted">{item.label}</div>
                  <div
                    className={`mt-2 ${item.mono ? 'font-mono text-xs break-all' : 'text-sm'} font-semibold text-text`}
                  >
                    {item.value}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.1fr_0.9fr]">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Fingerprint className="h-5 w-5 text-primary" />
                  Identity Fields
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className={fieldPanelClass}>
                  <div className="text-[11px] uppercase tracking-[0.2em] text-muted">Passport ID</div>
                  <div className="mt-2 break-all font-mono text-sm text-text">{passport.id}</div>
                </div>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <div className={fieldPanelClass}>
                    <div className="text-[11px] uppercase tracking-[0.2em] text-muted">Type</div>
                    <div className="mt-2 text-sm text-text">
                      {passport.passportType === 'model' ? 'ModelPassport' : 'AgentPassport'}
                    </div>
                  </div>
                  <div className={fieldPanelClass}>
                    <div className="text-[11px] uppercase tracking-[0.2em] text-muted">Version</div>
                    <div className="mt-2 text-sm text-text">{passport.version}</div>
                  </div>
                  <div className={fieldPanelClass}>
                    <div className="text-[11px] uppercase tracking-[0.2em] text-muted">
                      Architecture
                    </div>
                    <div className="mt-2 text-sm text-text">
                      {passport.architecture || 'Not stored'}
                    </div>
                  </div>
                  <div className={fieldPanelClass}>
                    <div className="text-[11px] uppercase tracking-[0.2em] text-muted">
                      Task Type
                    </div>
                    <div className="mt-2 text-sm text-text">
                      {passport.taskType || 'Not stored'}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5 text-accent" />
                  Integrity Fields
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {integrityFields.length > 0 ? (
                  integrityFields.map((item) => (
                    <div key={item.label} className={fieldPanelClass}>
                      <div className="text-[11px] uppercase tracking-[0.2em] text-muted">
                        {item.label}
                      </div>
                      <div className="mt-2 break-all font-mono text-sm text-text">
                        {item.value}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className={`${fieldPanelClass} text-sm text-muted`}>
                    No additional integrity fields are stored for this passport.
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ArrowRight className="h-5 w-5 text-brand" />
              Schema Fields
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {passport.trainingData?.length ? (
              <div>
                <div className="mb-3 text-[11px] uppercase tracking-[0.2em] text-muted">
                  Training Data References
                </div>
                <div className="space-y-3">
                  {passport.trainingData.map((item) => (
                    <div key={item} className={`${fieldPanelClass} text-sm text-text`}>
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {passport.capabilities ? (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className={fieldPanelClass}>
                  <div className="text-[11px] uppercase tracking-[0.2em] text-muted">
                    Modalities
                  </div>
                  <div className="mt-2 text-sm text-text">
                    {passport.capabilities.modalities.join(', ')}
                  </div>
                </div>
                <div className={fieldPanelClass}>
                  <div className="text-[11px] uppercase tracking-[0.2em] text-muted">
                    Context Length
                  </div>
                  <div className="mt-2 text-sm text-text">
                    {passport.capabilities.contextLength.toLocaleString()}
                  </div>
                </div>
              </div>
            ) : null}

            {passport.tools?.length ? (
              <div>
                <div className="mb-3 text-[11px] uppercase tracking-[0.2em] text-muted">Tools</div>
                <div className="space-y-3">
                  {passport.tools.map((tool) => (
                    <div key={`${tool.name}-${tool.version}`} className={fieldPanelClass}>
                      <div className="flex items-center gap-2 text-sm font-semibold text-text">
                        <Wrench className="h-4 w-4 text-accent" />
                        {tool.name} v{tool.version}
                      </div>
                      <div className="mt-2 break-all font-mono text-xs text-muted">
                        {tool.hash || 'No tool hash stored'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-primary" />
              Verify Checks
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {passport.verificationChecks.map((check) => (
              <div key={check.label} className={fieldPanelClass}>
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
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <GitBranch className="h-5 w-5 text-primary" />
            Lineage
          </CardTitle>
        </CardHeader>
        <CardContent>
          <LineageGraph passports={family} edges={edges} focusId={passport.id} />
        </CardContent>
      </Card>

      {relatedPassports.length > 0 ? (
        <section className="space-y-6">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-2xl font-bold text-text">Related Passports</h2>
            <Link to={`/lineage?id=${passport.id}`} className="section-link font-semibold">
              Open lineage view
            </Link>
          </div>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
            {relatedPassports.map((related) => (
              <PassportCard key={related.id} passport={related} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  )
}
