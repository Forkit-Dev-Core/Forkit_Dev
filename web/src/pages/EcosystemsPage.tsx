import {
  ArrowRight,
  Cable,
  CheckCircle2,
  FileText,
  Github,
  Network,
  Sparkles,
  Workflow,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { usePageTitle } from '@/hooks/usePageTitle'

const adapterCards = [
  {
    title: 'LangGraph',
    depth: 'Deep adapter',
    icon: Workflow,
    tone: 'text-primary',
    summary:
      'Best current adoption path. Captures graph structure, compile metadata, and sync-ready passports around real graph execution.',
    install: 'pip install -e ".[langgraph]"',
    start: 'examples/langgraph_sync_quickstart.py',
    outcome:
      'A graph passport with deterministic identity, runtime compile context, and a syncable local record.',
    proof: 'Validated with a real StateGraph compile and invoke flow.',
  },
  {
    title: 'LangChain',
    depth: 'Deep adapter',
    icon: Cable,
    tone: 'text-accent-dark',
    summary:
      'Strong agent adoption surface. Supports runnable binding, callback capture, tool-aware metadata, and sync-ready passports.',
    install: 'pip install -e ".[langchain]"',
    start: 'examples/langchain_sync_quickstart.py',
    outcome:
      'An agent passport with tool-aware metadata, runtime event capture, and a local-first verification path.',
    proof: 'Validated with real agent creation, invoke flow, and tool-calling coverage.',
  },
]

const bridgeCards = [
  {
    title: 'GitHub',
    depth: 'Bridge',
    icon: Github,
    tone: 'text-brand',
    summary:
      'Useful without a hosted service. Keep this as a CI validation bridge until developers clearly ask for more.',
    install: 'copy publish/github-ci-demo/ into your repository',
    start: 'publish/github-ci-demo/',
    outcome:
      'CI fails when a committed passport is missing, invalid, or has a mismatched deterministic ID.',
    proof: 'Reusable action plus local validator script.',
  },
  {
    title: 'Hugging Face',
    depth: 'Bridge',
    icon: FileText,
    tone: 'text-highlight-dark',
    summary:
      'Keep this lightweight for now. The current value is provenance-aware model card export, not a full remote publishing workflow.',
    install: 'python scripts/export_hf_model_card.py --path forkit-passport.json',
    start: 'publish/huggingface-demo/',
    outcome:
      'A model-card-ready markdown file that preserves provenance fields from a local ModelPassport.',
    proof: 'Local exporter with demo publication payload.',
  },
]

const strategyRules = [
  'Go deep only when runtime metadata is part of the value.',
  'Stay bridge-first when file export or CI already solves the main use case.',
  'Expand to the next ecosystem only after one current adapter pulls real users.',
]

const adoptionSteps = [
  {
    step: 'Install',
    detail: 'Use one extra only for the ecosystem you need.',
  },
  {
    step: 'Wrap',
    detail: 'Bind your graph or runnable and let Forkit derive the passport locally.',
  },
  {
    step: 'Verify',
    detail: 'Inspect the generated passport and keep the identity local-first.',
  },
  {
    step: 'Sync',
    detail: 'Push or pull only if you need another registry to mirror the record.',
  },
]

const nextTargets = [
  {
    title: 'Hugging Face publish path',
    label: 'Bridge refinement',
    description:
      'Polish the current export flow before adding API-level complexity.',
  },
  {
    title: 'OpenClaw',
    label: 'Next adapter',
    description:
      'Logical next target because it matches the same thin adapter model as Lang runtimes.',
  },
  {
    title: 'NeMo',
    label: 'Later adapter',
    description:
      'Better after the runtime adapter pattern is proven, because the surface is broader and heavier.',
  },
]

function IntegrationCard({
  title,
  depth,
  icon: Icon,
  tone,
  summary,
  install,
  start,
  outcome,
  proof,
}: {
  title: string
  depth: string
  icon: typeof Workflow
  tone: string
  summary: string
  install: string
  start: string
  outcome: string
  proof: string
}) {
  return (
    <article className="waterdrop-glass rounded-[2rem] border border-border/80 p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-border/70 bg-surface-soft">
            <Icon className={`h-6 w-6 ${tone}`} />
          </div>
          <div>
            <h3 className="text-2xl font-semibold text-text">{title}</h3>
            <div className="mt-1 inline-flex items-center gap-2 rounded-full border border-border/70 bg-white/75 px-3 py-1 text-xs font-semibold text-muted">
              {depth === 'Deep adapter' ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-semantic-success" />
              ) : (
                <Sparkles className="h-3.5 w-3.5 text-highlight-dark" />
              )}
              {depth}
            </div>
          </div>
        </div>
      </div>

      <p className="mt-5 leading-relaxed text-muted">{summary}</p>

      <div className="mt-5 grid gap-4">
        <div className="rounded-2xl border border-border bg-surface-soft p-4">
          <div className="text-[11px] uppercase tracking-[0.2em] text-muted">Install</div>
          <div className="mt-2 break-all font-mono text-sm text-text">{install}</div>
        </div>
        <div className="rounded-2xl border border-border bg-surface-soft p-4">
          <div className="text-[11px] uppercase tracking-[0.2em] text-muted">Start With</div>
          <div className="mt-2 break-all font-mono text-sm text-text">{start}</div>
        </div>
        <div className="rounded-2xl border border-border bg-surface-soft p-4">
          <div className="text-[11px] uppercase tracking-[0.2em] text-muted">Expected Outcome</div>
          <div className="mt-2 text-sm leading-relaxed text-text">{outcome}</div>
        </div>
        <div className="surface-muted rounded-2xl px-4 py-3 text-sm text-text">{proof}</div>
      </div>
    </article>
  )
}

