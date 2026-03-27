import { ArrowRight, Fingerprint, GitBranch, Search, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { LineageGraph } from '@/components/LineageGraph'
import PassportCard from '@/components/PassportCard'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  getPassportById,
  getPassportEdges,
  getPassportFamily,
  getPassports,
  getRegistryStats,
} from '@/lib/mockApi'

const moduleCards = [
  {
    title: 'forkit.domain',
    description: 'Identity derivation, SHA-256 hashing, lineage tracing, and integrity verification.',
  },
  {
    title: 'forkit.schemas',
    description: 'ModelPassport and AgentPassport structures used by the SDK and CLI.',
  },
  {
    title: 'forkit.registry',
    description: 'Local filesystem registry with JSON passport records and a rebuildable SQLite index.',
  },
]

export function LandingPage() {
  usePageTitle('Landing')
  const stats = getRegistryStats()
  const featuredPassports = getPassports().slice(0, 3)
  const focusPassport =
    getPassportById('b36533b819f6c687c5092b6e733ce2486d6bfb6a3f0bb2fd62f1b28781eca861') ??
    featuredPassports[0]
  const family = getPassportFamily(focusPassport.id)
  const edges = getPassportEdges(family)
  const statCards = [
    { label: 'Passports', value: stats.totalPassports, tone: 'text-primary' },
    { label: 'Verified', value: stats.verifiedPassports, tone: 'text-semantic-success' },
    { label: 'Models', value: stats.modelPassports, tone: 'text-text' },
    { label: 'Agents', value: stats.agentPassports, tone: 'text-text' },
  ]

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-16 px-4 pb-14 pt-16 sm:px-6 lg:px-8 lg:pt-24">
      <section className="grid grid-cols-1 items-center gap-10 xl:grid-cols-[1.16fr_0.94fr]">
        <div className="space-y-8">
          <div className="inline-flex items-center gap-3 rounded-full border border-border/85 bg-surface px-4 py-2.5 shadow-[0_10px_24px_rgba(42,31,85,0.06)]">
            <div className="brand-panel rounded-full px-2.5 py-1.5">
              <img
                src="/forkit-dev-logo.svg"
                alt="Forkit Dev"
                className="h-3.5 w-auto object-contain"
              />
            </div>
            <span className="text-sm font-semibold text-primary">README-aligned open source scope</span>
          </div>

          <div className="space-y-5">
            <h1 className="font-display text-5xl font-extrabold leading-[1.01] tracking-tight text-text md:text-7xl">
              Inspect and register{' '}
              <span className="bg-gradient-to-r from-primary via-accent to-brand bg-clip-text text-transparent">
                AI passports
              </span>{' '}
              in a local Forkit registry.
            </h1>
            <p className="max-w-3xl text-[1.08rem] leading-relaxed text-muted md:text-xl">
              Explore the current Forkit Core release in the browser. The web UI is mock-backed for demonstration, while the real open source value already ships in the schemas, local registry, SDK, CLI, and examples.
            </p>
          </div>

          <div className="flex flex-wrap gap-4">
            <Link
              to="/dashboard"
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-6 py-3.5 font-bold text-[#f1ebdf] shadow-[0_16px_28px_rgba(0,129,144,0.18)] transition-all hover:bg-accent-dark"
            >
              Open Dashboard
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              to="/search"
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-white/82 px-6 py-3.5 font-semibold text-text transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary"
            >
              <Search className="w-4 h-4" />
              Search Registry
            </Link>
            <Link
              to="/passports/create?type=model"
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-white/82 px-6 py-3.5 font-semibold text-text transition-colors hover:border-accent/30 hover:bg-accent/5 hover:text-accent-dark"
            >
              Register ModelPassport
            </Link>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {statCards.map((item) => (
              <div key={item.label} className="waterdrop-glass rounded-[1.5rem] border border-border/80 p-5">
                <div className="eyebrow">{item.label}</div>
                <div className={`mt-2 text-3xl font-extrabold ${item.tone}`}>{item.value}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="relative">
          <div className="absolute -inset-4 rounded-[2rem] bg-gradient-to-r from-primary/14 via-accent/10 to-highlight/16 blur-2xl" />
          <div className="relative overflow-hidden rounded-[2rem] border border-border/80 waterdrop-glass p-8">
            <div className="absolute inset-x-0 top-0 h-28 bg-gradient-to-r from-primary/12 via-transparent to-accent-soft/12" />
            <div className="relative mb-8 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-white shadow-sm">
                  <Fingerprint className="w-6 h-6" />
                </div>
                <div>
                  <div className="text-lg font-semibold text-text">Registry Snapshot</div>
                  <div className="text-sm text-muted">Current focus: {focusPassport.name}</div>
                </div>
              </div>
              <img
                src="/forkit-dev-logo.svg"
                alt="Forkit Dev"
                className="brand-panel hidden h-12 w-auto rounded-2xl px-2.5 py-2 sm:block"
              />
            </div>

            <div className="space-y-4">
              {[
                {
                  label: 'Passport ID',
                  value: focusPassport.id,
                },
                {
                  label: 'Registry Path',
                  value: focusPassport.recordPath,
                },
                {
                  label: 'Verification',
                  value: focusPassport.verificationChecks[0]?.detail ?? 'No verification checks stored.',
                },
              ].map((item) => (
                <div
                  key={item.label}
                  className="surface-muted rounded-2xl p-4"
                >
                  <div className="text-[11px] uppercase tracking-[0.2em] text-muted">
                    {item.label}
                  </div>
                  <div className="mt-2 break-all text-sm text-text">{item.value}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {moduleCards.map((moduleCard) => (
          <div
            key={moduleCard.title}
            className="waterdrop-glass rounded-[2rem] border border-border/80 p-6"
          >
            <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl border border-border/70 bg-surface-soft">
              {moduleCard.title === 'forkit.domain' ? (
                <ShieldCheck className="w-6 h-6 text-primary" />
              ) : moduleCard.title === 'forkit.schemas' ? (
                <Fingerprint className="w-6 h-6 text-accent" />
              ) : (
                <GitBranch className="w-6 h-6 text-brand" />
              )}
            </div>
            <h2 className="mb-3 text-xl font-semibold text-text">{moduleCard.title}</h2>
            <p className="leading-relaxed text-muted">{moduleCard.description}</p>
          </div>
        ))}
      </section>

      <section className="waterdrop-glass rounded-[2rem] border border-border/80 p-6 md:p-8">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4 mb-8">
          <div>
            <div className="eyebrow">Lineage Preview</div>
            <h2 className="mt-2 text-3xl font-bold text-text">
              Lineage is limited to README-supported passport links
            </h2>
            <p className="mt-3 max-w-3xl text-muted">
              The graph shows one fine-tuned model derived from a base model and one
              agent linked to a model with `model_id`.
            </p>
          </div>
          <Link
            to={`/lineage?id=${focusPassport.id}`}
            className="section-link font-semibold"
          >
            Open lineage view
          </Link>
        </div>
        <LineageGraph passports={family} edges={edges} focusId={focusPassport.id} />
      </section>

      <section className="space-y-6">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div>
            <div className="eyebrow">Registry Records</div>
            <h2 className="mt-2 text-3xl font-bold text-text">
              Example passports in the current mock registry
            </h2>
          </div>
          <Link
            to="/registry"
            className="section-link font-semibold"
          >
            Open registry
          </Link>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {featuredPassports.map((passport) => (
            <PassportCard key={passport.id} passport={passport} />
          ))}
        </div>
      </section>
    </div>
  )
}
