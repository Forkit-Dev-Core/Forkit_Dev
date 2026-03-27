import type {
  Passport,
  PassportEdge,
  PassportTool,
  PassportType,
  RegistryStats,
  VerificationCheck,
  VerificationStatus,
  VerifyPassportResult,
} from '../types'

type CreatePassportPayload = {
  passportType: PassportType
  name: string
  version: string
  creatorName: string
  creatorOrganization?: string
  license: string
  description?: string
  architecture?: string
  taskType?: string
  artifactHash?: string
  baseModelId?: string
  modelId?: string
  systemPromptHash?: string
  endpointHash?: string
  trainingData?: string[]
  tools?: PassportTool[]
}

const now = Date.now()

const LLAMA_BASE_ID =
  '77da08f276ff69ebf13848a027722161102a331d3329bed799eb1d1c69a0c8b4'
const MAMBA_BASE_ID =
  '7cd0099ea666e7c69ca243703525ea5b07c5db6b7c6c959284477a0932092c88'
const LLAMA_FT_ID =
  '34c8088d20e74829f5a6c22c6e539457e062fa32b04ac18ee15c39da98ff9c46'
const SUPPORT_AGENT_ID =
  'b36533b819f6c687c5092b6e733ce2486d6bfb6a3f0bb2fd62f1b28781eca861'

const LLAMA_BASE_ARTIFACT =
  '94f9062fc742503ffe6c2280637b6e787fcb391099ee3d400cb1527a8666e4a0'
const MAMBA_BASE_ARTIFACT =
  'fcb0721c216d56114ec71f6562e67c98073fb1173194366fc4810d25ac50e989'
const LLAMA_FT_ARTIFACT =
  '78a87239ea2a7d2325cefc4fb35f198e81f53f59290cc2b202d672b15612f018'
const SUPPORT_AGENT_PROMPT =
  '5ebade404e2eaf68bd9c6d6ae1920d7604516c2b7fced770929d0ae762b3747b'
const SUPPORT_AGENT_ENDPOINT =
  '85581546f40b31a7934a5773087f2625bd0b9954f097851bca2c88db3910a3ce'

