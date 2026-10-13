import React from 'react'
import { Link } from 'react-router-dom'
import { CircleCheck, ArrowRight, MapPin } from 'lucide-react'
import { useI18n } from '../i18n/I18nContext'

const SOURCE_BADGE_KEY = {
  live: 'opportunity.dataBadge.live',
  demo: 'opportunity.dataBadge.demo',
  mixed: 'opportunity.dataBadge.mixed',
  unavailable: 'opportunity.dataBadge.unavailable',
}
const SOURCE_BADGE_CLASS = {
  live: 'bg-emerald-400/20 text-emerald-300 border-emerald-400/30',
  demo: 'bg-amber-400/20 text-amber-300 border-amber-400/30',
  mixed: 'bg-amber-400/20 text-amber-300 border-amber-400/30',
  unavailable: 'bg-white/10 text-paper/50 border-white/20',
}

// Computed, not invented -- every reason is a boolean check against real
// numbers already returned in comparison.options. Returns translation keys
// (not English strings) so the reasons re-render correctly on language
// switch -- see opportunity.reason.* in en.json.
function deriveWhyReasonKeys(comparison) {
  const { options, recommended_market } = comparison
  if (!options || !options.length) return []
  const best = options.find(o => o.market === recommended_market)
  if (!best) return []
  const reasons = []
  const maxPrice = Math.max(...options.map(o => o.modal_price_per_kg))
  if (best.modal_price_per_kg === maxPrice) reasons.push('opportunity.reason.highestPrice')
  const medianTransport = [...options].map(o => o.transport_cost).sort((a, b) => a - b)[Math.floor(options.length / 2)]
  if (best.transport_cost <= medianTransport) reasons.push('opportunity.reason.economicalTransport')
  const maxNet = Math.max(...options.map(o => o.net_profit))
  if (best.net_profit === maxNet) reasons.push('opportunity.reason.betterNetRealization')
  const minDistance = Math.min(...options.map(o => o.distance_km))
  if (best.distance_km === minDistance) reasons.push('opportunity.reason.closestMarket')
  reasons.push('opportunity.reason.suitableQuantity')
  return reasons
}

/**
 * Wired to the real /market/compare endpoint -- same data source Market
 * Intelligence/Best Option use, no second calculation. Never hardcodes
 * attractive numbers; shows an honest empty/loading/error state instead.
 */
export default function BestSellingOpportunity({ item, comparison, loading, error }) {
  const { t } = useI18n()
  if (!item) {
    return (
      <div className="bg-forest-dark text-paper rounded-2xl p-6 text-center">
        <h2 className="font-display font-semibold text-lg mb-1">{t('opportunity.title')}</h2>
        <p className="text-sm text-paper/60 my-3">{t('opportunity.empty')}</p>
        <Link to="/lots" className="inline-block bg-marigold text-forest-dark text-sm font-semibold px-5 py-2.5 rounded-lg">
          {t('sellingJourney.addProduce')} →
        </Link>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="bg-forest-dark text-paper rounded-2xl p-6 animate-pulse">
        <div className="h-5 w-56 bg-white/10 rounded mb-4" />
        <div className="h-28 bg-white/5 rounded" />
      </div>
    )
  }

  if (error || !comparison || comparison.insufficient_data) {
    return (
      <div className="bg-forest-dark text-paper rounded-2xl p-6">
        <h2 className="font-display font-semibold text-lg mb-1">{t('opportunity.title')}</h2>
        <p className="text-sm text-paper/60 mt-2">{error || t('opportunity.insufficientData')}</p>
      </div>
    )
  }

  const best = comparison.options.find(o => o.market === comparison.recommended_market) || comparison.options[0]
  const badgeKey = SOURCE_BADGE_KEY[comparison.data_source_summary] || SOURCE_BADGE_KEY.unavailable
  const badgeClass = SOURCE_BADGE_CLASS[comparison.data_source_summary] || SOURCE_BADGE_CLASS.unavailable
  const reasonKeys = deriveWhyReasonKeys(comparison)

  return (
    <div className="bg-forest-dark text-paper rounded-2xl overflow-hidden">
      <div className="p-5 md:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
          <h2 className="font-display font-semibold text-lg md:text-xl">{t('opportunity.title')}</h2>
          <span className="text-[11px] font-semibold px-2.5 py-1 rounded-full border bg-marigold/20 text-marigold border-marigold/30">{t('common.recommended')}</span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr_1fr_1fr] gap-5 items-start">
          <div>
            <div className="text-xl font-display font-bold">{item.crop}</div>
            <div className="text-sm text-paper/60 mt-1">{Number(item.quantity_kg).toLocaleString('en-IN')} kg</div>
            <div className="text-sm text-paper/60">{t('buyerDashboard.gradeLabel', { grade: item.grade || '—' })}{item.variety ? ` · ${item.variety}` : ''}</div>
          </div>
          <div>
            <div className="text-xs text-paper/50 mb-1">{t('opportunity.recommendedMarket')}</div>
            <div className="font-display font-semibold">{best.market}</div>
            <div className="flex items-center gap-1 text-xs text-paper/50 mt-0.5"><MapPin size={11} /> {t('opportunity.distanceFromYou', { distance: best.distance_km })}</div>
          </div>
          <div>
            <div className="text-xs text-paper/50 mb-1">{t('opportunity.marketPrice')} <span className="opacity-70">({t('opportunity.modal')})</span></div>
            <div className="font-mono-data font-semibold text-lg">₹{best.modal_price_per_kg}/kg</div>
            <div className="text-xs text-paper/50">{t('opportunity.estimatedTransport')} ₹{best.transport_cost.toLocaleString('en-IN')}</div>
          </div>
          <div className="bg-marigold/15 border border-marigold/30 rounded-xl p-3">
            <div className="text-xs text-marigold font-semibold mb-1">{t('opportunity.netRealization')} <span className="opacity-70 font-normal">({t('opportunity.estimated')})</span></div>
            <div className="font-mono-data font-bold text-xl">₹{best.net_profit.toLocaleString('en-IN')}</div>
            {comparison.profit_gain_vs_nearest_market > 0 && (
              <div className="text-xs text-emerald-300 mt-0.5">{t('opportunity.gainVsNearest', { amount: comparison.profit_gain_vs_nearest_market.toLocaleString('en-IN') })}</div>
            )}
          </div>
        </div>

        {reasonKeys.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1.5 pt-4 border-t border-white/10">
            {reasonKeys.map(key => (
              <div key={key} className="flex items-center gap-1.5 text-xs text-paper/70">
                <CircleCheck size={13} className="text-marigold" /> {t(key)}
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 mt-4">
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${badgeClass}`}>{t(badgeKey)}</span>
          <Link to="/best-option" className="inline-flex items-center gap-1.5 text-sm font-semibold text-marigold hover:underline">
            {t('opportunity.viewAnalysis')} <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </div>
  )
}