export function EcosystemsPage() {
  usePageTitle('Ecosystems')

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-14 px-4 pb-14 pt-16 sm:px-6 lg:px-8 lg:pt-20">
      <section className="grid grid-cols-1 gap-8 xl:grid-cols-[1.06fr_0.94fr]">
        <div className="space-y-6">
          <div className="inline-flex items-center gap-3 rounded-full border border-border/80 bg-surface px-4 py-2.5 shadow-[0_10px_24px_rgba(42,31,85,0.06)]">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Network className="h-4 w-4" />
            </div>
            <span className="text-sm font-semibold text-primary">Integrations</span>
          </div>

          <div className="space-y-4">
            <h1 className="font-display text-5xl font-extrabold leading-[1.02] tracking-tight text-text md:text-6xl">
              Forkit Dev works best when it wraps real model and agent workflows.
            </h1>
            <p className="max-w-3xl text-[1.05rem] leading-relaxed text-muted md:text-xl">
              Forkit Dev gives models and agents a local-first passport with deterministic identity, provenance, and
              verification. The cleanest adoption path is to attach Forkit to tools people already use, then show the
              exact outcome they can expect from each integration.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {adoptionSteps.map((item, index) => (
              <div key={item.step} className="waterdrop-glass rounded-[1.6rem] border border-border/80 p-5">
                <div className="eyebrow">{`0${index + 1}`}</div>
                <h2 className="mt-2 text-lg font-semibold text-text">{item.step}</h2>
                <p className="mt-2 text-sm leading-relaxed text-muted">{item.detail}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="waterdrop-glass rounded-[2rem] border border-border/80 p-7">
          <div className="eyebrow">Decision Rule</div>
          <h2 className="mt-3 text-3xl font-bold text-text">Deep where runtime matters. Bridge where it does not.</h2>
          <p className="mt-4 leading-relaxed text-muted">
            The safest product rule is simple: keep deep adapters for ecosystems where runtime structure and events add real
            passport value, and keep bridge integrations lightweight until user pull proves otherwise. That keeps Forkit
            Dev adoptable without forcing users into a larger system on day one.
          </p>

          <div className="mt-8 space-y-4">
            {strategyRules.map((rule) => (
              <div key={rule} className="surface-muted rounded-2xl px-4 py-3 text-sm text-text">
                {rule}
              </div>
            ))}
          </div>

          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              to="/passports/create?type=agent"
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-3 font-semibold text-[#f1ebdf] shadow-[0_14px_28px_rgba(0,129,144,0.18)] transition-all hover:bg-accent-dark"
            >
              Register Agent Passport
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              to="/verify"
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-white/82 px-5 py-3 font-semibold text-text transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary"
            >
              Verify Passport
            </Link>
          </div>
        </div>
      </section>

      <section className="space-y-6">
        <div>
          <div className="eyebrow">Deep Adapters</div>
          <h2 className="mt-2 text-3xl font-bold text-text">Use these first</h2>
        </div>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {adapterCards.map((card) => (
            <IntegrationCard key={card.title} {...card} />
          ))}
        </div>
      </section>

      <section className="space-y-6">
        <div>
          <div className="eyebrow">Bridge Integrations</div>
          <h2 className="mt-2 text-3xl font-bold text-text">Keep these lightweight</h2>
        </div>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {bridgeCards.map((card) => (
            <IntegrationCard key={card.title} {...card} />
          ))}
        </div>
      </section>

      <section className="space-y-6">
        <div>
          <div className="eyebrow">Next</div>
          <h2 className="mt-2 text-3xl font-bold text-text">Expand in this order</h2>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {nextTargets.map((card) => (
            <article key={card.title} className="waterdrop-glass rounded-[2rem] border border-border/80 p-6">
              <div className="inline-flex items-center gap-2 rounded-full border border-border/75 bg-white/75 px-3 py-1 text-xs font-semibold text-muted">
                <Sparkles className="h-3.5 w-3.5 text-accent-dark" />
                {card.label}
              </div>
              <h3 className="mt-4 text-2xl font-semibold text-text">{card.title}</h3>
              <p className="mt-3 leading-relaxed text-muted">{card.description}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}
