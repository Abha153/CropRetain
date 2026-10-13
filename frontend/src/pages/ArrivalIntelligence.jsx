import React, { useEffect, useState } from 'react'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { resolveDefaultLocation } from '../utils/location'
import { useTheme } from '../context/ThemeContext'
import LoadingSpinner from '../components/LoadingSpinner'
import Badge from '../components/Badge'
import { useI18n } from '../i18n/I18nContext'

const SIGNAL_COLORS = {
  STRONG: 'green',
  POSITIVE: 'green',
  NEUTRAL: 'gray',
  NEGATIVE: 'orange',
  WEAK: 'red',
  UNKNOWN: 'gray',
}

const RISK_COLORS = {
  LOW: 'green',
  MEDIUM: 'orange',
  HIGH: 'red',
}

const WINDOW_ICONS = {
  SELL_NOW: '⚡',
  WAIT_5_DAYS: '⏳',
  WAIT_7_DAYS: '⏳',
  STORE_15_DAYS: '🏭',
}

const CROP_KEY_MAP = {
  Tomato: 'auth.crop.tomato',
  'Paddy (Rice)': 'auth.crop.paddyRice',
  Wheat: 'auth.crop.wheat',
  Potato: 'auth.crop.potato',
  Onion: 'auth.crop.onion',
  Soybean: 'auth.crop.soybean',
  Maize: 'auth.crop.maize',
  'Chana (Gram)': 'auth.crop.chanaGram',
  Groundnut: 'auth.crop.groundnut',
  Mustard: 'auth.crop.mustard',
  Sugarcane: 'auth.crop.sugarcane',
}

function getLocalizedCropName(name, t) {
  const key = CROP_KEY_MAP[name]
  return key ? t(key) : name
}

