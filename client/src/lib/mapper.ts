import type {
  ClaimStatus,
  Credibility,
  KeyClaim,
  NewsArticle,
  ReportDetail,
  ReportListItem,
  SourceRef,
} from '../types'

const FACTUALITY_LABELS: Record<string, string> = {
  'very-high': 'Very High',
  high: 'High',
  'mostly-factual': 'Mostly Factual',
  mixed: 'Moderate',
  low: 'Low',
  unknown: 'Unknown',
}

const TECH_KEYWORDS = [
  'ai', 'artificial intelligence', 'software', 'digital', 'tech', 'algorithm',
  'cyber', 'coding', 'semiconductor', 'chip', 'computer', 'startup', 'robot',
]
const ENV_KEYWORDS = [
  'climate', 'environment', 'energy', 'renewable', 'emission', 'carbon',
  'pollution', 'warming', 'solar', 'wind power', 'flood', 'drought', 'glacier',
]
const ECON_KEYWORDS = [
  'econom', 'inflation', 'gdp', 'bank', 'rate cut', 'interest rate', 'market',
  'stock', 'trade', 'tax', 'unemployment', 'invest', 'currency', 'finance', 'budget',
]
const SCIENCE_KEYWORDS = [
  'study', 'research', 'scientist', 'space', 'lunar', 'mars', 'medical',
  'brain', 'coffee', 'vaccine', 'dna', 'cognition', 'cognitive',
]
const POLITICS_KEYWORDS = [
  'senate', 'parliament', 'election', 'vote', 'bill', 'government', 'minister',
  'president', 'policy', 'republican', 'democrat', 'referendum', 'treaty', 'accord',
]

const KEYWORD_SET: Record<string, string[]> = {
  Politics: POLITICS_KEYWORDS,
  Tech: TECH_KEYWORDS,
  Environment: ENV_KEYWORDS,
  Economy: ECON_KEYWORDS,
  Science: SCIENCE_KEYWORDS,
}

/** Best-effort topic bucket for a claim/headline, used for the strip filter. */
export function guessCategory(claim: string, headline: string): string {
  const haystack = `${claim} ${headline}`.toLowerCase()
  const order: Array<keyof typeof KEYWORD_SET> = [
    'Economy', 'Politics', 'Environment', 'Science', 'Tech',
  ]
  for (const category of order) {
    if (KEYWORD_SET[category].some((kw) => haystack.includes(kw))) return category
  }
  return 'World'
}

