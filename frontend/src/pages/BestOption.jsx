import React, { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { resolveDefaultLocation } from '../utils/location'
import LoadingSpinner from '../components/LoadingSpinner'
import Badge from '../components/Badge'
import { useI18n } from '../i18n/I18nContext'

/**
 * Phase 18 — Market Intelligence → Best Selling Action
 * Combines: Mandi Price + Forecast + Buyer Demand + Quality + Transport/Storage Cost
 * into a single BEST OPTION recommendation.
 */

export default function BestOption() {
  const { user, role } = useAuth()
  const { t } = useI18n()
  const [crops, setCrops] = useState([])
  const [markets, setMarkets] = useState([])
  const [crop, setCrop] = useState('Soybean')
  const [location, setLocation] = useState(() => resolveDefaultLocation(user))
  const [quantity, setQuantity] = useState(1000)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [marketData, setMarketData] = useState(null)
  const [buyerMatches, setBuyerMatches] = useState([])
  const [sellingWindow, setSellingWindow] = useState(null)
  const [demands, setDemands] = useState([])

  useEffect(() => {
    api.getCrops().then(d => { setCrops(d); if (d.length) setCrop(d[0].name) }).catch(() => {})
    api.getMarkets().then(setMarkets).catch(() => {})
  }, [])

  useEffect(() => {
    if (role === 'farmer' && user?.location) setLocation(user.location)
  }, [user, role])

  async function loadAll() {
    setLoading(true)
    setError('')
    try {
      const [market, window_, demandsData] = await Promise.all([
        api.compareMarkets(crop, quantity, location).catch(() => null),
        api.getSellingWindow(crop, location, quantity).catch(() => null),
        api.getDemands({ crop, status: 'ACTIVE' }).catch(() => []),
      ])
      setMarketData(market)
      setSellingWindow(window_)
      setDemands(Array.isArray(demandsData) ? demandsData.slice(0, 3) : [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (crop && location) loadAll() }, [crop, location])

  const bestMandi = marketData?.options?.[0]
  const bestDemand = demands[0]
  const hasBuyerData = !!bestDemand && Number.isFinite(bestDemand.target_price_per_kg)
  const hasMandiData = !!bestMandi && Number.isFinite(bestMandi.net_profit)

  let bestOptionType = null
  let bestOptionLabel = t('bestOption.noRecommendation')
  if (hasBuyerData && hasMandiData) {
    const demandNetRev = bestDemand.target_price_per_kg * quantity
    bestOptionType = demandNetRev > bestMandi.net_profit ? 'buyer' : 'mandi'
  } else if (hasBuyerData) {
    bestOptionType = 'buyer'
  } else if (hasMandiData) {
    bestOptionType = 'mandi'
  }

  bestOptionLabel = bestOptionType === 'buyer'
    ? t('bestOption.sellToBuyer', { name: bestDemand?.buyer_name || t('bestOption.verifiedBuyer') })
    : hasMandiData ? t('bestOption.sellAtMandi', { market: bestMandi.market }) : t('opportunity.insufficientData')

  return (
    <div>
      <h1 className="font-display text-3xl font-bold mb-1">{t('bestOption.title')}</h1>
      <p className="text-ink/60 dark:text-paper/60 mb-6">
        {t('bestOption.subtitle')}
      </p>

      {/* Controls */}
      <div className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-4 mb-6 flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('common.crop')}</label>
          <select value={crop} onChange={e => setCrop(e.target.value)}
            className="border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper">
            {crops.map(c => <option key={c.name} value={c.name}>{c.emoji} {c.name}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('bestOption.location')}</label>
          <select value={location} onChange={e => setLocation(e.target.value)}
            className="border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper">
            {markets.map(m => <option key={m.name} value={m.name}>{m.name}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('common.quantityKg')}</label>
          <input type="number" value={quantity} min="1"
            onChange={e => setQuantity(Number(e.target.value))}
            className="border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm w-28 bg-white dark:bg-white/5 dark:text-paper" />
        </div>
        <button onClick={loadAll}
          className="bg-forest text-paper px-4 py-2 rounded-lg text-sm font-semibold hover:bg-forest/90">
          {t('bestOption.analyse')}
        </button>
      </div>

      {loading && <LoadingSpinner />}
      {error && <div className="text-red-500 text-sm mb-4">{error}</div>}

      {!loading && (bestMandi || bestDemand) && (
        <>
          {/* BEST OPTION BANNER */}
          <div className="bg-forest text-paper rounded-2xl p-6 mb-6">
            <p className="text-xs font-medium opacity-70 uppercase tracking-widest mb-1">{t('bestOption.bestOption')}</p>
            <h2 className="font-display text-2xl font-bold mb-3">{bestOptionLabel}</h2>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {bestOptionType === 'buyer' && bestDemand && (
                <>
                  <div><p className="text-xs opacity-70">{t('bestOption.buyerPrice')}</p><p className="font-bold text-lg">₹{bestDemand.target_price_per_kg}/kg</p></div>
                  <div><p className="text-xs opacity-70">{t('opportunity.marketPrice')}</p><p className="font-bold">{bestMandi ? `₹${bestMandi.modal_price_per_kg}/kg` : '—'}</p></div>
                  <div>
                    <p className="text-xs opacity-70 flex items-center gap-1">
                      {t('opportunity.estimatedTransport')}
                      <span
                        className="cursor-help opacity-70"
                        title={t('bestOption.transportEstimateTooltip')}
                      >ⓘ</span>
                    </p>
                    <p className="font-bold">{bestMandi ? `₹${bestMandi.transport_cost?.toFixed(0) || 0}` : '—'}</p>
                  </div>
                  <div><p className="text-xs opacity-70">{t('bestOption.verification')}</p><p className="font-bold">{bestDemand.buyer_verified ? t('bestOption.verifiedCheck') : t('bestOption.notVerified')}</p></div>
                </>
              )}
              {bestOptionType === 'mandi' && bestMandi && (
                <>
                  <div><p className="text-xs opacity-70">{t('arrivalIntel.modalPrice')}</p><p className="font-bold text-lg">₹{bestMandi.modal_price_per_kg}/kg</p></div>
                  <div>
                    <p className="text-xs opacity-70 flex items-center gap-1">
                      {t('opportunity.estimatedTransport')}
                      <span
                        className="cursor-help opacity-70"
                        title={t('bestOption.transportEstimateTooltip')}
                      >ⓘ</span>
                    </p>
                    <p className="font-bold">₹{bestMandi.transport_cost?.toFixed(0) || 0}</p>
                  </div>
                  <div><p className="text-xs opacity-70">{t('bestOption.estimatedNetReturn')}</p><p className="font-bold">₹{bestMandi.net_profit?.toLocaleString('en-IN')}</p></div>
                  <div><p className="text-xs opacity-70">{t('dashboard.distance')}</p><p className="font-bold">{bestMandi.distance_km} km</p></div>
                </>
              )}
            </div>
            {/* Impossible-to-miss source label for the figures in this banner --
                especially important when a live price and a demo/estimated
                transport figure appear on the same card. */}
            {bestOptionType === 'mandi' && bestMandi && (
              <div className="mt-3">
                <span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded-full ${
                  bestMandi.data_source === 'live'
                    ? 'bg-emerald-400/20 text-emerald-100'
                    : 'bg-amber-400/20 text-amber-100'
                }`}>
                  {bestMandi.data_source === 'live' ? t('bestOption.liveGovtPrice') : t('bestOption.demoPriceData')} · {t('bestOption.transportAlwaysEstimated')}
                </span>
              </div>
            )}
          </div>

          {/* Side-by-side comparison */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">

            {/* Mandi Options */}
            <div className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-4">
              <h3 className="font-bold mb-3 flex items-center gap-2">🏛️ {t('bestOption.mandiOptions')}</h3>
              {marketData?.options?.length > 0 ? (
                <div className="space-y-2">
                  {marketData.options.slice(0, 4).map((opt, i) => (
                    <div key={i} className={`p-2 rounded-lg text-sm ${i === 0 ? 'bg-forest/10 border border-forest/20' : 'bg-black/3 dark:bg-white/5'}`}>
                      <div className="flex justify-between">
                        <span className="font-semibold">{opt.market}</span>
                        <span className="font-bold">₹{opt.modal_price_per_kg}/kg</span>
                      </div>
                      <div className="flex justify-between text-xs text-ink/50 dark:text-paper/50">
                        <span>{t('opportunity.distanceFromYou', { distance: opt.distance_km })}</span>
                        <span>{t('bestOption.estNet', { amount: opt.net_profit?.toLocaleString('en-IN') })}</span>
                      </div>
                      <span className={`inline-block mt-1 text-[10px] font-bold px-1.5 py-0.5 rounded ${
                        opt.data_source === 'demo'
                          ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
                          : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                      }`}>
                        {opt.data_source === 'demo' ? t('arrivalIntel.tagDemo') : t('arrivalIntel.tagLive')}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-ink/40 dark:text-paper/40">{t('bestOption.noMandiData')}</p>
              )}
            </div>

            {/* Buyer Demands */}
            <div className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-4">
              <h3 className="font-bold mb-3 flex items-center gap-2">🤝 {t('bestOption.activeBuyerDemands')}</h3>
              {demands.length > 0 ? (
                <div className="space-y-2">
                  {demands.map((d, i) => (
                    <div key={i} className={`p-2 rounded-lg text-sm ${i === 0 ? 'bg-forest/10 border border-forest/20' : 'bg-black/3 dark:bg-white/5'}`}>
                      <div className="flex justify-between">
                        <span className="font-semibold">{d.buyer_name || t('bestOption.verifiedBuyer')}</span>
                        <span className="font-bold">₹{d.target_price_per_kg}/kg</span>
                      </div>
                      <div className="text-xs text-ink/50 dark:text-paper/50">
                        {d.required_quantity_kg} kg • {d.delivery_location}
                      </div>
                      {d.buyer_verified && <span className="text-xs text-emerald-600">{t('bestOption.verifiedCheck')}</span>}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-ink/40 dark:text-paper/40">{t('bestOption.noActiveDemandsFor', { crop })}</p>
              )}
            </div>

            {/* Selling Window */}
            <div className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-4">
              <h3 className="font-bold mb-3 flex items-center gap-2">📅 {t('bestOption.sellingWindow')}</h3>
              {sellingWindow ? (
                <>
                  <div className="mb-2">
                    <p className="text-xs text-ink/50 dark:text-paper/50">{t('opportunity.marketPrice')}</p>
                    <p className="font-bold">₹{sellingWindow.current_price}/kg</p>
                  </div>
                  <div className="mb-3">
                    <p className="text-xs font-semibold text-forest uppercase tracking-wide">{t('arrivalIntel.recommendationLabel')}</p>
                    <p className="font-bold">{t(`arrivalIntel.recommendation.${sellingWindow.recommendation}`) !== sellingWindow.recommendation ? t(`arrivalIntel.recommendation.${sellingWindow.recommendation}`) : sellingWindow.recommendation?.replace(/_/g, ' ')}</p>
                  </div>
                  {sellingWindow.is_demo && (
                    <p className="text-xs text-amber-500 mb-2">⚠️ {t('bestOption.demoForecast')}</p>
                  )}
                  <div className="space-y-1">
                    {sellingWindow.options?.slice(0, 3).map(opt => (
                      <div key={opt.label} className={`flex justify-between text-xs p-1.5 rounded ${opt.label === sellingWindow.recommendation ? 'bg-forest/10 font-semibold' : ''}`}>
                        <span>{t(`arrivalIntel.recommendation.${opt.label}`) !== opt.label ? t(`arrivalIntel.recommendation.${opt.label}`) : opt.label?.replace(/_/g, ' ')}</span>
                        <span>₹{opt.estimated_net_revenue?.toLocaleString('en-IN')}</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="text-sm text-ink/40 dark:text-paper/40">{t('bestOption.noForecastData')}</p>
              )}
            </div>
          </div>

          {/* Action buttons for farmer */}
          {role === 'farmer' && (bestMandi || bestDemand) && (
            <div className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-5">
              <h3 className="font-bold mb-3">{t('bestOption.recommendedActions')}</h3>
              <div className="flex flex-wrap gap-3">
                <a href="/lots" className="bg-forest text-paper px-4 py-2 rounded-lg text-sm font-semibold hover:bg-forest/90">
                  {t('bestOption.createCropLot')}
                </a>
                <a href="/buyer-demands" className="border border-forest text-forest px-4 py-2 rounded-lg text-sm font-semibold hover:bg-forest/5">
                  {t('bestOption.browseBuyerDemands')}
                </a>
                <a href="/market-intelligence" className="border border-black/10 dark:border-white/10 text-ink dark:text-paper px-4 py-2 rounded-lg text-sm font-semibold hover:bg-black/5">
                  {t('bestOption.fullMarketAnalysis')}
                </a>
                <a href="/storage" className="border border-black/10 dark:border-white/10 text-ink dark:text-paper px-4 py-2 rounded-lg text-sm font-semibold hover:bg-black/5">
                  {t('bestOption.findStorage')}
                </a>
              </div>
            </div>
          )}
        </>
      )}

      {!loading && !bestMandi && !bestDemand && !error && (
        <div className="text-center py-12 text-ink/40 dark:text-paper/40">
          <p className="text-4xl mb-3">🎯</p>
          <p className="font-medium">{t('bestOption.selectPrompt')}</p>
        </div>
      )}
    </div>
  )
}
