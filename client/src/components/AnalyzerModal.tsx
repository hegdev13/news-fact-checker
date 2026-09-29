import { useState } from 'react'
import {
  CheckCircle2,
  ChevronRight,
  Compass,
  ExternalLink,
  Eye,
  Info,
  ScrollText,
  XCircle,
} from 'lucide-react'
import { cn } from '../lib/cn'
import type { NewsArticle } from '../types'

type Tab = 'CLAIMS' | 'SOURCES' | 'BIAS' | 'AUDIT'

interface AnalyzerModalProps {
  article: NewsArticle
  onClose: () => void
}

export default function AnalyzerModal({ article, onClose }: AnalyzerModalProps) {
  const hasAudit = Boolean(article.audit && article.audit.length > 0)
  const [activeTab, setActiveTab] = useState<Tab>('CLAIMS')

  const tabs: Array<{ id: Tab; label: string; available: boolean }> = [
    { id: 'CLAIMS', label: `Key Claims Fact-Check (${article.keyClaims?.length ?? 0})`, available: true },
    { id: 'SOURCES', label: `Source Analysis (${article.sources?.length ?? 0})`, available: true },
    { id: 'BIAS', label: 'Media Bias Distribution', available: true },
    { id: 'AUDIT', label: 'Pipeline Audit Trail', available: hasAudit },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0A3323]/70 p-3 backdrop-blur-sm sm:p-6 animate-fadeIn">
      <div
        className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-[#839958]/50 bg-[#F7F4D6] text-[#105666] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-start justify-between gap-4 border-b border-[#839958]/30 bg-[#0A3323] p-5 text-[#F7F4D6] sm:p-6">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <span className="rounded bg-[#839958] px-2 py-0.5 text-[10px] font-black uppercase text-[#0A3323]">
                {article.category}
              </span>
              <span className="text-xs text-[#F7F4D6]/70">{article.timestamp}</span>
            </div>
            <h2 className="text-xl font-bold leading-tight text-[#F7F4D6] sm:text-2xl">{article.title}</h2>
          </div>

          <button
            onClick={onClose}
            className="rounded-full p-1.5 text-[#F7F4D6]/80 transition-all hover:bg-[#105666] hover:text-[#F7F4D6]"
            aria-label="Close"
          >
            <XCircle className="h-6 w-6" />
          </button>
        </div>

        {/* Modal Navigation Tabs */}
        <div className="flex items-center gap-4 overflow-x-auto border-b border-[#839958]/30 bg-[#105666] px-6 py-2 text-xs font-bold no-scrollbar">
          {tabs.filter((t) => t.available).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                'rounded-lg px-3 py-1.5 whitespace-nowrap transition-all',
                activeTab === tab.id
                  ? 'bg-[#F7F4D6] text-[#0A3323]'
                  : 'text-[#F7F4D6]/70 hover:text-[#F7F4D6]',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Modal Scrollable Body */}
        <div className="flex-1 space-y-6 overflow-y-auto p-6">
          {/* Summary Box */}
          <div className="rounded-xl border border-[#105666]/20 bg-[#0A3323]/5 p-4">
            <h4 className="mb-1 text-xs font-extrabold uppercase tracking-wider text-[#0A3323]">
              Factual Executive Summary
            </h4>
            <p className="text-sm leading-relaxed text-[#105666]">{article.summary}</p>
          </div>

          {/* TAB 1: KEY CLAIMS */}
          {activeTab === 'CLAIMS' && (
            <div className="space-y-4">
              <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-[#0A3323]">
                <CheckCircle2 className="h-4 w-4 text-[#839958]" /> Individual Claim Verification
              </h3>

              <div className="space-y-3">
                {article.keyClaims?.length ? (
                  article.keyClaims.map((claim, idx) => (
                    <div
                      key={idx}
                      className="flex flex-col justify-between gap-3 rounded-xl border border-[#105666]/15 bg-white p-4 shadow-sm sm:flex-row sm:items-center"
                    >
                      <div className="flex-1 space-y-1">
                        <p className="text-sm font-semibold text-[#0A3323]">"{claim.text}"</p>
                        <span className="text-[11px] text-[#105666]/70">
                          Confidence Rating: {claim.rating}
                        </span>
                      </div>

                      <div className="shrink-0">
                        {claim.status === 'VERIFIED' && (
                          <span className="inline-flex items-center gap-1.5 rounded-full bg-[#839958] px-3 py-1 text-xs font-bold text-[#F7F4D6]">
                            <CheckCircle2 className="h-3.5 w-3.5" /> Verified True
                          </span>
                        )}
                        {claim.status === 'PARTIALLY_TRUE' && (
                          <span className="inline-flex items-center gap-1.5 rounded-full bg-[#105666] px-3 py-1 text-xs font-bold text-[#F7F4D6]">
                            <Info className="h-3.5 w-3.5" /> Needs Context
                          </span>
                        )}
                        {(claim.status === 'MISLEADING' || claim.status === 'FALSE') && (
                          <span className="inline-flex items-center gap-1.5 rounded-full bg-[#D3968C] px-3 py-1 text-xs font-bold text-[#0A3323]">
                            <XCircle className="h-3.5 w-3.5" /> {claim.status}
                          </span>
                        )}
                        {claim.status === 'UNVERIFIED' && (
                          <span className="inline-flex items-center gap-1.5 rounded-full bg-[#D3968C]/30 px-3 py-1 text-xs font-bold text-[#0A3323]">
                            <Info className="h-3.5 w-3.5" /> Unverified
                          </span>
                        )}
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-[#105666]/70">Load the full report to see claim-level detail.</p>
                )}
              </div>
            </div>
          )}

          {/* TAB 2: SOURCE PERSPECTIVES */}
          {activeTab === 'SOURCES' && (
            <div className="space-y-4">
              <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-[#0A3323]">
                <Compass className="h-4 w-4 text-[#105666]" /> Reporting Outlets Retrieved
              </h3>

              <div className="grid grid-cols-1 gap-3">
                {article.sources?.length ? (
                  article.sources.map((src, idx) => (
                    <div key={idx} className="space-y-2 rounded-xl border border-[#105666]/15 bg-white p-4 shadow-sm">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-bold text-[#0A3323]">{src.name}</span>
                        <div className="flex items-center gap-2 text-xs">
                          <span className="rounded border border-[#105666]/20 bg-[#F7F4D6] px-2 py-0.5 font-semibold text-[#105666]">
                            Bias: {src.bias}
                          </span>
                          <span className="rounded bg-[#839958]/20 px-2 py-0.5 font-bold text-[#0A3323]">
                            Veracity: {src.rating}
                          </span>
                        </div>
                      </div>
                      {src.quote && (
                        <p className="rounded border-l-2 border-[#839958] bg-[#F7F4D6]/50 p-2.5 text-xs italic text-[#105666]/90">
                          "{src.quote}"
                        </p>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-[#105666]/70">Load the full report to see retrieved outlets.</p>
                )}
              </div>
            </div>
          )}

          {/* TAB 3: MEDIA BIAS & BLINDSPOT */}
          {activeTab === 'BIAS' && (
            <div className="space-y-6">
              <div>
                <h3 className="mb-2 text-sm font-bold uppercase tracking-wider text-[#0A3323]">
                  Partisan Coverage Distribution
                </h3>
                <div className="space-y-3 rounded-xl border border-[#105666]/15 bg-white p-4">
                  <div className="flex h-4 w-full overflow-hidden rounded-full bg-[#0A3323]/10">
                    <div
                      style={{ width: `${article.biasDistribution.left}%` }}
                      className="h-full bg-[#105666]"
                      title="Left"
                    />
                    <div
                      style={{ width: `${article.biasDistribution.center}%` }}
                      className="h-full bg-[#839958]"
                      title="Center"
                    />
                    <div
                      style={{ width: `${article.biasDistribution.right}%` }}
                      className="h-full bg-[#D3968C]"
                      title="Right"
                    />
                  </div>

                  <div className="grid grid-cols-3 border-t border-[#105666]/10 pt-2 text-center text-xs font-bold">
                    <div className="rounded bg-[#105666]/10 p-2 text-[#105666]">
                      Left Outlets
                      <div className="text-lg font-black">{article.biasDistribution.left}%</div>
                    </div>
                    <div className="rounded bg-[#839958]/10 p-2 text-[#0A3323]">
                      Center Outlets
                      <div className="text-lg font-black">{article.biasDistribution.center}%</div>
                    </div>
                    <div className="rounded bg-[#D3968C]/20 p-2 text-[#0A3323]">
                      Right Outlets
                      <div className="text-lg font-black">{article.biasDistribution.right}%</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Blindspot Analysis */}
              <div className="space-y-1 rounded-xl border border-[#D3968C] bg-[#D3968C]/20 p-4">
                <h4 className="flex items-center gap-1.5 text-xs font-black uppercase text-[#0A3323]">
                  <Eye className="h-4 w-4 text-[#0A3323]" /> Ground News Blindspot Warning
                </h4>
                <p className="text-xs font-medium leading-relaxed text-[#0A3323]">{article.blindspot}</p>
              </div>
            </div>
          )}

          {/* TAB 4: PIPELINE AUDIT TRAIL */}
          {activeTab === 'AUDIT' && (
            <div className="space-y-4">
              <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-[#0A3323]">
                <ScrollText className="h-4 w-4 text-[#105666]" /> What the multi-agent pipeline did
              </h3>
              <div className="space-y-1.5">
                {article.audit?.map((event, idx) => (
                  <div
                    key={idx}
                    className="flex items-start gap-3 rounded-lg border border-[#105666]/10 bg-white px-3 py-2 text-xs"
                  >
                    <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#839958]" />
                    <div>
                      <span className="font-bold text-[#0A3323]">{event.agent}</span>{' '}
                      <span className="font-mono text-[10px] capitalize text-[#839958]">[{event.kind}]</span>
                      <p className="text-[#105666]/90">{event.message}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between border-t border-[#105666]/20 bg-[#0A3323]/5 p-4 text-xs font-bold">
          <div className="flex items-center gap-2">
            <span>Overall Score:</span>
            <span className="rounded-md bg-[#0A3323] px-2.5 py-1 font-mono text-[#F7F4D6]">
              {article.reliabilityScore} / 100
            </span>
          </div>

          {article.url ? (
            <a
              href={article.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg bg-[#0A3323] px-4 py-2 text-[#F7F4D6] transition-all hover:bg-[#105666]"
            >
              <span>Read Original Article</span>
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          ) : (
            <a
              href="https://gdeltproject.org"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg bg-[#0A3323] px-4 py-2 text-[#F7F4D6] transition-all hover:bg-[#105666]"
            >
              <span>Sources via GDELT</span>
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
      </div>
    </div>
  )
}