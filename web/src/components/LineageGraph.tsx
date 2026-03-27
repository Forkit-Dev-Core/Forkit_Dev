import { Activity, Cpu } from 'lucide-react'
import { useState } from 'react'
import type { Passport, PassportEdge } from '@/types'
import { cn } from '@/lib/utils'

type LineageGraphProps = {
  passports: Passport[]
  edges: PassportEdge[]
  focusId: string
}

function getPassportDepth(
  passport: Passport,
  passportsById: Map<string, Passport>,
  trail = new Set<string>(),
): number {
  if (trail.has(passport.id)) {
    return 0
  }

  const nextTrail = new Set(trail)
  nextTrail.add(passport.id)

  const parentDepth = passport.baseModelId
    ? getPassportDepth(passportsById.get(passport.baseModelId) ?? passport, passportsById, nextTrail) + 1
    : 0
  const modelDepth =
    passport.passportType === 'agent' && passport.modelId
      ? getPassportDepth(passportsById.get(passport.modelId) ?? passport, passportsById, nextTrail) + 1
      : passport.passportType === 'agent'
        ? 1
        : 0

  return Math.max(parentDepth, modelDepth)
}

function describeLineageNode(passport: Passport) {
  if (passport.passportType === 'agent' && passport.modelId) {
    return 'Linked with model_id'
  }

  if (passport.baseModelId) {
    return 'Derived via base_model_id'
  }

  return 'Root passport'
}

export function LineageGraph({ passports, edges, focusId }: LineageGraphProps) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(focusId)
  const passportsById = new Map(passports.map((passport) => [passport.id, passport]))
  const grouped = passports.reduce<Record<number, Passport[]>>((accumulator, passport) => {
    const depth = getPassportDepth(passport, passportsById)

    if (!accumulator[depth]) {
      accumulator[depth] = []
    }

    accumulator[depth].push(passport)
    return accumulator
  }, {})

  const levels = Object.keys(grouped)
    .map(Number)
    .sort((left, right) => left - right)

  const positions = new Map<string, { x: number; y: number }>()
  levels.forEach((level, levelIndex) => {
    const column = grouped[level]
    const x =
      levels.length === 1 ? 50 : 12 + (76 / (levels.length - 1)) * levelIndex

    column.forEach((passport, rowIndex) => {
      const y = ((rowIndex + 1) / (column.length + 1)) * 78 + 11
      positions.set(passport.id, { x, y })
    })
  })

  const connectedNodes = new Set<string>()
  const connectedEdges = new Set<string>()

  if (hoveredNode) {
    const queue = [hoveredNode]

    while (queue.length > 0) {
      const current = queue.shift()

      if (!current || connectedNodes.has(current)) {
        continue
      }

      connectedNodes.add(current)

      edges.forEach((edge) => {
        if (edge.from === current || edge.to === current) {
          const key = `${edge.from}-${edge.to}-${edge.relation}`
          connectedEdges.add(key)

          if (!connectedNodes.has(edge.from)) {
            queue.push(edge.from)
          }

          if (!connectedNodes.has(edge.to)) {
            queue.push(edge.to)
          }
        }
      })
    }
  }

  return (
    <div className="relative h-[500px] w-full overflow-x-auto rounded-[1.75rem] border border-border/80 bg-surface shadow-[inset_0_1px_0_rgba(255,255,255,0.85),0_14px_34px_rgba(42,31,85,0.06)]">
      <div className="min-w-[960px] h-full relative">
        <div className="pointer-events-none absolute left-0 top-1/2 h-1 w-full -translate-y-1/2 bg-gradient-to-r from-transparent via-primary/10 to-transparent blur-sm" />
        <div className="absolute inset-0 bg-grid-pattern opacity-18" />

        <svg
          className="absolute inset-0 w-full h-full pointer-events-none"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
        >
          {edges.map((edge) => {
            const from = positions.get(edge.from)
            const to = positions.get(edge.to)

            if (!from || !to) {
              return null
            }

            const isHighlighted =
              connectedEdges.size === 0 ||
              connectedEdges.has(`${edge.from}-${edge.to}-${edge.relation}`)
            const dimmed = hoveredNode !== null && !isHighlighted
            const stroke = edge.relation === 'model-link' ? '#008190' : '#f49355'

            return (
              <path
                key={`${edge.from}-${edge.to}-${edge.relation}`}
                d={`M ${from.x} ${from.y} C ${(from.x + to.x) / 2} ${from.y}, ${(from.x + to.x) / 2} ${to.y}, ${to.x} ${to.y}`}
                stroke={stroke}
                strokeWidth={isHighlighted ? 0.75 : 0.4}
                strokeDasharray={edge.relation === 'model-link' ? '2 2' : 'none'}
                opacity={dimmed ? 0.18 : isHighlighted ? 0.95 : 0.4}
                fill="none"
                vectorEffect="non-scaling-stroke"
              />
            )
          })}
        </svg>

        {passports.map((passport) => {
          const position = positions.get(passport.id)

          if (!position) {
            return null
          }

          const highlighted =
            connectedNodes.size === 0 || connectedNodes.has(passport.id)
          const dimmed = hoveredNode !== null && !highlighted
          const isFocus = passport.id === focusId
          return (
            <div
              key={passport.id}
              className="absolute z-20"
              style={{
                left: `${position.x}%`,
                top: `${position.y}%`,
                transform: 'translate(-50%, -50%)',
              }}
              onMouseEnter={() => setHoveredNode(passport.id)}
              onMouseLeave={() => setHoveredNode(focusId)}
            >
              <div
                className={cn(
                  'w-52 cursor-pointer rounded-2xl border p-4 transition-all duration-300',
                  isFocus
                    ? 'border-primary/42 bg-primary/8 shadow-[0_18px_32px_rgba(42,31,85,0.15)]'
                    : 'border-border/80 bg-white/94 shadow-[0_12px_24px_rgba(42,31,85,0.08)]',
                  dimmed && 'opacity-35',
                  highlighted && !dimmed && 'shadow-lg',
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-border/70 bg-surface-soft">
                    {passport.passportType === 'agent' ? (
                      <Activity className="w-5 h-5 text-accent" />
                    ) : (
                      <Cpu className="w-5 h-5 text-primary" />
                    )}
                  </div>
                  <span className="text-[10px] uppercase tracking-[0.2em] text-muted">
                    {passport.passportType}
                  </span>
                </div>
                <div className="mt-3">
                  <div className="text-sm font-semibold text-text">{passport.name}</div>
                  <div className="mt-1 text-[11px] text-muted">
                    {passport.id.slice(0, 12)}...
                  </div>
                  <div className="mt-2 text-[11px] text-muted">
                    {describeLineageNode(passport)}
                  </div>
                </div>
                <div className="mt-3 flex items-center justify-between text-[10px] uppercase tracking-[0.2em]">
                  <span className="text-muted">v{passport.version}</span>
                  <span className="text-accent">{passport.verificationStatus}</span>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
