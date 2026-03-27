import { GitBranch, Layers } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { LineageGraph } from '@/components/LineageGraph'
import { usePageTitle } from '@/hooks/usePageTitle'
import {
  getPassportById,
  getPassportEdges,
  getPassportFamily,
  getPassports,
} from '@/lib/mockApi'

export function LineagePage() {
  usePageTitle('Lineage')
  const [searchParams, setSearchParams] = useSearchParams()
  const passports = getPassports()
  const selectedId =
    searchParams.get('id') || 'b36533b819f6c687c5092b6e733ce2486d6bfb6a3f0bb2fd62f1b28781eca861'
  const focusPassport = getPassportById(selectedId) ?? passports[0]
  const family = getPassportFamily(focusPassport.id)
  const edges = getPassportEdges(family)
  const descendants = family.filter(
    (passport) => passport.baseModelId === focusPassport.id || passport.modelId === focusPassport.id,
  )

  return (
    <div className="mx-auto w-full max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
      <div>
        <h1 className="font-display text-3xl font-bold tracking-tight text-text">Lineage</h1>
        <p className="mt-1 text-muted">
          Trace base model relationships and agent `model_id` links that exist in the open source passport structures.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-primary" />
            Focus Passport
          </CardTitle>
        </CardHeader>
        <CardContent>
          <select
            value={focusPassport.id}
            onChange={(event) => setSearchParams({ id: event.target.value })}
            className="field-shell w-full rounded-xl border px-4 py-3 text-text focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
          >
            {passports.map((passport) => (
              <option key={passport.id} value={passport.id}>
                {passport.name}
              </option>
            ))}
          </select>
        </CardContent>
      </Card>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-[1.5rem] border border-border/80 p-5 waterdrop-glass">
          <div className="eyebrow">Family Nodes</div>
          <div className="mt-2 text-3xl font-bold text-primary">{family.length}</div>
        </div>
        <div className="rounded-[1.5rem] border border-border/80 p-5 waterdrop-glass">
          <div className="eyebrow">Descendants</div>
          <div className="mt-2 text-3xl font-bold text-accent">{descendants.length}</div>
        </div>
        <div className="rounded-[1.5rem] border border-border/80 p-5 waterdrop-glass">
          <div className="eyebrow">Passport Type</div>
          <div className="mt-2 text-sm font-semibold text-text">
            {focusPassport.passportType === 'model' ? 'ModelPassport' : 'AgentPassport'}
          </div>
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <GitBranch className="w-5 h-5 text-primary" />
            Lineage Graph
          </CardTitle>
        </CardHeader>
        <CardContent>
          <LineageGraph passports={family} edges={edges} focusId={focusPassport.id} />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {family.map((passport) => (
          <Link
            key={passport.id}
            to={`/passports/${passport.id}`}
            className="rounded-2xl border border-border/80 p-5 transition-colors hover:border-primary/25 hover:bg-primary/5 waterdrop-glass"
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-lg font-semibold text-text">{passport.name}</div>
                <div className="mt-1 break-all font-mono text-sm text-muted">
                  {passport.id}
                </div>
              </div>
              <Badge
                variant={
                  passport.verificationStatus === 'verified'
                    ? 'success'
                    : passport.verificationStatus === 'warning'
                      ? 'warning'
                      : 'outline'
                }
              >
                {passport.verificationStatus}
              </Badge>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