const seedPassports: Passport[] = [
  {
    id: LLAMA_BASE_ID,
    passportType: 'model',
    name: 'llama-3-8b-base',
    version: '1.0.0',
    description:
      'Base ModelPassport for a root text generation model registered in the local Forkit registry.',
    creator: {
      name: 'Meta',
      organization: 'Meta AI',
    },
    license: 'Llama-3-Community',
    verificationStatus: 'verified',
    architecture: 'decoder-only',
    taskType: 'text_generation',
    artifactHash: LLAMA_BASE_ARTIFACT,
    parentHash: null,
    baseModelId: null,
    modelId: null,
    systemPromptHash: null,
    endpointHash: null,
    trainingData: ['Common Crawl references', 'Curated instruction data references'],
    capabilities: {
      modalities: ['text'],
      contextLength: 8192,
      benchmarks: ['MMLU', 'GSM8K'],
    },
    tools: null,
    recordPath: `~/.forkit/registry/models/${LLAMA_BASE_ID}.json`,
    verificationChecks: [
      {
        label: 'Deterministic ID',
        status: 'pass',
        detail: 'Passport ID is a stable SHA-256 derived from model identity fields.',
      },
      {
        label: 'Artifact hash',
        status: 'pass',
        detail: 'Artifact hash is present and matches the sealed model record.',
      },
      {
        label: 'Lineage anchor',
        status: 'pass',
        detail: 'No parent model is expected for this root ModelPassport.',
      },
    ],
    createdAt: new Date(now - 21 * 24 * 60 * 60 * 1000).toISOString(),
    updatedAt: new Date(now - 2 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: MAMBA_BASE_ID,
    passportType: 'model',
    name: 'mamba-2.8b-base',
    version: '1.0.0',
    description:
      'Independent ModelPassport showing a second model family in the same local registry.',
    creator: {
      name: 'State Spaces Inc',
      organization: 'Research Lab',
    },
    license: 'Apache-2.0',
    verificationStatus: 'verified',
    architecture: 'mamba',
    taskType: 'text_generation',
    artifactHash: MAMBA_BASE_ARTIFACT,
    parentHash: null,
    baseModelId: null,
    modelId: null,
    systemPromptHash: null,
    endpointHash: null,
    trainingData: ['Public web corpus references', 'Code data references'],
    capabilities: {
      modalities: ['text'],
      contextLength: 4096,
      benchmarks: ['ARC-C'],
    },
    tools: null,
    recordPath: `~/.forkit/registry/models/${MAMBA_BASE_ID}.json`,
    verificationChecks: [
      {
        label: 'Deterministic ID',
        status: 'pass',
        detail: 'Passport ID remains stable for identical identity inputs.',
      },
      {
        label: 'Artifact hash',
        status: 'pass',
        detail: 'Model artifact hash is stored in the passport and verified.',
      },
      {
        label: 'Registry record',
        status: 'pass',
        detail: 'Passport is available in the local JSON registry and SQLite index.',
      },
    ],
    createdAt: new Date(now - 18 * 24 * 60 * 60 * 1000).toISOString(),
    updatedAt: new Date(now - 3 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: LLAMA_FT_ID,
    passportType: 'model',
    name: 'llama-3-8b-ft',
    version: '1.0.0',
    description:
      'Fine-tuned ModelPassport linked to a base model through `base_model_id` and `parent_hash`.',
    creator: {
      name: 'Alice',
      organization: 'Forkit',
    },
    license: 'Apache-2.0',
    verificationStatus: 'warning',
    architecture: 'decoder-only',
    taskType: 'instruction_following',
    artifactHash: LLAMA_FT_ARTIFACT,
    parentHash: LLAMA_BASE_ARTIFACT,
    baseModelId: LLAMA_BASE_ID,
    modelId: null,
    systemPromptHash: null,
    endpointHash: null,
    trainingData: ['Customer support data references'],
    capabilities: {
      modalities: ['text'],
      contextLength: 8192,
      benchmarks: ['MT-Bench'],
    },
    tools: null,
    recordPath: `~/.forkit/registry/models/${LLAMA_FT_ID}.json`,
    verificationChecks: [
      {
        label: 'Deterministic ID',
        status: 'pass',
        detail: 'Passport ID is stable for the fine-tuned model identity record.',
      },
      {
        label: 'Parent hash chain',
        status: 'pass',
        detail: 'Parent hash resolves to the base model artifact hash.',
      },
      {
        label: 'Training data references',
        status: 'warn',
        detail: 'Training data references are present but dataset hashes are not stored in this mock.',
      },
    ],
    createdAt: new Date(now - 13 * 24 * 60 * 60 * 1000).toISOString(),
    updatedAt: new Date(now - 1 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: SUPPORT_AGENT_ID,
    passportType: 'agent',
    name: 'support-agent',
    version: '1.0.0',
    description:
      'AgentPassport linked to the fine-tuned model via `model_id` and stored in the local registry.',
    creator: {
      name: 'Alice',
      organization: 'Forkit',
    },
    license: 'Apache-2.0',
    verificationStatus: 'verified',
    architecture: 'react',
    taskType: 'customer_support',
    artifactHash: null,
    parentHash: null,
    baseModelId: null,
    modelId: LLAMA_FT_ID,
    systemPromptHash: SUPPORT_AGENT_PROMPT,
    endpointHash: SUPPORT_AGENT_ENDPOINT,
    trainingData: null,
    capabilities: {
      modalities: ['text', 'tools'],
      contextLength: 8192,
      benchmarks: ['Internal eval set'],
    },
    tools: [
      {
        name: 'kb_search',
        version: '1.2.0',
        hash: '36a3c053543c90996ea476b7016d039ca250ca1ac631ffe720c8f597b266fa93',
      },
      {
        name: 'ticketing',
        version: '0.9.1',
        hash: '5bad38ff5ad78e645241bff66b12a2f881d63dcac0bc0a9acff56839b4b99c29',
      },
    ],
    recordPath: `~/.forkit/registry/agents/${SUPPORT_AGENT_ID}.json`,
    verificationChecks: [
      {
        label: 'Model link',
        status: 'pass',
        detail: 'Agent `model_id` resolves to a known ModelPassport in the local registry.',
      },
      {
        label: 'System prompt hash',
        status: 'pass',
        detail: 'Prompt hash is stored instead of raw prompt content.',
      },
      {
        label: 'Endpoint hash',
        status: 'pass',
        detail: 'Endpoint configuration hash is present and verified.',
      },
    ],
    createdAt: new Date(now - 7 * 24 * 60 * 60 * 1000).toISOString(),
    updatedAt: new Date(now - 12 * 60 * 60 * 1000).toISOString(),
  },
]

let passportStore = [...seedPassports]

function normalizeQuery(value: string) {
  return value.trim().toLowerCase()
}

function getShortText(items?: string[] | null) {
  if (!items?.length) {
    return 'No additional references attached.'
  }

  return items.join(', ')
}

async function sha256(value: string) {
  const payload = new TextEncoder().encode(value)
  const digest = await crypto.subtle.digest('SHA-256', payload)
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
}

function buildVerificationStatus(checks: VerificationCheck[]): VerificationStatus {
  if (checks.some((check) => check.status === 'warn')) {
    return 'warning'
  }

  if (checks.some((check) => check.status === 'pending')) {
    return 'pending'
  }

  return 'verified'
}

function getPassportStoragePath(passportType: PassportType, id: string) {
  return `~/.forkit/registry/${passportType === 'model' ? 'models' : 'agents'}/${id}.json`
}

function getPassportsInternal() {
  return [...passportStore]
}

export function getPassports() {
  return getPassportsInternal()
}

export function getPassportById(id: string) {
  return passportStore.find((passport) => passport.id === id)
}

export function searchPassports(query: string, type: 'all' | PassportType = 'all') {
  const normalized = normalizeQuery(query)

  return getPassportsInternal().filter((passport) => {
    const matchesType = type === 'all' || passport.passportType === type

    if (!normalized) {
      return matchesType
    }

    const haystack = [
      passport.id,
      passport.name,
      passport.version,
      passport.creator.name,
      passport.creator.organization,
      passport.description,
      passport.taskType,
      getShortText(passport.trainingData),
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()

    return matchesType && haystack.includes(normalized)
  })
}

export function getRegistryStats(): RegistryStats {
  const passports = getPassportsInternal()

  return {
    totalPassports: passports.length,
    modelPassports: passports.filter((passport) => passport.passportType === 'model').length,
    agentPassports: passports.filter((passport) => passport.passportType === 'agent').length,
    verifiedPassports: passports.filter(
      (passport) => passport.verificationStatus === 'verified',
    ).length,
    lineageLinks: getPassportEdges(passports).length,
    registryPath: '~/.forkit/registry',
    storage: [
      'index.db',
      'lineage.json',
      'models/<sha256>.json',
      'agents/<sha256>.json',
    ],
  }
}

export function getPassportEdges(passports = getPassportsInternal()) {
  return passports.flatMap<PassportEdge>((passport) => {
    const edges: PassportEdge[] = []

    if (passport.baseModelId) {
      edges.push({
        from: passport.baseModelId,
        to: passport.id,
        relation: 'base-model',
      })
    }

    if (passport.passportType === 'agent' && passport.modelId) {
      edges.push({
        from: passport.modelId,
        to: passport.id,
        relation: 'model-link',
      })
    }

    return edges
  })
}

export function getPassportFamily(seedId: string) {
  const queue = [seedId]
  const visited = new Set<string>()

  while (queue.length > 0) {
    const current = queue.shift()

    if (!current || visited.has(current)) {
      continue
    }

    visited.add(current)
    const focus = getPassportById(current)

    passportStore.forEach((passport) => {
      const related =
        passport.id === current ||
        passport.baseModelId === current ||
        passport.modelId === current ||
        passport.id === focus?.baseModelId ||
        passport.id === focus?.modelId

      if (related && !visited.has(passport.id)) {
        queue.push(passport.id)
      }
    })
  }

  return passportStore.filter((passport) => visited.has(passport.id))
}

async function buildPassportFromPayload(payload: CreatePassportPayload) {
  const creator = {
    name: payload.creatorName,
    organization: payload.creatorOrganization || undefined,
  }
  const identityMaterial =
    payload.passportType === 'model'
      ? payload.artifactHash || ''
      : payload.systemPromptHash || payload.endpointHash || payload.modelId || ''
  const deterministicId = await sha256(
    JSON.stringify({
      type: payload.passportType,
      name: payload.name,
      version: payload.version,
      creator,
      identityMaterial,
    }),
  )

  const checks: VerificationCheck[] =
    payload.passportType === 'model'
      ? [
          {
            label: 'Deterministic ID',
            status: 'pass',
            detail: 'Passport ID was generated from the submitted model identity fields.',
          },
          {
            label: 'Artifact hash',
            status: payload.artifactHash ? 'pass' : 'pending',
            detail: payload.artifactHash
              ? 'Artifact hash is present in the draft ModelPassport.'
              : 'Add an artifact hash to match README model passport guidance.',
          },
          {
            label: 'Base model link',
            status: payload.baseModelId ? 'pass' : 'pending',
            detail: payload.baseModelId
              ? 'Base model linkage is attached for lineage tracing.'
              : 'No base model link was attached to this draft.',
          },
        ]
      : [
          {
            label: 'Model link',
            status: payload.modelId ? 'pass' : 'pending',
            detail: payload.modelId
              ? 'Agent `model_id` references an existing ModelPassport.'
              : 'Agent passports should link to a model with `model_id`.',
          },
          {
            label: 'System prompt hash',
            status: payload.systemPromptHash ? 'pass' : 'pending',
            detail: payload.systemPromptHash
              ? 'Prompt hash is stored without exposing raw prompt text.'
              : 'Add a system prompt hash to mirror the README structure.',
          },
          {
            label: 'Endpoint hash',
            status: payload.endpointHash ? 'pass' : 'pending',
            detail: payload.endpointHash
              ? 'Endpoint hash is attached to the agent passport.'
              : 'Endpoint hash is optional but recommended for agent integrity checks.',
          },
        ]

  const passport: Passport = {
    id: deterministicId,
    passportType: payload.passportType,
    name: payload.name,
    version: payload.version,
    description:
      payload.description ||
      (payload.passportType === 'model'
        ? 'Draft ModelPassport created from the open source registration form.'
        : 'Draft AgentPassport created from the open source registration form.'),
    creator,
    license: payload.license,
    verificationStatus: buildVerificationStatus(checks),
    architecture: payload.architecture || null,
    taskType: payload.taskType || null,
    artifactHash: payload.passportType === 'model' ? payload.artifactHash || null : null,
    parentHash:
      payload.passportType === 'model' && payload.baseModelId
        ? getPassportById(payload.baseModelId)?.artifactHash || null
        : null,
    baseModelId: payload.passportType === 'model' ? payload.baseModelId || null : null,
    modelId: payload.passportType === 'agent' ? payload.modelId || null : null,
    systemPromptHash: payload.passportType === 'agent' ? payload.systemPromptHash || null : null,
    endpointHash: payload.passportType === 'agent' ? payload.endpointHash || null : null,
    trainingData: payload.trainingData?.length ? payload.trainingData : null,
    capabilities: {
      modalities: payload.passportType === 'agent' ? ['text', 'tools'] : ['text'],
      contextLength: 8192,
      benchmarks: [],
    },
    tools:
      payload.passportType === 'agent' && payload.tools?.length ? payload.tools : null,
    recordPath: getPassportStoragePath(payload.passportType, deterministicId),
    verificationChecks: checks,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  }

  passportStore = [passport, ...passportStore]
  return passport
}

function buildVerifyResult(passport: Passport): VerifyPassportResult {
  const failedChecks = passport.verificationChecks.filter((check) => check.status !== 'pass')

  return {
    passport,
    verified: failedChecks.length === 0,
    summary:
      failedChecks.length === 0
        ? 'All integrity checks passed for this passport.'
        : `${failedChecks.length} integrity check${failedChecks.length === 1 ? '' : 's'} returned warnings.`,
  }
}

export async function mockFetchApi(endpoint: string, options: RequestInit = {}) {
  await new Promise((resolve) => setTimeout(resolve, 120))

  const method = options.method || 'GET'
  const url = new URL(endpoint, 'http://mock.local')

  if (url.pathname === '/v1/passports') {
    if (method === 'POST') {
      const payload = JSON.parse((options.body as string) || '{}') as CreatePassportPayload
      return buildPassportFromPayload(payload)
    }

    return { passports: getPassportsInternal() }
  }

  if (url.pathname === '/v1/passports/search') {
    const query = url.searchParams.get('q') || ''
    const type = (url.searchParams.get('type') as 'all' | PassportType | null) || 'all'
    return { passports: searchPassports(query, type) }
  }

  if (url.pathname.startsWith('/v1/passports/')) {
    const parts = url.pathname.split('/')
    const passportId = parts[3]
    const passport = getPassportById(passportId)

    if (!passport) {
      throw new Error('Passport not found')
    }

    if (url.pathname.endsWith('/lineage')) {
      const family = getPassportFamily(passportId)
      return {
        focus: passport,
        family,
        edges: getPassportEdges(family),
      }
    }

    if (url.pathname.endsWith('/verify')) {
      return buildVerifyResult(passport)
    }

    return passport
  }

  if (url.pathname === '/v1/registry/stats') {
    return getRegistryStats()
  }

  throw new Error(`Unknown mock endpoint: ${endpoint}`)
}
