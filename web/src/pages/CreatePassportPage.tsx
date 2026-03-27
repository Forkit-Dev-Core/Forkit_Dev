import { useEffect, useMemo, useState } from 'react'
import { Activity, Box, Info, Loader2, ShieldCheck } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { fetchApi } from '@/lib/api'
import { usePageTitle } from '@/hooks/usePageTitle'
import { getPassports } from '@/lib/mockApi'
import { cn } from '@/lib/utils'
import type { Passport, PassportTool } from '@/types'

function parseLines(value: string) {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

function parseToolLines(value: string): PassportTool[] {
  return parseLines(value).map((line) => {
    const [nameVersion, hash] = line.split('#').map((item) => item.trim())
    const [name, version = '1.0.0'] = nameVersion.split('@').map((item) => item.trim())

    return {
      name,
      version,
      hash: hash || null,
    }
  })
}

const fieldLabelClass = 'mb-2 block text-sm font-semibold text-text'
const inputClass =
  'field-shell w-full rounded-xl border px-4 py-3 text-text placeholder:text-muted transition-all focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20'
const monoInputClass = `${inputClass} font-mono text-sm`
const textareaClass = `${inputClass} resize-none`
const selectClass = `${inputClass} appearance-none`

export function CreatePassportPage() {
  usePageTitle('Register Passport')
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryType = searchParams.get('type')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [passportType, setPassportType] = useState<'model' | 'agent'>(
    queryType === 'agent' ? 'agent' : 'model',
  )
  const [name, setName] = useState('')
  const [version, setVersion] = useState('1.0.0')
  const [creatorName, setCreatorName] = useState('Forkit')
  const [creatorOrganization, setCreatorOrganization] = useState('')
  const [license, setLicense] = useState('Apache-2.0')
  const [architecture, setArchitecture] = useState('')
  const [taskType, setTaskType] = useState('')
  const [artifactHash, setArtifactHash] = useState('')
  const [baseModelId, setBaseModelId] = useState('')
  const [modelId, setModelId] = useState('')
  const [systemPromptHash, setSystemPromptHash] = useState('')
  const [endpointHash, setEndpointHash] = useState('')
  const [trainingData, setTrainingData] = useState('')
  const [toolLines, setToolLines] = useState('')

  useEffect(() => {
    setPassportType(queryType === 'agent' ? 'agent' : 'model')
  }, [queryType])

  useEffect(() => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('type', passportType)
      return next
    })
  }, [passportType, setSearchParams])

  const passports = useMemo(() => getPassports(), [])
  const modelOptions = passports.filter((passport) => passport.passportType === 'model')

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    setLoading(true)

    try {
      const createdPassport = await fetchApi<Passport>('/v1/passports', {
        method: 'POST',
        body: JSON.stringify({
          passportType,
          name,
          version,
          creatorName,
          creatorOrganization: creatorOrganization || undefined,
          license,
          architecture: architecture || undefined,
          taskType: taskType || undefined,
          artifactHash: passportType === 'model' ? artifactHash || undefined : undefined,
          baseModelId: passportType === 'model' ? baseModelId || undefined : undefined,
          modelId: passportType === 'agent' ? modelId || undefined : undefined,
          systemPromptHash:
            passportType === 'agent' ? systemPromptHash || undefined : undefined,
          endpointHash: passportType === 'agent' ? endpointHash || undefined : undefined,
          trainingData: parseLines(trainingData),
          tools: passportType === 'agent' ? parseToolLines(toolLines) : undefined,
        }),
      })

      navigate(`/passports/${createdPassport.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to register passport')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl space-y-8">
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.3fr_0.7fr] xl:items-end">
          <div className="space-y-2">
            <div className="eyebrow">Create a new passport record</div>
            <h1 className="font-display text-3xl font-bold tracking-tight text-text">
              Register Passport
            </h1>
            <p className="max-w-3xl text-muted">
              Create a new ModelPassport or AgentPassport using fields that map directly to
              the public Forkit Core README structure. This page is create-only and
              redirects to Inspect after submit.
            </p>
          </div>

          <div className="rounded-[1.5rem] border border-border/80 bg-surface/86 p-5 shadow-[0_12px_28px_rgba(42,31,85,0.05)]">
            <div className="text-sm font-semibold text-text">Need an existing record instead?</div>
            <p className="mt-2 text-sm text-muted">
              Use Search to filter existing passports or Registry to browse the full mock registry.
            </p>
            <div className="mt-4 flex flex-wrap gap-4 text-sm font-semibold">
              <Link to="/search" className="section-link">
                Search Registry
              </Link>
              <Link to="/registry" className="section-link">
                Browse Registry
              </Link>
            </div>
          </div>
        </div>

        {error ? (
          <div className="rounded-[1.5rem] border border-semantic-danger/20 bg-semantic-danger/8 px-5 py-4 text-sm text-semantic-danger">
            {error}
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <form
              onSubmit={handleSubmit}
              className="overflow-hidden rounded-[2rem] border border-border/80 waterdrop-glass"
            >
              <div className="border-b border-border/70 bg-surface-soft/65 p-8">
                <div className="eyebrow mb-4">Passport Type</div>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => setPassportType('model')}
                    className={cn(
                      'rounded-[1.5rem] border p-6 text-left transition-all',
                      passportType === 'model'
                        ? 'border-primary/30 bg-primary/7 shadow-[0_18px_36px_rgba(42,31,85,0.12)]'
                        : 'border-border bg-white/85 hover:border-primary/25 hover:bg-primary/4',
                    )}
                  >
                    <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-white">
                      <Box className="h-6 w-6" />
                    </div>
                    <div className="text-lg font-semibold text-text">ModelPassport</div>
                    <div className="mt-2 text-sm text-muted">
                      Deterministic model identity with hashes, lineage, and metadata.
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setPassportType('agent')}
                    className={cn(
                      'rounded-[1.5rem] border p-6 text-left transition-all',
                      passportType === 'agent'
                        ? 'border-accent/30 bg-accent/8 shadow-[0_18px_36px_rgba(15,139,141,0.12)]'
                        : 'border-border bg-white/85 hover:border-accent/25 hover:bg-accent/4',
                    )}
                  >
                    <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent text-white">
                      <Activity className="h-6 w-6" />
                    </div>
                    <div className="text-lg font-semibold text-text">AgentPassport</div>
                    <div className="mt-2 text-sm text-muted">
                      Agent record linked to a model with optional prompt and endpoint hashes.
                    </div>
                  </button>
                </div>
              </div>

              <div className="space-y-8 p-8">
                <div className="space-y-2">
                  <div className="eyebrow">Identity fields</div>
                  <p className="text-sm text-muted">
                    Fill the fields that define the passport identity, creator metadata, and
                    README-backed schema values for the new record.
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                  <div>
                    <label className={fieldLabelClass}>Name *</label>
                    <input
                      type="text"
                      required
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      placeholder={passportType === 'model' ? 'llama-3-8b-ft' : 'support-agent'}
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className={fieldLabelClass}>Version *</label>
                    <input
                      type="text"
                      required
                      value={version}
                      onChange={(event) => setVersion(event.target.value)}
                      placeholder="1.0.0"
                      className={inputClass}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                  <div>
                    <label className={fieldLabelClass}>Creator Name *</label>
                    <input
                      type="text"
                      required
                      value={creatorName}
                      onChange={(event) => setCreatorName(event.target.value)}
                      placeholder="Alice"
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className={fieldLabelClass}>Creator Organization</label>
                    <input
                      type="text"
                      value={creatorOrganization}
                      onChange={(event) => setCreatorOrganization(event.target.value)}
                      placeholder="Forkit"
                      className={inputClass}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
                  <div>
                    <label className={fieldLabelClass}>License *</label>
                    <input
                      type="text"
                      required
                      value={license}
                      onChange={(event) => setLicense(event.target.value)}
                      placeholder="Apache-2.0"
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className={fieldLabelClass}>Architecture</label>
                    <input
                      type="text"
                      value={architecture}
                      onChange={(event) => setArchitecture(event.target.value)}
                      placeholder={passportType === 'model' ? 'decoder-only' : 'react'}
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className={fieldLabelClass}>Task Type</label>
                    <input
                      type="text"
                      value={taskType}
                      onChange={(event) => setTaskType(event.target.value)}
                      placeholder={passportType === 'model' ? 'text_generation' : 'customer_support'}
                      className={inputClass}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="eyebrow">Integrity and linkage</div>
                  <p className="text-sm text-muted">
                    Add hashes and lineage links only for the passport you are creating now.
                  </p>
                </div>

                {passportType === 'model' ? (
                  <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                    <div>
                      <label className={fieldLabelClass}>artifact_hash</label>
                      <input
                        type="text"
                        value={artifactHash}
                        onChange={(event) => setArtifactHash(event.target.value)}
                        placeholder="64-character SHA-256 hash"
                        className={monoInputClass}
                      />
                    </div>
                    <div>
                      <label className={fieldLabelClass}>base_model_id</label>
                      <select
                        value={baseModelId}
                        onChange={(event) => setBaseModelId(event.target.value)}
                        className={selectClass}
                      >
                        <option value="">No base model link</option>
                        {modelOptions.map((passport) => (
                          <option key={passport.id} value={passport.id}>
                            {passport.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
                    <div>
                      <label className={fieldLabelClass}>model_id *</label>
                      <select
                        required
                        value={modelId}
                        onChange={(event) => setModelId(event.target.value)}
                        className={selectClass}
                      >
                        <option value="">Select a model passport</option>
                        {modelOptions.map((passport) => (
                          <option key={passport.id} value={passport.id}>
                            {passport.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className={fieldLabelClass}>system_prompt_hash</label>
                      <input
                        type="text"
                        value={systemPromptHash}
                        onChange={(event) => setSystemPromptHash(event.target.value)}
                        placeholder="64-character SHA-256 hash"
                        className={monoInputClass}
                      />
                    </div>
                    <div>
                      <label className={fieldLabelClass}>endpoint_hash</label>
                      <input
                        type="text"
                        value={endpointHash}
                        onChange={(event) => setEndpointHash(event.target.value)}
                        placeholder="64-character SHA-256 hash"
                        className={monoInputClass}
                      />
                    </div>
                  </div>
                )}

                <div className="space-y-2">
                  <div className="eyebrow">Supporting schema fields</div>
                  <p className="text-sm text-muted">
                    Add training references for models or tool references for agents when they
                    are part of the new passport record.
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                  <div>
                    <label className={fieldLabelClass}>Training Data References</label>
                    <textarea
                      value={trainingData}
                      onChange={(event) => setTrainingData(event.target.value)}
                      rows={5}
                      placeholder="One reference per line"
                      className={textareaClass}
                    />
                  </div>

                  {passportType === 'agent' ? (
                    <div>
                      <label className={fieldLabelClass}>Tools</label>
                      <textarea
                        value={toolLines}
                        onChange={(event) => setToolLines(event.target.value)}
                        rows={5}
                        placeholder={'kb_search@1.2.0#<tool hash>\nticketing@0.9.1#<tool hash>'}
                        className={`${textareaClass} font-mono text-sm`}
                      />
                    </div>
                  ) : (
                    <div className="rounded-[1.5rem] border border-border bg-surface-soft p-5 text-sm text-muted">
                      Optional fields are intentionally limited to what the README exposes for a
                      ModelPassport.
                    </div>
                  )}
                </div>

                <div className="flex flex-col gap-4 border-t border-border/70 pt-6 sm:flex-row sm:items-center sm:justify-between">
                  <div className="text-sm text-muted">
                    This creates a new in-memory mock passport and opens the inspect view.
                  </div>
                  <button
                    type="submit"
                    disabled={loading}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-accent px-6 py-3 font-semibold text-[#f1ebdf] shadow-[0_16px_30px_rgba(0,129,144,0.18)] transition-all hover:bg-accent-dark hover:shadow-[0_20px_34px_rgba(0,129,144,0.22)] disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                    {loading ? 'Creating...' : 'Create Mock Passport'}
                  </button>
                </div>
              </div>
            </form>
          </div>

          <div className="space-y-6">
            <div className="rounded-[2rem] border border-border/80 p-6 waterdrop-glass">
              <div className="mb-4 flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-surface-soft text-primary">
                  <Info className="h-5 w-5" />
                </div>
                <div>
                  <div className="text-lg font-semibold text-text">Open source fields</div>
                  <div className="text-sm text-muted">Only README-backed fields are shown.</div>
                </div>
              </div>
              <ul className="space-y-3 text-sm text-muted">
                <li className="rounded-xl border border-border bg-surface-soft px-4 py-3">
                  Model passports support `artifact_hash` and `base_model_id`.
                </li>
                <li className="rounded-xl border border-border bg-surface-soft px-4 py-3">
                  Agent passports support `model_id`, `system_prompt_hash`, and `endpoint_hash`.
                </li>
                <li className="rounded-xl border border-border bg-surface-soft px-4 py-3">
                  All records remain mock-backed until the repo exposes HTTP endpoints.
                </li>
              </ul>
            </div>

            <div className="rounded-[2rem] border border-border/80 p-6 waterdrop-glass">
              <div className="mb-4 flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white">
                  <ShieldCheck className="h-5 w-5" />
                </div>
                <div>
                  <div className="text-lg font-semibold text-text">Creation flow</div>
                  <div className="text-sm text-muted">What this page does, and what it does not do.</div>
                </div>
              </div>

              <ul className="space-y-3 text-sm text-muted">
                <li className="rounded-xl border border-border bg-surface-soft px-4 py-3">
                  Creates one new mock-backed passport record per submit.
                </li>
                <li className="rounded-xl border border-border bg-surface-soft px-4 py-3">
                  Redirects to Inspect so you can review the newly created record.
                </li>
                <li className="rounded-xl border border-border bg-surface-soft px-4 py-3">
                  Existing passports belong in Search or Registry, not on this page.
                </li>
              </ul>

              <div className="mt-4 rounded-xl border border-border bg-surface-soft px-4 py-3 text-sm text-muted">
                {modelOptions.length} model passport{modelOptions.length === 1 ? '' : 's'} are
                currently available for `base_model_id` or `model_id` linking in this mock session.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
