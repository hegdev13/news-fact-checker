import type { NewsArticle } from '../types'

/** Offline fallback feed, shown only when the FactGround API is unreachable.
 *  Mirrors the shape the backend mapper produces so the UI never special-cases it. */
export const MOCK_NEWS_ITEMS: NewsArticle[] = [
  {
    id: '1',
    title: 'Global Climate Summit Reaches Landmark Accord on Renewable Energy Investments',
    summary: 'Over 140 nations agreed on a binding protocol to triple renewable energy capacity by 2030, with controversial funding mechanisms for developing nations.',
    category: 'Environment',
    timestamp: '2 hours ago',
    url: 'https://example.com/climate-accord',
    reliabilityScore: 88,
    credibility: 'HIGH',
    sourcesCount: 42,
    biasDistribution: { left: 45, center: 35, right: 20 },
    blindspot: 'Right-leaning outlets are focusing less on clean energy transition and more on cost impact on oil exporters.',
    keyClaims: [
      { text: '$1.5 Trillion pledged for clean energy subsidies over next 5 years.', status: 'VERIFIED', rating: 'High' },
      { text: 'Developing nations will receive immediate zero-interest loans.', status: 'PARTIALLY_TRUE', rating: 'Medium' },
      { text: 'All fossil fuel subsidies will be completely banned by 2028.', status: 'MISLEADING', rating: 'Low' },
    ],
    sources: [
      { name: 'Reuters', bias: 'Center', rating: 'Very High', quote: 'Delegates approved the final text after marathon overnight talks.' },
      { name: 'The Guardian', bias: 'Left', rating: 'High', quote: 'Climate activists praise historic deal despite lingering loopholes.' },
      { name: 'Wall Street Journal', bias: 'Right', rating: 'High', quote: 'Energy sector prepares for economic fallout following new emissions target.' },
    ],
  },
  {
    id: '2',
    title: 'Breakthrough AI Regulation Bill Passes Initial Senate Vote',
    summary: 'Lawmakers push forward landmark legislation requiring safety audits and provenance watermarks for frontier artificial intelligence models.',
    category: 'Tech',
    timestamp: '4 hours ago',
    url: 'https://example.com/ai-regulation-pass',
    reliabilityScore: 92,
    credibility: 'HIGH',
    sourcesCount: 64,
    biasDistribution: { left: 30, center: 50, right: 20 },
    blindspot: 'Minimal coverage in independent tech blogs regarding open-source exemptions.',
    keyClaims: [
      { text: 'Models over 10^26 FLOPs require mandatory federal safety filing.', status: 'VERIFIED', rating: 'High' },
      { text: 'Open-source developers face criminal penalties for non-compliance.', status: 'FALSE', rating: 'High' },
      { text: 'Biometric identification technology remains untouched by bill.', status: 'VERIFIED', rating: 'Medium' },
    ],
    sources: [
      { name: 'Associated Press', bias: 'Center', rating: 'Very High', quote: 'Bipartisan coalition votes 78-22 to advance foundational AI guardrails.' },
      { name: 'TechCrunch', bias: 'Center-Left', rating: 'High', quote: 'Startups express relief over increased thresholds for open source.' },
      { name: 'Fox Business', bias: 'Right', rating: 'Moderate', quote: 'Industry groups warn of innovation dampening compared to overseas competitors.' },
    ],
  },
  {
    id: '3',
    title: 'Central Bank Unexpectedly Pauses Interest Rate Adjustments',
    summary: 'Financial markets react with cautious optimism as monetary authority holds benchmark rates steady citing stabilizing core inflation metrics.',
    category: 'Economy',
    timestamp: '6 hours ago',
    url: 'https://example.com/fed-rate-pause',
    reliabilityScore: 74,
    credibility: 'MEDIUM',
    sourcesCount: 28,
    biasDistribution: { left: 15, center: 40, right: 45 },
    blindspot: 'Left-leaning publications emphasizing housing market distress while right-leaning outlets highlight market gains.',
    keyClaims: [
      { text: 'Inflation dropped to 2.4% annually prior to meeting.', status: 'VERIFIED', rating: 'High' },
      { text: 'Unemployment is predicted to spike by 2% next quarter.', status: 'UNVERIFIED', rating: 'Low' },
    ],
    sources: [
      { name: 'Bloomberg', bias: 'Center', rating: 'Very High', quote: 'Fed chair signals data-dependent approach for upcoming autumn sessions.' },
      { name: 'National Review', bias: 'Right', rating: 'Moderate', quote: 'Central bank hesitation reflects underlying fears of economic stagnation.' },
      { name: 'HuffPost', bias: 'Left', rating: 'Moderate', quote: 'Working families continue to feel squeezed despite hold on interest rates.' },
    ],
  },
  {
    id: '4',
    title: 'Claims of Secret Lunar Mining Expedition Debunked by Space Agencies',
    summary: 'Viral social media videos claiming private corporations started unannounced mineral extractions on the lunar surface are unfounded.',
    category: 'Science',
    timestamp: '12 hours ago',
    url: 'https://example.com/lunar-mining-myth',
    reliabilityScore: 32,
    credibility: 'LOW',
    sourcesCount: 12,
    biasDistribution: { left: 10, center: 20, right: 70 },
    blindspot: 'Mainstream news completely absent from initial viral wave; heavy dissemination on unverified fringe blogs.',
    keyClaims: [
      { text: 'Commercial spacecraft landed near Shackleton Crater in secret.', status: 'FALSE', rating: 'High' },
      { text: 'Satellite imagery proves new heavy structures on lunar south pole.', status: 'MISLEADING', rating: 'High' },
    ],
    sources: [
      { name: 'FactCheck.org', bias: 'Center', rating: 'Very High', quote: 'Images used in video are recycled renderings from a 2018 ESA concept art.' },
      { name: 'Space News', bias: 'Center', rating: 'High', quote: 'NASA confirms all active surface hardware accounts remain fully public.' },
    ],
  },
]