export default function ArrivalIntelligence() {
  const { user, role } = useAuth()
  const { theme } = useTheme()
  const { t } = useI18n()
  const axisColor = theme === 'dark' ? '#EEF0FB' : '#1B2140'
  const gridColor = theme === 'dark' ? 'rgba(247,243,234,0.12)' : '#eee'

  const [crops, setCrops] = useState([])
  const [markets, setMarkets] = useState([])
  const [crop, setCrop] = useState('Soybean')
  const [market, setMarket] = useState(() => resolveDefaultLocation(user))
  const [quantity, setQuantity] = useState(1000)
  const [days, setDays] = useState(14)

  const [arrivals, setArrivals] = useState(null)
  const [window_, setWindow_] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getCrops().then(d => { setCrops(d); if (d.length) setCrop(d[0].name) }).catch(() => {})
    api.getMarkets().then(setMarkets).catch(() => {})
  }, [])

  useEffect(() => {
    if (role === 'farmer' && user?.location) setMarket(user.location)
  }, [user, role])

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [arr, win] = await Promise.all([
        api.getArrivals(crop, market, days),
        api.getSellingWindow(crop, market, quantity),
      ])
      setArrivals(arr)
      setWindow_(win)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (crop && market) loadData() }, [crop, market])

  const chartData = arrivals?.data?.map(d => ({
    date: d.date?.slice(5), // MM-DD
    arrivals: d.arrivals_tonnes,
    price: d.modal_price,
  })) || []

  const RECOMMENDATION_KEY = {
    SELL_NOW: 'arrivalIntel.recommendation.SELL_NOW',
    WAIT_5_DAYS: 'arrivalIntel.recommendation.WAIT_5_DAYS',
    WAIT_7_DAYS: 'arrivalIntel.recommendation.WAIT_7_DAYS',
    STORE_15_DAYS: 'arrivalIntel.recommendation.STORE_15_DAYS',
  }

  return (
    <div>
      <h1 className="font-display text-3xl font-bold mb-1">{t('navArrival')}</h1>
      <p className="text-ink/60 dark:text-paper/60 mb-6">{t('arrivalIntel.subtitle')}</p>

      {/* Controls */}
      <div className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-4 mb-6 flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('common.crop')}</label>
          <select value={crop} onChange={e => setCrop(e.target.value)}
            className="border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper">
            {crops.map(c => <option key={c.name} value={c.name}>{c.emoji} {getLocalizedCropName(c.name, t)}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('ui.market')}</label>
          <select value={market} onChange={e => setMarket(e.target.value)}
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
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('arrivalIntel.historyDays')}</label>
          <select value={days} onChange={e => setDays(Number(e.target.value))}
            className="border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper">
            {[7, 14, 30, 60].map(d => <option key={d} value={d}>{t('arrivalIntel.daysCount', { count: d })}</option>)}
          </select>
        </div>
        <button onClick={loadData}
          className="bg-forest text-paper px-4 py-2 rounded-lg text-sm font-semibold hover:bg-forest/90">
          {t('common.refresh')}
        </button>
      </div>

      {loading && <LoadingSpinner />}
      {error && <div className="text-red-500 text-sm mb-4">{error}</div>}

      {!arrivals && !loading && (
        <div className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-5 text-sm text-ink/60 dark:text-paper/60">
          {t('arrivalIntel.noDataYet')}
        </div>
      )}

      {arrivals?.available && (
        <>
          {arrivals.is_demo && (
            <div className="mb-4 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg text-amber-700 dark:text-amber-300 text-xs">
              {t('arrivalIntel.demoDisclaimer')}
            </div>
          )}
          {/* Dedicated arrival-volume freshness label -- distinct from the
              price-level banner above. arrivals_status can be "demo" or
              "mixed" even when the price data itself is live, because the
              verified live mandi-price source doesn't publish arrival
              volume at all yet. */}
          {!arrivals.is_demo && arrivals.arrivals_status && arrivals.arrivals_status !== 'live' && (
            <div className="mb-4 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg text-amber-700 dark:text-amber-300 text-xs">
              {t('arrivalIntel.arrivalsDisclaimer')}
            </div>
          )}

          {/* Summary cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
            {[
              { label: t('arrivalIntel.modalPrice'), value: `₹${arrivals.summary.modal_price}/kg`, sub: arrivals.summary.as_of_date, tag: arrivals.is_demo ? 'demo' : 'live' },
              { label: t('arrivalIntel.minPrice'), value: `₹${arrivals.summary.min_price}/kg`, sub: '' },
              { label: t('arrivalIntel.maxPrice'), value: `₹${arrivals.summary.max_price}/kg`, sub: '' },
              {
                label: t('arrivalIntel.todaysArrivals'),
                value: arrivals.summary.today_arrivals_tonnes != null ? `${arrivals.summary.today_arrivals_tonnes} t` : t('arrivalIntel.notApplicable'),
                sub: arrivals.summary.arrival_change_pct != null
                  ? t(arrivals.summary.arrival_change_pct > 0 ? 'arrivalIntel.changeUpVsYesterday' : 'arrivalIntel.changeDownVsYesterday', { pct: Math.abs(arrivals.summary.arrival_change_pct) })
                  : '',
                color: arrivals.summary.arrival_change_pct < 0 ? 'text-red-500' : 'text-emerald-600',
                tag: arrivals.arrivals_status,
              },
              {
                label: t('arrivalIntel.priceTrend'),
                value: arrivals.summary.price_change_pct != null
                  ? `${arrivals.summary.price_change_pct > 0 ? '↑' : '↓'} ${Math.abs(arrivals.summary.price_change_pct)}%`
                  : '—',
                color: arrivals.summary.price_change_pct > 0 ? 'text-emerald-600' : 'text-red-500',
              },
              {
                label: t('arrivalIntel.marketSignal'),
                badge: arrivals.summary.demand_signal,
                badgeColor: SIGNAL_COLORS[arrivals.summary.demand_signal],
                sub: arrivals.summary.signal_explanation,
              },
            ].map((card, i) => (
              <div key={i} className="bg-white dark:bg-white/5 rounded-xl border border-black/5 dark:border-white/10 p-3">
                <p className="text-xs text-ink/50 dark:text-paper/50 mb-1">{card.label}</p>
                {card.badge ? (
                  <Badge color={card.badgeColor}>{t(`arrivalIntel.signal.${card.badge}`)}</Badge>
                ) : (
                  <p className={`font-bold text-sm ${card.color || 'text-ink dark:text-paper'}`}>{card.value}</p>
                )}
                {card.tag && (
                  <span className={`inline-block mt-1 text-[10px] font-bold px-1.5 py-0.5 rounded ${
                    card.tag === 'live'
                      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                      : card.tag === 'demo' || card.tag === 'mixed'
                      ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
                      : 'bg-black/5 text-ink/50 dark:bg-white/10 dark:text-paper/50'
                  }`}>
                    {card.tag === 'live' ? t('arrivalIntel.tagLive') : card.tag === 'mixed' ? t('arrivalIntel.tagMixed') : card.tag === 'unavailable' ? t('arrivalIntel.tagNA') : t('arrivalIntel.tagDemo')}
                  </span>
                )}
                {card.sub && <p className="text-xs text-ink/40 dark:text-paper/40 mt-0.5">{card.sub}</p>}
              </div>
            ))}
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            <div className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-4">
              <h3 className="font-semibold text-sm mb-3">{t('arrivalIntel.arrivalVolumesTonnes')}</h3>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                  <XAxis dataKey="date" tick={{ fill: axisColor, fontSize: 10 }} />
                  <YAxis tick={{ fill: axisColor, fontSize: 10 }} />
                  <Tooltip formatter={(v) => [`${v} t`, t('arrivalIntel.arrivals')]} />
                  <Bar dataKey="arrivals" fill="#166534" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-4">
              <h3 className="font-semibold text-sm mb-3">{t('arrivalIntel.priceTrendRsKg')}</h3>
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                  <XAxis dataKey="date" tick={{ fill: axisColor, fontSize: 10 }} />
                  <YAxis tick={{ fill: axisColor, fontSize: 10 }} />
                  <Tooltip formatter={(v) => [`₹${v}/kg`, t('arrivalIntel.modalPrice')]} />
                  <Line type="monotone" dataKey="price" stroke="#166534" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}

      {/* Selling Window */}
      {window_ && (
        <div>
          <h2 className="font-display text-2xl font-bold mb-1">🎯 {t('arrivalIntel.bestSellingWindow')}</h2>
          <p className="text-ink/60 dark:text-paper/60 mb-4 text-sm">
            {t('arrivalIntel.forecastDisclaimer')}
          </p>

          {/* Recommendation banner */}
          <div className="bg-forest text-paper rounded-2xl p-5 mb-6">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-3xl">{WINDOW_ICONS[window_.recommendation] || '📊'}</span>
              <div>
                <p className="text-xs font-medium opacity-70 uppercase tracking-wide">{t('arrivalIntel.recommendationLabel')}</p>
                <p className="font-bold text-xl">{t(RECOMMENDATION_KEY[window_.recommendation] || window_.recommendation)}</p>
              </div>
            </div>
            <p className="text-sm opacity-90">{t('arrivalIntel.recommendationExplanation')}</p>
          </div>

          {/* Options */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            {window_.options?.map(opt => (
              <div key={opt.label}
                className={`rounded-2xl border p-4 ${
                  opt.label === window_.recommendation
                    ? 'border-forest bg-forest/5 dark:bg-forest/10'
                    : 'border-black/5 dark:border-white/10 bg-white dark:bg-white/5'
                }`}>
                <div className="flex items-center justify-between mb-2">
                  <p className="font-bold text-sm">{t(RECOMMENDATION_KEY[opt.label] || opt.label)}</p>
                  {opt.label === window_.recommendation && (
                    <span className="text-xs bg-forest text-paper px-2 py-0.5 rounded-full">{t('arrivalIntel.best')}</span>
                  )}
                </div>
                <div className="space-y-1 text-xs text-ink/60 dark:text-paper/60">
                  <div className="flex justify-between">
                    <span>{t('arrivalIntel.avgPrice')}</span>
                    <span className="font-semibold text-ink dark:text-paper">₹{opt.expected_price_range.avg}/kg</span>
                  </div>
                  <div className="flex justify-between">
                    <span>{t('arrivalIntel.storageCost')}</span>
                    <span className="font-semibold text-ink dark:text-paper">₹{opt.storage_cost.toLocaleString('en-IN')}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>{t('arrivalIntel.netRevenue')}</span>
                    <span className="font-bold text-forest">₹{opt.estimated_net_revenue.toLocaleString('en-IN')}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>{t('arrivalIntel.vsSellNow')}</span>
                    <span className={`font-semibold ${opt.additional_revenue_vs_now >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                      {opt.additional_revenue_vs_now >= 0 ? '+' : ''}₹{opt.additional_revenue_vs_now.toLocaleString('en-IN')}
                    </span>
                  </div>
                  <div className="flex justify-between pt-1">
                    <span>{t('arrivalIntel.risk')}</span>
                    <Badge color={RISK_COLORS[opt.risk]} size="sm">{t(`arrivalIntel.riskLevel.${opt.risk}`)}</Badge>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && !arrivals?.available && (
        <div className="text-center py-12 text-ink/40 dark:text-paper/40">
          <p className="text-4xl mb-3">📊</p>
          <p className="font-medium">{t('arrivalIntel.noDataFor', { crop: getLocalizedCropName(crop, t), market })}</p>
          <p className="text-sm mt-1">{t('arrivalIntel.tryDifferent')}</p>
        </div>
      )}
    </div>
  )
}
