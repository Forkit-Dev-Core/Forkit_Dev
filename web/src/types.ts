export type PassportType = 'model' | 'agent'
export type VerificationStatus = 'verified' | 'warning' | 'pending'
export type VerificationCheckStatus = 'pass' | 'warn' | 'pending'

export interface Creator {
  name: string
  organization?: string
}

export interface VerificationCheck {
  label: string
  status: VerificationCheckStatus
  detail: string
}

export interface PassportTool {
  name: string
  version: string
  hash?: string | null
}

export interface PassportCapabilities {
  modalities: string[]
  contextLength: number
  benchmarks?: string[]
}

export interface Passport {
  id: string
  passportType: PassportType
  name: string
  version: string
  description: string
  creator: Creator
  license: string
  verificationStatus: VerificationStatus
  architecture?: string | null
  taskType?: string | null
  artifactHash?: string | null
  parentHash?: string | null
  baseModelId?: string | null
  modelId?: string | null
  systemPromptHash?: string | null
  endpointHash?: string | null
  trainingData?: string[] | null
  capabilities?: PassportCapabilities | null
  tools?: PassportTool[] | null
  recordPath: string
  verificationChecks: VerificationCheck[]
  createdAt: string
  updatedAt: string
}

export interface PassportEdge {
  from: string
  to: string
  relation: 'base-model' | 'model-link'
}

export interface RegistryStats {
  totalPassports: number
  modelPassports: number
  agentPassports: number
  verifiedPassports: number
  lineageLinks: number
  registryPath: string
  storage: string[]
}

export interface VerifyPassportResult {
  passport: Passport
  verified: boolean
  summary: string
}
