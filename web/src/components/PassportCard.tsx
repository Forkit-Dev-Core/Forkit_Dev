import { Activity, AlertTriangle, Box, Clock3, GitBranch, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import type { Passport } from '@/types'

interface PassportCardProps {
  passport: Passport
}

export default function PassportCard({ passport }: PassportCardProps) {
  const isAgent = passport.passportType === 'agent'
  const hasLineage = Boolean(passport.baseModelId || passport.modelId)

  const StatusIcon =
    passport.verificationStatus === 'verified'
      ? ShieldCheck
      : passport.verificationStatus === 'warning'
        ? Clock3
      : AlertTriangle

  const statusColor =
    passport.verificationStatus === 'verified'
      ? 'border-accent/18 bg-accent/10 text-accent'
      : passport.verificationStatus === 'warning'
        ? 'border-brand/20 bg-highlight/26 text-brand'
        : 'border-slate-200 bg-slate-100 text-slate-700'

  return (
    <div className="group relative flex h-full flex-col overflow-hidden rounded-[1.75rem] border border-border/85 shadow-[0_16px_40px_rgba(42,31,85,0.08)] transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_24px_48px_rgba(42,31,85,0.11)] waterdrop-glass">
      <div className="h-1.5 w-full bg-gradient-to-r from-accent via-primary to-brand/80 opacity-90" />

      <div className="p-6 flex-1 flex flex-col">
        <div className="flex justify-between items-start mb-5">
          <div className="flex items-start gap-3">
            <div className="rounded-xl border border-border/70 bg-surface-soft p-2.5 shadow-sm">
              {isAgent ? (
                <Activity className="w-6 h-6 text-accent" />
              ) : (
                <Box className="w-6 h-6 text-primary" />
              )}
            </div>
            <div>
              <h3 className="mb-1 line-clamp-1 text-lg font-bold leading-tight text-text">
                {passport.name}
              </h3>
              <p className="max-w-[210px] truncate rounded-md bg-surface-soft px-2 py-0.5 font-mono text-xs text-muted">
                {passport.id}
              </p>
            </div>
          </div>

          <div
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-bold capitalize shadow-sm',
              statusColor,
            )}
          >
            <StatusIcon className="w-3.5 h-3.5" />
            {passport.verificationStatus}
          </div>
        </div>

        <p className="mb-6 flex-1 line-clamp-3 text-sm leading-relaxed text-muted">
          {passport.description}
        </p>

        <div className="mt-auto grid grid-cols-2 gap-4 border-t border-border/70 pt-5">
          <div>
            <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-muted">
              Type
            </p>
            <span className="truncate text-sm font-semibold capitalize text-text">
              {isAgent ? 'AgentPassport' : 'ModelPassport'}
            </span>
          </div>

          <div>
            <p className="mb-1 text-[10px] font-bold uppercase tracking-widest text-muted">
              Version
            </p>
            <p className="truncate text-sm font-semibold text-text">{passport.version}</p>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-border/70 bg-surface-soft/76 px-6 py-4 transition-colors group-hover:bg-primary/4">
        <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted">
          <GitBranch className="h-3.5 w-3.5" />
          {hasLineage ? 'Lineage linked' : 'Root record'}
        </div>
        <Link
          to={`/passports/${passport.id}`}
          className="flex items-center gap-1.5 text-sm font-bold text-primary transition-colors hover:text-accent"
        >
          Inspect
        </Link>
      </div>
    </div>
  )
}