/** Simulated search result used when the API is offline (mimics the old demo flow). */
export function offlineAnalysis(query: string): NewsArticle {
  const isUrl = query.startsWith('http://') || query.startsWith('https://')
  const reliabilityScore = Math.floor(Math.random() * 35) + 60
  const credibility =
    reliabilityScore >= 80 ? 'HIGH' : reliabilityScore >= 60 ? 'MEDIUM' : 'LOW'
  return {
    id: `custom-${Date.now()}`,
    claim: query,
    title: isUrl
      ? `Analyzed Article: ${query.replace(/^https?:\/\//, '').slice(0, 45)}...`
      : `Fact-Check Report: "${query}"`,
    summary: `Automated cross-source audit conducted for "${query}". Factual consensus gathered across 38 global newsrooms and verification databases.`,
    category: 'Custom Verification',
    timestamp: 'Just now',
    url: isUrl ? query : 'https://example.com/verify',
    reliabilityScore,
    credibility,
    sourcesCount: Math.floor(Math.random() * 30) + 15,
    biasDistribution: { left: 35, center: 40, right: 25 },
    blindspot: 'Story has uneven coverage density across partisan media outlets.',
    keyClaims: [
      { text: 'Core factual premise matches peer-reviewed / official documentation.', status: 'VERIFIED', rating: 'High' },
      { text: 'Attributed statistics are accurate within a 3% margin.', status: 'VERIFIED', rating: 'Medium' },
      { text: 'Viral headline overstates immediate impact duration.', status: 'PARTIALLY_TRUE', rating: 'Medium' },
    ],
    sources: [
      { name: 'Global Wire Service', bias: 'Center', rating: 'Very High', quote: 'Official statements confirm baseline data.' },
      { name: 'Independent Monitor', bias: 'Center-Left', rating: 'High', quote: 'Cross-referenced with open primary sources.' },
    ],
  }
}