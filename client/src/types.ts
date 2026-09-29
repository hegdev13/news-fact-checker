export type Credibility = 'HIGH' | 'MEDIUM' | 'LOW'

export type ClaimStatus = 'VERIFIED' | 'PARTIALLY_TRUE' | 'MISLEADING' | 'FALSE' | 'UNVERIFIED'

export interface KeyClaim {
  text: string
  status: ClaimStatus
  rating: 'High' | 'Medium' | 'Low'
}

export interface SourceRef {
  name: string
  bias: string
  rating: string
  quote: string
}

export interface BiasDistribution {
  left: number
  center: number
  right: number
}

/** The shape every story card + analyzer modal renders. */
export interface NewsArticle {
  id: string
  claim?: string
  title: string
  summary: string
  category: string
  timestamp: string
  url?: string
  reliabilityScore: number
  credibility: Credibility
  sourcesCount: number
  biasDistribution: BiasDistribution
  blindspot: string
  keyClaims: KeyClaim[]
  sources: SourceRef[]
  /** true when this article carries complete modal data (not a feed stub). */
  full?: boolean
  /** pipeline audit trail (present on full detail) */
  audit?: AuditEvent[]
}

// --- backend API types (newsfact.web) ---

export interface GdeltArticle {
  title: string
  url: string
  source_domain: string
  seen_date: string
  tone: number | null
  language: string | null
}

export type VerdictLabel = 'corroborated' | 'disputed' | 'unverifiable'

export interface ReportListItem {
  claim: string | null
  claim_id: string
  headline: string
  verdict_label: VerdictLabel
  verdict_confidence: number
  created_at: number
  bias_spread: Record<string, number>
  source_finder_count: number
  opposition_count: number
  url: string | null
}

export interface AuditEvent {
  ts: number
  agent: string
  kind: string
  message: string
  data: Record<string, unknown>
}

export interface ReportDetail {
  claim: string
  claim_id: string
  report: {
    headline: string
    body_md: string
    verdict_label: VerdictLabel
    verdict_confidence: number
  }
  verdict: { label: VerdictLabel; confidence: number; reasoning: string; created_at: number } | null
  bias_report: {
    spread: Record<string, number>
    outlets: Array<Record<string, unknown>>
    blindspots: string[]
    dominant_side: string
  } | null
  findings: Record<'source_finder' | 'opposition', { articles: GdeltArticle[]; summary: string }>
  audit_log: AuditEvent[]
  created_at: number
}

export interface CheckStatus {
  claim_id: string
  status: 'queued' | 'running' | 'done' | 'error'
  error?: string
  detail?: ReportDetail
}

export interface HealthStatus {
  status: string
  mode: 'demo' | 'live'
}