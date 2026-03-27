import {
  ArrowRight,
  Cable,
  CheckCircle2,
  Clock3,
  FileText,
  Github,
  Network,
  Sparkles,
  Workflow,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { usePageTitle } from '@/hooks/usePageTitle'

const liveCards = [
  {
    title: 'LangGraph',
    status: 'Available now',
    icon: Workflow,
    tone: 'text-primary',
    summary:
      'Registers real graph structure, compiles runtime metadata, and syncs model + graph passports into another local registry.',
    details: [
      'Adapter-based graph registration',
      'Runtime compile metadata capture',
      'Sync demo included in OSS examples',
    ],
  },
  {
    title: 'LangChain',
    status: 'Available now',
    icon: Cable,
    tone: 'text-accent-dark',
    summary:
      'Supports runnable binding, callback capture, tool-aware agent metadata, and sync-ready passport export/import.',
    details: [
      'Lazy registration wrappers',
      'Tool-calling runtime capture',
      'Sync demo included in OSS examples',
    ],
  },
  {
    title: 'GitHub',
    status: 'Compatibility bridge',
    icon: Github,
    tone: 'text-brand',
    summary:
      'Provides reusable CI validation so a committed passport file can be checked in any repository without a hosted service.',
    details: [
      'Reusable GitHub Action',
      'Copyable workflow demo',
      'Local validator script',
    ],
  },
  {
    title: 'Hugging Face',
    status: 'Compatibility bridge',
    icon: FileText,
    tone: 'text-highlight-dark',
    summary:
      'Exports a local ModelPassport into a Hugging Face-style model card, preserving deterministic identity and provenance fields.',
    details: [
      'Local markdown exporter',
      'Demo publication payload',
      'No HF API upload yet',
    ],
  },
]

const principles = [
  {
    title: 'Protocol first',
    description:
      'Forkit connects through passports, export envelopes, and HTTP contracts rather than shared hosted state.',
  },
  {
    title: 'Local first',
    description:
      'Every integration should stay useful without requiring a centralized account, org, or control plane.',
  },
  {
    title: 'Thin adapters',
    description:
      'Each ecosystem should get a small adapter over its real runtime/config surface instead of a new architecture.',
  },
]

const roadmapCards = [
  {
    title: 'Hugging Face deeper publish flow',
    status: 'Next layer',
    description:
      'Extend the current export bridge into a cleaner model publishing path once the lightweight compatibility flow gets user pull.',
  },
  {
    title: 'OpenClaw and Nemo',
    status: 'Candidate adapters',
    description:
      'Good next targets after Lang adoption because they fit the same adapter model: config capture, runtime metadata, and passport sync.',
  },
  {
    title: 'Additional agent and model stacks',
    status: 'Global adoption path',
    description:
      'Broaden only after the current adapter pattern is proven. Reuse the same shape instead of adding stack-specific backend logic.',
  },
]

export function EcosystemsPage() {
  usePageTitle('Ecosystems')

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-14 px-4 pb-14 pt-16 sm:px-6 lg:px-8 lg:pt-20">
      <section className="grid grid-cols-1 gap-8 xl:grid-cols-[1.08fr_0.92fr]">
        <div className="space-y-6">
          <div className="inline-flex items-center gap-3 rounded-full border border-border/80 bg-surface px-4 py-2.5 shadow-[0_10px_24px_rgba(42,31,85,0.06)]">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Network className="h-4 w-4" />
            </div>
            <span className="text-sm font-semibold text-primary">Ecosystem adoption surface</span>
          </div>

          <div className="space-y-4">
            <h1 className="font-display text-5xl font-extrabold leading-[1.02] tracking-tight text-text md:text-6xl">
              Where Forkit already connects, and where it should expand next.
            </h1>
            <p className="max-w-3xl text-[1.05rem] leading-relaxed text-muted md:text-xl">
              Forkit Core is strongest today when it works as a local-first passport layer around real developer ecosystems.
              LangGraph and LangChain are the first full adapters. GitHub and Hugging Face are compatibility bridges.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {principles.map((item) => (
              <div key={item.title} className="waterdrop-glass rounded-[1.75rem] border border-border/80 p-5">
                <div className="eyebrow">{item.title}</div>
                <p className="mt-3 text-sm leading-relaxed text-muted">{item.description}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="waterdrop-glass rounded-[2rem] border border-border/80 p-7">
          <div className="eyebrow">Current recommendation</div>
          <h2 className="mt-3 text-3xl font-bold text-text">Use Lang first, expand later.</h2>
          <p className="mt-4 leading-relaxed text-muted">
            The current OSS branch is ready to demonstrate value through LangGraph and LangChain. That is the cleanest way
            to make Forkit adoptive now, then extend the same adapter pattern to Hugging Face, OpenClaw, Nemo, and other
            important ecosystems without rewriting the core.
          </p>

          <div className="mt-8 space-y-4">
            {[
              'LangGraph and LangChain are now the most complete integrations.',
              'Hugging Face is currently a local export bridge, not a deep API integration.',
              'The next good UI step is one ecosystem page, not one page per integration.',
            ].map((line) => (
              <div key={line} className="surface-muted rounded-2xl px-4 py-3 text-sm text-text">
                {line}
              </div>
            ))}
          </div>

          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              to="/registry"
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-5 py-3 font-semibold text-[#f1ebdf] shadow-[0_14px_28px_rgba(0,129,144,0.18)] transition-all hover:bg-accent-dark"
            >
              Explore Registry
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
          <div className="eyebrow">Live Now</div>
          <h2 className="mt-2 text-3xl font-bold text-text">Current adapters and compatibility bridges</h2>
        </div>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          {liveCards.map((card) => {
            const Icon = card.icon
            return (
              <article key={card.title} className="waterdrop-glass rounded-[2rem] border border-border/80 p-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-center gap-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-border/70 bg-surface-soft">
                      <Icon className={`h-6 w-6 ${card.tone}`} />
                    </div>
                    <div>
                      <h3 className="text-2xl font-semibold text-text">{card.title}</h3>
                      <div className="mt-1 inline-flex items-center gap-2 rounded-full border border-border/70 bg-white/75 px-3 py-1 text-xs font-semibold text-muted">
                        {card.status === 'Available now' ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-semantic-success" />
                        ) : (
                          <Clock3 className="h-3.5 w-3.5 text-highlight-dark" />
                        )}
                        {card.status}
                      </div>
                    </div>
                  </div>
                </div>

                <p className="mt-5 leading-relaxed text-muted">{card.summary}</p>

                <div className="mt-5 space-y-2">
                  {card.details.map((detail) => (
                    <div key={detail} className="surface-muted rounded-2xl px-4 py-3 text-sm text-text">
                      {detail}
                    </div>
                  ))}
                </div>
              </article>
            )
          })}
        </div>
      </section>

      <section className="space-y-6">
        <div>
          <div className="eyebrow">Next Targets</div>
          <h2 className="mt-2 text-3xl font-bold text-text">Where to expand after Lang adoption</h2>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {roadmapCards.map((card) => (
            <article key={card.title} className="waterdrop-glass rounded-[2rem] border border-border/80 p-6">
              <div className="inline-flex items-center gap-2 rounded-full border border-border/75 bg-white/75 px-3 py-1 text-xs font-semibold text-muted">
                <Sparkles className="h-3.5 w-3.5 text-accent-dark" />
                {card.status}
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
