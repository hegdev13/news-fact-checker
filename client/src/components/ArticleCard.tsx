import { AlertTriangle, BarChart2, ChevronRight, Info, ShieldCheck } from 'lucide-react'
import { cn } from '../lib/cn'
import type { NewsArticle } from '../types'

interface ArticleCardProps {
  article: NewsArticle
  onSelect: () => void
}

function getCredibilityBadge(rating: NewsArticle['credibility']) {
  switch (rating) {
    case 'HIGH':
      return { bg: 'bg-[#839958] text-[#F7F4D6]', icon: ShieldCheck, label: 'High Veracity' }
    case 'MEDIUM':
      return { bg: 'bg-[#105666] text-[#F7F4D6]', icon: Info, label: 'Medium Veracity' }
    case 'LOW':
      return { bg: 'bg-[#D3968C] text-[#0A3323]', icon: AlertTriangle, label: 'Low / Disputed' }
    default:
      return { bg: 'bg-gray-500 text-white', icon: Info, label: 'Unrated' }
  }
}

export default function ArticleCard({ article, onSelect }: ArticleCardProps) {
  const badge = getCredibilityBadge(article.credibility)
  const BadgeIcon = badge.icon

  return (
    <div
      onClick={onSelect}
      className="group relative flex flex-col justify-between overflow-hidden rounded-xl border border-[#105666]/20 bg-[#F7F4D6] p-5 shadow-sm transition-all hover:border-[#105666]/50 hover:shadow-md"
    >
      <div className="space-y-3">
        {/* Top Header info */}
        <div className="flex items-center justify-between text-xs">
          <span className="rounded border border-[#839958]/30 bg-[#839958]/20 px-2.5 py-0.5 font-bold uppercase tracking-wider text-[#0A3323]">
            {article.category}
          </span>
          <div className="flex items-center gap-2">
            <span className="font-medium text-[#105666]/60">{article.timestamp}</span>
            <span className={cn('inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-bold', badge.bg)}>
              <BadgeIcon className="h-3 w-3" />
              {badge.label}
            </span>
          </div>
        </div>

        {/* Headline */}
        <h3 className="text-lg font-bold leading-snug text-[#0A3323] transition-colors group-hover:text-[#105666]">
          {article.title}
        </h3>

        {/* Summary Snippet */}
        <p className="line-clamp-2 text-xs leading-relaxed text-[#105666]/90">{article.summary}</p>

        {/* News Bias Breakdown Meter */}
        <div className="pt-2">
          <div className="mb-1.5 flex items-center justify-between text-[11px] font-bold text-[#105666]">
            <span className="flex items-center gap-1">
              <BarChart2 className="h-3.5 w-3.5 text-[#839958]" />
              Coverage Bias Breakdown
            </span>
            <span>{article.sourcesCount} Outlets Reporting</span>
          </div>

          {/* Tri-Color Meter Bar */}
          <div className="flex h-3 w-full overflow-hidden rounded-full bg-[#0A3323]/10 shadow-inner">
            <div
              style={{ width: `${article.biasDistribution.left}%` }}
              className="h-full bg-[#105666] transition-all duration-500"
              title={`Left: ${article.biasDistribution.left}%`}
            />
            <div
              style={{ width: `${article.biasDistribution.center}%` }}
              className="h-full bg-[#839958] transition-all duration-500"
              title={`Center: ${article.biasDistribution.center}%`}
            />
            <div
              style={{ width: `${article.biasDistribution.right}%` }}
              className="h-full bg-[#D3968C] transition-all duration-500"
              title={`Right: ${article.biasDistribution.right}%`}
            />
          </div>

          {/* Percentage Labels */}
          <div className="mt-1 flex justify-between text-[10px] font-bold text-[#105666]/80">
            <span className="text-[#105666]">Left {article.biasDistribution.left}%</span>
            <span className="text-[#0A3323]">Center {article.biasDistribution.center}%</span>
            <span className="text-[#D3968C]">Right {article.biasDistribution.right}%</span>
          </div>
        </div>
      </div>

      {/* Footer Details */}
      <div className="mt-4 flex items-center justify-between border-t border-[#105666]/10 pt-3 text-xs font-semibold text-[#0A3323]">
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-[#105666]/70">Fact Score:</span>
          <span
            className={cn(
              'rounded px-2 py-0.5 text-xs font-extrabold',
              article.reliabilityScore >= 80
                ? 'bg-[#839958] text-[#F7F4D6]'
                : article.reliabilityScore >= 60
                  ? 'bg-[#105666] text-[#F7F4D6]'
                  : 'bg-[#D3968C] text-[#0A3323]',
            )}
          >
            {article.reliabilityScore}/100
          </span>
        </div>

        <div className="flex items-center gap-1 text-[#105666] transition-transform group-hover:translate-x-0.5">
          <span>Detailed Audit</span>
          <ChevronRight className="h-4 w-4" />
        </div>
      </div>
    </div>
  )
}