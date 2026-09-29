import { useEffect, useState } from 'react'
import {
  Compass,
  Filter,
  Info,
  Layers,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import AnalysisModal from './components/AnalyzerModal'
import ArticleCard from './components/ArticleCard'
import { api } from './lib/api'
import { mapDetailToArticle, mapListItemToArticle } from './lib/mapper'
import { MOCK_NEWS_ITEMS, offlineAnalysis } from './lib/mock'
import type { Credibility, NewsArticle, ReportDetail } from './types'

const CATEGORIES = ['All', 'Politics', 'Tech', 'Environment', 'Economy', 'Science', 'World']
const CREDIBILITY_LEVELS: Array<'ALL' | Credibility> = ['ALL', 'HIGH', 'MEDIUM', 'LOW']
const POLL_INTERVAL_MS = 1600
const POLL_TIMEOUT_MS = 150000

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

export default function App() {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('All')
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null)
  const [filterCredibility, setFilterCredibility] = useState<'ALL' | Credibility>('ALL')
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isSeeding, setIsSeeding] = useState(false)
  const [apiOnline, setApiOnline] = useState<boolean | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [articles, setArticles] = useState<NewsArticle[]>([])

  // Load feed: live reports from the backend, or the offline mock feed.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        await api.health()
        const reports = await api.listReports()
        if (cancelled) return
        setApiOnline(true)
        setArticles(reports.map(mapListItemToArticle))
      } catch {
        if (cancelled) return
        setApiOnline(false)
        setArticles(MOCK_NEWS_ITEMS)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const upsertArticle = (article: NewsArticle) => {
    setArticles((prev) => [article, ...prev.filter((a) => a.id !== article.id)])
  }

  const openModal = (article: NewsArticle) => {
    setSelectedArticle(article)
    if (article.full) return
    // Feed items are lightweight; upgrade to full detail on open.
    api
      .getReport(article.id)
      .then((detail: ReportDetail) => {
        const full = mapDetailToArticle(detail)
        setSelectedArticle(full)
        setArticles((prev) => prev.map((a) => (a.id === full.id ? full : a)))
      })
      .catch(() => {
        // Keep the stub open; detail is unavailable.
      })
  }

  const runDemo = async () => {
    setNotice(null)
    setIsSeeding(true)
    try {
      const res = await api.startDemo()
      const reports = await api.listReports()
      setArticles(reports.map(mapListItemToArticle))
      setNotice(`Seeded ${res.count} sample fact-checks from the bundled pipeline.`)
    } catch (err) {
      setNotice(`Demo run failed: ${(err as Error).message}`)
    } finally {
      setIsSeeding(false)
    }
  }

  const handleSearchSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const query = searchQuery.trim()
    if (!query) return

    setIsAnalyzing(true)
    setNotice(null)
    try {
      const { claim_id } = await api.startCheck(query)
      const startedAt = Date.now()
      while (Date.now() - startedAt < POLL_TIMEOUT_MS) {
        await sleep(POLL_INTERVAL_MS)
        const status = await api.pollCheck(claim_id)
        if (status.status === 'done' && status.detail) {
          const article = mapDetailToArticle(status.detail)
          upsertArticle(article)
          setSelectedArticle(article)
          return
        }
        if (status.status === 'error') {
          throw new Error(status.error ?? 'Fact-check failed.')
        }
      }
      throw new Error('Timed out waiting for the check to finish.')
    } catch (err) {
      if (apiOnline === false) {
        // API unreachable — fall back to the simulated analysis flow.
        const article = offlineAnalysis(query)
        upsertArticle(article)
        setSelectedArticle(article)
      } else {
        setNotice(`Could not run the check: ${(err as Error).message}`)
      }
    } finally {
      setIsAnalyzing(false)
    }
  }

  const resetFilters = () => {
    setSelectedCategory('All')
    setFilterCredibility('ALL')
    setSearchQuery('')
  }

  const filteredArticles = articles.filter((article) => {
    const matchesCategory =
      selectedCategory === 'All' || article.category === selectedCategory
    const matchesCredibility =
      filterCredibility === 'ALL' || article.credibility === filterCredibility
    const matchesSearch =
      article.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      article.summary.toLowerCase().includes(searchQuery.toLowerCase())
    return matchesCategory && matchesCredibility && matchesSearch
  })

  return (
    <div className="min-h-screen bg-[#F7F4D6] font-sans text-[#105666] antialiased selection:bg-[#839958] selection:text-[#F7F4D6]">
      <header className="sticky top-0 z-40 border-b border-[#839958]/30 bg-[#0A3323] text-[#F7F4D6] shadow-lg">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-20 items-center justify-between gap-4">
            {/* Brand Logo */}
            <div
              className="flex shrink-0 cursor-pointer items-center gap-3"
              onClick={resetFilters}
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-[#F7F4D6]/20 bg-[#839958] text-xl font-black text-[#0A3323] shadow-md">
                FG
              </div>
              <div className="hidden sm:block">
                <span className="flex items-center gap-1.5 text-2xl font-black tracking-tight text-[#F7F4D6]">
                  Fact<span className="text-[#D3968C]">Ground</span>
                </span>
                <p className="text-[10px] font-semibold uppercase tracking-widest text-[#839958]">
                  Media Bias & Veracity Intelligence
                </p>
              </div>
            </div>

            {/* URL/Topic Search Input */}
            <form onSubmit={handleSearchSubmit} className="relative flex-1 max-w-2xl">
              <div className="relative flex items-center">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Paste article URL or claim to check…"
                  className="w-full bg-[#F7F4D6] py-2.5 pl-11 pr-28 text-sm font-medium text-[#105666] shadow-inner transition-all placeholder:text-[#105666]/60 focus:outline-none focus:ring-2 focus:ring-[#839958] rounded-full"
                />
                <Search className="absolute left-3.5 h-5 w-5 text-[#105666]/70" />
                <button
                  type="submit"
                  disabled={isAnalyzing}
                  className="absolute right-1.5 flex items-center gap-1.5 rounded-full bg-[#105666] px-4 py-1.5 text-xs font-bold text-[#F7F4D6] shadow transition-all duration-200 hover:bg-[#839958]"
                >
                  {isAnalyzing ? (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      Analyzing…
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-3.5 w-3.5 text-[#D3968C]" />
                      Fact Check
                    </>
                  )}
                </button>
              </div>
            </form>

            {/* Status Badge */}
            <div className="hidden shrink-0 items-center gap-4 text-xs font-medium text-[#F7F4D6]/80 lg:flex">
              <div className="flex items-center gap-1.5 rounded-full border border-[#839958]/30 bg-[#105666]/50 px-3 py-1.5">
                <ShieldCheck className="h-4 w-4 text-[#839958]" />
                <span>
                  {apiOnline === null
                    ? 'Connecting…'
                    : apiOnline
                      ? 'Live Audit Active'
                      : 'Offline Demo Feed'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Topics + Veracity filter bar */}
        <div className="border-t border-[#839958]/20 bg-[#105666] px-4 py-2 sm:px-6 lg:px-8">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-2 overflow-x-auto no-scrollbar">
            <div className="flex shrink-0 items-center gap-1.5">
              <span className="mr-2 flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-[#D3968C]">
                <Filter className="h-3 w-3" /> Topics:
              </span>
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setSelectedCategory(cat)}
                  className={`shrink-0 rounded-md px-3 py-1 text-xs font-semibold transition-all ${
                    selectedCategory === cat
                      ? 'bg-[#F7F4D6] text-[#0A3323] shadow-sm'
                      : 'text-[#F7F4D6]/80 hover:bg-[#0A3323]/50 hover:text-[#F7F4D6]'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>

            <div className="hidden shrink-0 items-center gap-2 border-l border-[#839958]/30 pl-4 md:flex">
              <span className="text-[11px] font-medium text-[#F7F4D6]/70">Veracity:</span>
              {CREDIBILITY_LEVELS.map((level) => (
                <button
                  key={level}
                  onClick={() => setFilterCredibility(level)}
                  className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase transition-all ${
                    filterCredibility === level
                      ? 'bg-[#839958] text-[#F7F4D6]'
                      : 'bg-[#0A3323]/40 text-[#F7F4D6]/60 hover:text-[#F7F4D6]'
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Connection / action notice */}
        {apiOnline === false && (
          <div className="mb-6 flex flex-wrap items-center gap-2 rounded-xl border border-[#D3968C] bg-[#D3968C]/15 px-4 py-3 text-xs font-semibold text-[#0A3323]">
            <Info className="h-4 w-4 shrink-0" />
            <span>
              API offline — showing sample data. Start the backend (
              <code className="rounded bg-[#0A3323]/10 px-1.5 py-0.5 font-mono">uvicorn newsfact.web:app</code> or{' '}
              <code className="rounded bg-[#0A3323]/10 px-1.5 py-0.5 font-mono">newsfact-server</code>) to enable
              live fact-checking.
            </span>
          </div>
        )}
        {notice && (
          <div className="mb-6 rounded-xl border border-[#839958] bg-[#839958]/15 px-4 py-3 text-xs font-semibold text-[#0A3323]">
            {notice}
          </div>
        )}

        {/* Banner Section */}
        <div className="relative mb-8 overflow-hidden rounded-2xl border border-[#839958]/30 bg-[#0A3323] p-6 text-[#F7F4D6] shadow-xl md:p-8">
          <div className="pointer-events-none absolute -mr-8 -mt-8 right-0 top-0 h-64 w-64 rounded-full bg-[#105666]/30 blur-3xl" />
          <div className="relative z-10 max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[#839958] bg-[#839958]/30 px-3 py-1 text-xs font-semibold text-[#F7F4D6]">
              <Compass className="h-3.5 w-3.5 text-[#D3968C]" /> Grounded News Verification Engine
            </div>
            <h1 className="mb-3 text-2xl font-extrabold tracking-tight sm:text-4xl">
              Compare Perspectives. <span className="text-[#D3968C]">Expose Blindspots.</span> Verify Facts.
            </h1>
            <p className="mb-6 text-sm leading-relaxed text-[#F7F4D6]/80 sm:text-base">
              FactGround cross-references hundreds of news outlets in real-time, mapping partisan bias
              distribution and checking underlying claims against verifiable databases.
            </p>

            <div className="flex flex-wrap items-center gap-6 border-t border-[#839958]/30 pt-4 text-xs text-[#F7F4D6]/90">
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-full bg-[#105666]" />
                <span>Left & Center-Left Bias</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-full bg-[#839958]" />
                <span>Center / Neutral Coverage</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-full bg-[#D3968C]" />
                <span>Right & Center-Right Bias</span>
              </div>
            </div>
          </div>
        </div>

        {/* Story List Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-xl font-bold text-[#105666]">
              <Layers className="h-5 w-5 text-[#839958]" />
              {selectedCategory === 'All'
                ? 'Latest Fact-Checked Stories'
                : `${selectedCategory} News`}
            </h2>
            <p className="text-xs text-[#105666]/70">
              Showing cross-perspective analysis for {filteredArticles.length} stories
            </p>
          </div>

          <span className="rounded-full border border-[#839958]/40 bg-[#839958]/20 px-3 py-1 text-xs font-semibold text-[#0A3323]">
            Updated in Realtime
          </span>
        </div>

        {filteredArticles.length === 0 ? (
          <div className="rounded-2xl border-2 border-dashed border-[#839958]/40 bg-[#F7F4D6] py-16 text-center">
            <Info className="mx-auto mb-3 h-10 w-10 text-[#D3968C]" />
            {articles.length === 0 ? (
              <>
                <p className="text-lg font-bold text-[#105666]">No fact-checks yet</p>
                <p className="mb-4 text-sm text-[#105666]/70">
                  Run the bundled demo pipeline to seed three sample stories, or paste a claim into the
                  search bar above.
                </p>
                <button
                  onClick={runDemo}
                  disabled={isSeeding}
                  className="inline-flex items-center gap-2 rounded-lg bg-[#0A3323] px-4 py-2 text-xs font-bold text-[#F7F4D6] transition-all hover:bg-[#105666] disabled:opacity-50"
                >
                  {isSeeding ? (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 animate-spin" /> Seeding…
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-3.5 w-3.5 text-[#D3968C]" /> Run demo pipeline
                    </>
                  )}
                </button>
              </>
            ) : (
              <>
                <p className="text-lg font-bold text-[#105666]">No news items match your criteria</p>
                <p className="mb-4 text-sm text-[#105666]/70">
                  Try adjusting your topic filter or search keyword.
                </p>
                <button
                  onClick={resetFilters}
                  className="rounded-lg bg-[#0A3323] px-4 py-2 text-xs font-bold text-[#F7F4D6] transition-all hover:bg-[#105666]"
                >
                  Reset Filters
                </button>
              </>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {filteredArticles.map((article) => (
              <ArticleCard key={article.id} article={article} onSelect={() => openModal(article)} />
            ))}
          </div>
        )}
      </main>

      {selectedArticle && (
        <AnalysisModal article={selectedArticle} onClose={() => setSelectedArticle(null)} />
      )}
    </div>
  )
}