/** Relative time for SQLite epoch timestamps. */
export function timeAgo(ts: number): string {
  const seconds = Date.now() / 1000 - ts
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min${minutes === 1 ? '' : 's'} ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days} day${days === 1 ? '' : 's'} ago`
  return new Date(ts * 1000).toLocaleDateString()
}

export function confidenceToCredibility(label: string, confidence: number): Credibility {
  if (label === 'corroborated') return confidence >= 0.75 ? 'HIGH' : 'MEDIUM'
  if (label === 'disputed') return confidence >= 0.6 ? 'MEDIUM' : 'LOW'
  return 'LOW'
}

function claimStatusFor(label: string, confidence: number): ClaimStatus {
  if (label === 'corroborated') return confidence >= 0.6 ? 'VERIFIED' : 'PARTIALLY_TRUE'
  if (label === 'disputed') return 'PARTIALLY_TRUE'
  return 'UNVERIFIED'
}

function ratingFor(confidence: number): KeyClaim['rating'] {
  if (confidence >= 0.7) return 'High'
  if (confidence >= 0.4) return 'Medium'
  return 'Low'
}

function buildSources(detail: ReportDetail): SourceRef[] {
  const sf = detail.findings.source_finder?.articles ?? []
  const opp = detail.findings.opposition?.articles ?? []
  const firstTitle = new Map<string, string>()
  for (const a of [...sf, ...opp]) {
    if (!firstTitle.has(a.source_domain)) firstTitle.set(a.source_domain, a.title)
  }

  const outletByDomain = new Map<string, Record<string, unknown>>()
  for (const o of detail.bias_report?.outlets ?? []) {
    const domain = String(o.domain ?? '')
    if (domain) outletByDomain.set(domain, o)
  }

  const sources: SourceRef[] = []
  for (const [domain, o] of outletByDomain) {
    sources.push({
      name: String(o.name ?? domain),
      bias: String(o.bias ?? 'unknown'),
      rating: FACTUALITY_LABELS[String(o.factuality ?? 'unknown')] ?? 'Unknown',
      quote: firstTitle.get(domain) ?? '',
    })
  }
  for (const domain of firstTitle.keys()) {
    if (outletByDomain.has(domain)) continue
    sources.push({
      name: domain,
      bias: 'unknown',
      rating: 'Unknown',
      quote: firstTitle.get(domain) ?? '',
    })
  }
  return sources
}

function toBiasDistribution(spread: Record<string, number>) {
  const left = spread.left ?? 0
  const center = spread.center ?? 0
  const right = spread.right ?? 0
  const rated = left + center + right || 1
  const pct = (n: number) => Math.round((n / rated) * 100)
  return {
    left: pct(left),
    center: pct(center),
    right: pct(right),
    raw: spread,
  }
}

/** Full backend detail → the UI's story document. */
export function mapDetailToArticle(detail: ReportDetail): NewsArticle {
  const label = detail.report.verdict_label
  const confidence = detail.report.verdict_confidence
  const score = Math.round(confidence * 100)
  const sf = detail.findings.source_finder?.articles ?? []
  const opp = detail.findings.opposition?.articles ?? []
  const oppSummary = detail.findings.opposition?.summary ?? ''
  const spread = detail.bias_report?.spread ?? {}
  const biasPct = toBiasDistribution(spread)

  const keyClaims: KeyClaim[] = [
    {
      text: `Claim under review: "${detail.claim}"`,
      status: claimStatusFor(label, confidence),
      rating: ratingFor(confidence),
    },
  ]
  if (detail.verdict) {
    keyClaims.push({
      text: `Cross-check: ${label}. ${detail.verdict.reasoning}`,
      status: claimStatusFor(label, confidence),
      rating: ratingFor(confidence),
    })
  }
  if (oppSummary) {
    keyClaims.push({
      text: `Counter-argument surfaced: ${oppSummary}`,
      status: label === 'corroborated' ? 'PARTIALLY_TRUE' : 'UNVERIFIED',
      rating: 'Medium',
    })
  }

  const blindspots = detail.bias_report?.blindspots ?? []
  const url = sf.find((a) => a.url)?.url ?? null

  return {
    id: detail.claim_id,
    claim: detail.claim,
    title: detail.report.headline,
    summary: detail.verdict?.reasoning ?? 'No reasoning recorded for this claim.',
    category: guessCategory(detail.claim, detail.report.headline),
    timestamp: timeAgo(detail.created_at),
    url: url ?? undefined,
    reliabilityScore: score,
    credibility: confidenceToCredibility(label, confidence),
    sourcesCount: sf.length + opp.length,
    biasDistribution: { left: biasPct.left, center: biasPct.center, right: biasPct.right },
    blindspot: blindspots.length ? blindspots.join(' ') : 'No blindspot analysis available.',
    keyClaims,
    sources: buildSources(detail),
    full: true,
    audit: detail.audit_log,
  }
}

/** Lightweight list entry → card-only story document (detail fetched on open). */
export function mapListItemToArticle(item: ReportListItem): NewsArticle {
  const confidence = item.verdict_confidence
  const spread = toBiasDistribution(item.bias_spread ?? {})
  const sourcesCount = (item.source_finder_count ?? 0) + (item.opposition_count ?? 0)
  const claim = item.claim ?? item.headline
  return {
    id: item.claim_id,
    claim,
    title: item.headline,
    summary: `Verdict: ${item.verdict_label} (${Math.round(confidence * 100)}/100 confidence) across ${sourcesCount} retrieved article(s).`,
    category: guessCategory(claim, item.headline),
    timestamp: timeAgo(item.created_at),
    url: item.url ?? undefined,
    reliabilityScore: Math.round(confidence * 100),
    credibility: confidenceToCredibility(item.verdict_label, confidence),
    sourcesCount,
    biasDistribution: { left: spread.left, center: spread.center, right: spread.right },
    blindspot: '',
    keyClaims: [],
    sources: [],
    full: false,
  }
}