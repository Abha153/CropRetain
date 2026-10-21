import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import {
  Package, Briefcase, ShoppingCart, Bell, Bot, Truck, Handshake, Calculator,
  MapPin, ArrowRight, TrendingUp, TrendingDown, Minus, LineChart as LineChartIcon, ScrollText,
} from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../i18n/I18nContext'
import StatCard from '../components/StatCard'
import Badge from '../components/Badge'
import LoadingSpinner from '../components/LoadingSpinner'
import SellingJourney from '../components/SellingJourney'
import WeatherCard from '../components/WeatherCard'
import BestSellingOpportunity from '../components/BestSellingOpportunity'
import FarmHealthCard from '../components/FarmHealthCard'
import { selectFocusJourney } from '../utils/sellingJourney'

const TXN_STATUS_TONE = {
  OFFER_ACCEPTED: 'info', ORDER_CONFIRMED: 'info', LOGISTICS_PENDING: 'warning',
  IN_TRANSIT: 'marigold', DELIVERED: 'success', PAYMENT_PENDING: 'warning',
  PAYMENT_INITIATED: 'info', PAYMENT_RECEIVED: 'success', COMPLETED: 'forest', completed: 'forest',
}

const DATA_BADGE_KEY = {
  live: 'opportunity.dataBadge.live',
  demo: 'opportunity.dataBadge.demo',
  mixed: 'opportunity.dataBadge.mixed',
  unavailable: 'opportunity.dataBadge.unavailable',
}
const DATA_BADGE_CLASS = {
  live: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  demo: 'bg-amber-50 text-amber-700 border-amber-200',
  mixed: 'bg-amber-50 text-amber-700 border-amber-200',
  unavailable: 'bg-gray-100 text-gray-500 border-gray-200',
}

function greetingKey() {
  const hour = new Date().getHours()
  if (hour < 12) return 'dashboard.goodMorning'
  if (hour < 17) return 'dashboard.goodAfternoon'
  return 'dashboard.goodEvening'
}

// Simple data-driven initials avatar -- no fabricated photo, just the
// farmer's own name initials on the brand palette. Gives the header a
// little warmth without inventing anything.
function InitialsAvatar({ name }) {
  const initials = (name || '?').trim().split(/\s+/).slice(0, 2).map(w => w[0]?.toUpperCase()).join('')
  return (
    <div className="w-11 h-11 rounded-full bg-forest text-paper flex items-center justify-center font-display font-semibold text-sm shrink-0">
      {initials || '?'}
    </div>
  )
}

function TrendIcon({ direction }) {
  if (direction === 'up' || direction === 'increasing') return <TrendingUp size={14} className="text-emerald-600" />
  if (direction === 'down' || direction === 'decreasing') return <TrendingDown size={14} className="text-red-500" />
  return <Minus size={14} className="text-ink/40" />
}

// A quiet section label -- icon + text, no card, no all-caps eyebrow chrome.
// Used to give the page real visual hierarchy (per redesign brief) without
// adding more boxes to an already card-heavy layout.
function SectionLabel({ icon: Icon, children }) {
  return (
    <div className="flex items-center gap-2 text-ink/40 dark:text-paper/40 mb-3">
      <Icon size={15} />
      <span className="text-xs font-semibold tracking-wide">{children}</span>
    </div>
  )
}

export default function FarmerDashboard() {
  const { user } = useAuth()
  const { t } = useI18n()
  const [listings, setListings] = useState(null)
  const [lots, setLots] = useState(null)
  const [transactions, setTransactions] = useState(null)
  const [notifications, setNotifications] = useState(null)
  const [error, setError] = useState('')

  const [comparison, setComparison] = useState(null)
  const [comparisonLoading, setComparisonLoading] = useState(false)
  const [comparisonError, setComparisonError] = useState('')

  const [forecast, setForecast] = useState(null)
  const [forecastLoading, setForecastLoading] = useState(false)

  const [demands, setDemands] = useState(null)

  useEffect(() => {
    Promise.all([
      api.myListings(),
      api.myLots(),
      api.myTransactions(),
      api.myNotifications(),
    ])
      .then(([l, lo, t, n]) => { setListings(l); setLots(lo); setTransactions(t); setNotifications(n) })
      .catch(e => setError(e.message))
  }, [])

  const journey = (lots && transactions) ? selectFocusJourney(lots, transactions) : null
  const focusLot = journey?.lot || null

  // Best Selling Opportunity + Market Comparison: ONE call, shared by both
  // sections below -- no duplicated business logic, real /market/compare
  // data throughout (see BestSellingOpportunity.jsx).
  useEffect(() => {
    if (!focusLot) return
    setComparisonLoading(true)
    setComparisonError('')
    api.compareMarkets(focusLot.crop, focusLot.quantity_kg, focusLot.location)
      .then(setComparison)
      .catch(e => setComparisonError(e.message))
      .finally(() => setComparisonLoading(false))
  }, [focusLot?.crop, focusLot?.quantity_kg, focusLot?.location])

  // Price Trend: real history only (getForecast defaults to live-only data
  // and honestly reports `available:false` rather than fabricating a
  // trend -- see forecast.py's own honesty note).
  useEffect(() => {
    if (!focusLot || !comparison?.recommended_market) return
    setForecastLoading(true)
    api.getForecast(focusLot.crop, comparison.recommended_market, false)
      .then(setForecast)
      .catch(() => setForecast(null))
      .finally(() => setForecastLoading(false))
  }, [focusLot?.crop, comparison?.recommended_market])

  // Buyer demand relevant to what the farmer actually has to sell.
  useEffect(() => {
    if (!focusLot) { setDemands([]); return }
    api.getDemands({ crop: focusLot.crop }).then(setDemands).catch(() => setDemands([]))
  }, [focusLot?.crop])

  if (error) return <div className="text-red-600">{error}</div>
  if (!listings) return <LoadingSpinner label={t('dashboard.loadingDashboard')} />

  const active = listings.filter(l => l.status === 'active')
  const activeLots = (lots || []).filter(l => l.status === 'AVAILABLE')
  const pendingTxns = (transactions || []).filter(txn =>
    !['COMPLETED', 'completed', 'CANCELLED'].includes(txn.status)
  )
  const unread = (notifications || []).filter(n => !n.is_read).length
  const dataBadgeKey = comparison ? (DATA_BADGE_KEY[comparison.data_source_summary] || DATA_BADGE_KEY.unavailable) : null
  const dataBadgeClass = comparison ? (DATA_BADGE_CLASS[comparison.data_source_summary] || DATA_BADGE_CLASS.unavailable) : null

  return (
    <div className="space-y-8">
      {/* Header -- no card chrome, just clear typographic hierarchy */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <InitialsAvatar name={user?.name} />
          <div>
            <h1 className="font-display text-2xl md:text-3xl font-bold leading-tight">
              {t(greetingKey())}, {user?.name?.split(' ')[0]}
            </h1>
            <p className="text-ink/60 dark:text-paper/60 mt-1">{t('dashboard.subtitle')}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {focusLot?.location && (
            <span className="flex items-center gap-1 text-sm text-ink/60 dark:text-paper/60 bg-white dark:bg-white/5 border border-black/5 dark:border-white/10 rounded-lg px-3 py-1.5">
              <MapPin size={14} /> {focusLot.location}
            </span>
          )}
          {dataBadgeKey && (
            <span className={`text-xs font-semibold px-2.5 py-1.5 rounded-lg border ${dataBadgeClass}`}>{t(dataBadgeKey)}</span>
          )}
        </div>
      </div>

      {/* Farm Health & Soil -- compact summary; honest empty state until soil data is stored */}
      <FarmHealthCard user={user} />

      {/* Selling Journey -- premium dark hero treatment */}
      {journey && <SellingJourney journey={journey} dark />}

      {/* Best Selling Opportunity -- the primary decision, right after the journey */}
      <BestSellingOpportunity item={focusLot} comparison={comparison} loading={comparisonLoading} error={comparisonError} />

      {/* Key metrics -- real counts, not decorative */}
      <div>
        <SectionLabel icon={LineChartIcon}>{t('dashboard.keyMetrics')}</SectionLabel>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label={t('dashboard.activeListings')} value={active.length} icon={<Package size={16} />} tone="marigold" />
          <StatCard label={t('dashboard.activeLots')} value={activeLots.length} icon={<Package size={16} />} />
          <StatCard label={t('dashboard.buyerDemand')} value={demands === null ? '—' : demands.length} sub={demands?.length ? focusLot?.crop : undefined} icon={<ShoppingCart size={16} />} />
          <StatCard label={t('dashboard.activeTransactions')} value={pendingTxns.length} icon={<Briefcase size={16} />} />
        </div>
      </div>

      {/* Market Comparison + Price Trend + Weather -- the intelligence row */}
      <div>
        <SectionLabel icon={ScrollText}>{t('dashboard.marketIntelligence')}</SectionLabel>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            {comparison && comparison.options?.length > 1 && (
              <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5 md:p-6 overflow-x-auto">
                <h2 className="font-display font-semibold text-lg mb-1">{t('dashboard.marketComparison')}</h2>
                <p className="text-xs text-ink/40 dark:text-paper/40 mb-3">{t('dashboard.marketComparisonNote')}</p>
                <table className="w-full text-sm min-w-[480px]">
                  <thead>
                    <tr className="text-left text-xs text-ink/40 dark:text-paper/40 border-b border-black/5 dark:border-white/10">
                      <th className="pb-2 font-medium">{t('ui.market')}</th>
                      <th className="pb-2 font-medium">{t('ui.price')}</th>
                      <th className="pb-2 font-medium">{t('dashboard.distance')}</th>
                      <th className="pb-2 font-medium">{t('dashboard.transport')}</th>
                      <th className="pb-2 font-medium">{t('dashboard.netRealization')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.options.slice(0, 5).map(o => (
                      <tr key={o.market} className={`border-b border-black/5 dark:border-white/10 last:border-0 transition-colors hover:bg-wheat/20 dark:hover:bg-white/5 ${o.market === comparison.recommended_market ? 'bg-forest/5' : ''}`}>
                        <td className="py-2.5 font-medium">
                          {o.market}
                          {o.market === comparison.recommended_market && <span className="ml-2 text-[10px] font-semibold text-forest dark:text-forest-light bg-forest/10 px-1.5 py-0.5 rounded">{t('dashboard.recommended')}</span>}
                        </td>
                        <td className="py-2.5 font-mono-data">₹{o.modal_price_per_kg}/kg</td>
                        <td className="py-2.5">{o.distance_km} km</td>
                        <td className="py-2.5 font-mono-data">₹{o.transport_cost.toLocaleString('en-IN')}</td>
                        <td className="py-2.5 font-mono-data font-semibold">₹{o.net_profit.toLocaleString('en-IN')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Price Trend -- real history only, honest empty state otherwise */}
            <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5 md:p-6">
              <div className="flex items-center justify-between mb-1">
                <h2 className="font-display font-semibold text-lg">
                  {focusLot ? `${focusLot.crop} ${t('dashboard.priceTrend')}` : t('dashboard.priceTrend')}
                </h2>
                {forecast?.trend_direction && (
                  <span className="flex items-center gap-1 text-xs font-semibold text-ink/60 dark:text-paper/60">
                    <TrendIcon direction={forecast.trend_direction} /> {forecast.trend_direction}
                  </span>
                )}
              </div>
              {forecastLoading ? (
                <div className="h-40 flex items-center justify-center text-sm text-ink/40">{t('common.loading')}</div>
              ) : forecast?.available && forecast.history?.length > 1 ? (
                <>
                  <div className="h-48 mt-3">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={forecast.history}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#E3E7F7" />
                        <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={30} />
                        <YAxis tick={{ fontSize: 10 }} width={40} domain={['auto', 'auto']} />
                        <Tooltip formatter={(v) => [`₹${v}/kg`, 'Modal Price']} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                        <Line type="monotone" dataKey="modal_price" stroke="#27358A" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="text-[11px] text-ink/40 dark:text-paper/40 mt-2">
                    {t('dashboard.source')}: {forecast.is_demo ? t('dashboard.sourceDemo') : t('dashboard.sourceGovt')} · {comparison?.recommended_market}
                  </p>
                </>
              ) : (
                <p className="text-sm text-ink/50 dark:text-paper/50 py-8 text-center">
                  {t('dashboard.notEnoughHistory')}
                </p>
              )}
            </div>
          </div>

          <div className="space-y-6">
            <WeatherCard location={user?.location} />

            {/* Transport -- reuses the same comparison.options entry already
                fetched for Best Selling Opportunity above; no second API
                call, no second transport formula. */}
            {comparison?.options?.length > 0 && (() => {
              const best = comparison.options.find(o => o.market === comparison.recommended_market) || comparison.options[0]
              return (
                <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <Truck size={16} className="text-forest dark:text-forest-light" />
                    <h2 className="font-display font-semibold">{t('dashboard.estimatedTransportCost')}</h2>
                  </div>
                  <div className="grid grid-cols-2 gap-y-2 text-sm">
                    <div className="text-ink/50 dark:text-paper/50">{t('dashboard.from')}</div>
                    <div className="text-right font-medium">{focusLot?.location || '—'}</div>
                    <div className="text-ink/50 dark:text-paper/50">{t('dashboard.to')}</div>
                    <div className="text-right font-medium">{best.market}</div>
                    <div className="text-ink/50 dark:text-paper/50">{t('dashboard.distance')}</div>
                    <div className="text-right font-medium">{best.distance_km} km</div>
                    <div className="text-ink/50 dark:text-paper/50 font-semibold">{t('dashboard.estimatedTransport')}</div>
                    <div className="text-right font-mono-data font-bold text-forest dark:text-forest-light">₹{best.transport_cost.toLocaleString('en-IN')}</div>
                  </div>
                  <p className="text-[11px] text-ink/40 dark:text-paper/40 mt-2">{t('dashboard.transportDisclaimer')}</p>
                  <Link to="/transport" className="inline-flex items-center gap-1 text-sm font-semibold text-forest dark:text-forest-light hover:underline mt-3">
                    {t('dashboard.manageTransport')} →
                  </Link>
                </div>
              )
            })()}

            {/* Buyer demand relevant to this crop */}
            <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-display font-semibold">{t('dashboard.buyerDemand')}</h2>
                <Link to="/buyer-demands" className="text-sm text-forest dark:text-forest-light font-semibold hover:underline">{t('dashboard.all')} →</Link>
              </div>
              {!demands || demands.length === 0 ? (
                <p className="text-sm text-ink/50 dark:text-paper/50">
                  {focusLot ? t('dashboard.noBuyerDemand') : t('dashboard.addProduceForDemand')}
                </p>
              ) : (
                <div className="space-y-2">
                  {demands.slice(0, 3).map(d => (
                    <div key={d.id} className="text-xs border border-black/5 dark:border-white/10 rounded-lg px-3 py-2">
                      <div className="font-semibold">{d.required_quantity_kg.toLocaleString('en-IN')} kg {d.crop}</div>
                      <div className="text-ink/50 dark:text-paper/50 mt-0.5">
                        {d.target_price_per_kg ? `${t('dashboard.target')} ₹${d.target_price_per_kg}/kg` : t('dashboard.priceNegotiable')}
                        {d.delivery_location ? ` · ${d.delivery_location}` : ''}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* AI Advisor entry */}
            <Link to="/advisor" className="block bg-forest-dark text-paper rounded-2xl p-5 hover:opacity-90 transition-opacity">
              <div className="flex items-center gap-2 mb-1">
                <Bot size={18} className="text-marigold" />
                <h2 className="font-display font-semibold">{t('dashboard.aiAdvisor')}</h2>
              </div>
              <p className="text-sm text-paper/60 mb-3">{t('dashboard.aiAdvisorDesc')}</p>
              <span className="inline-flex items-center gap-1 text-sm font-semibold text-marigold">
                {t('dashboard.askAiAdvisor')} <ArrowRight size={14} />
              </span>
            </Link>
          </div>
        </div>
      </div>

      {/* Transactions + Alerts + Lots */}
      <div>
        <SectionLabel icon={Briefcase}>{t('dashboard.sellShip')}</SectionLabel>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display font-semibold text-lg">{t('dashboard.activeTransactions')}</h2>
              <Link to="/transactions" className="text-sm text-forest dark:text-forest-light font-semibold hover:underline">{t('dashboard.viewAll')} →</Link>
            </div>
            {pendingTxns.length === 0 ? (
              <p className="text-sm text-ink/50 dark:text-paper/50">{t('dashboard.noActiveTransactions')}</p>
            ) : (
              <div className="space-y-2">
                {pendingTxns.slice(0, 4).map(t2 => (
                  <Link key={t2.id} to={`/transactions/${t2.id}`} className="flex items-center justify-between border border-black/5 dark:border-white/10 rounded-xl px-4 py-3 hover:bg-wheat/30 dark:hover:bg-white/5 transition-colors">
                    <div>
                      <div className="font-medium text-sm">Transaction #{t2.id}</div>
                      <div className="text-xs text-ink/50 dark:text-paper/50">₹{t2.final_price_per_kg}/kg · {t2.quantity_kg.toLocaleString()} kg · ₹{t2.total_amount.toLocaleString('en-IN')}</div>
                    </div>
                    <Badge tone={TXN_STATUS_TONE[t2.status] || 'neutral'} className="text-xs">{t2.status.replace(/_/g, ' ')}</Badge>
                  </Link>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-4">
            <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-display font-semibold">{t('dashboard.recentAlerts')}</h2>
                <Link to="/notifications" className="text-sm text-forest dark:text-forest-light font-semibold hover:underline">{t('dashboard.all')} →</Link>
              </div>
              {(notifications || []).length === 0 ? (
                <p className="text-sm text-ink/50 dark:text-paper/50">{t('dashboard.noAlerts')}</p>
              ) : (
                <div className="space-y-2">
                  {notifications.slice(0, 3).map(n => (
                    <div key={n.id} className="text-sm border-l-2 border-marigold pl-3">
                      <div className="font-medium text-xs">{n.title}</div>
                      <div className="text-ink/50 dark:text-paper/50 text-xs">{n.message}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-display font-semibold">{t('dashboard.myLots')}</h2>
                <Link to="/lots" className="text-sm text-forest dark:text-forest-light font-semibold hover:underline">{t('dashboard.all')} →</Link>
              </div>
              {activeLots.length === 0 ? (
                <p className="text-sm text-ink/50 dark:text-paper/50">{t('dashboard.noActiveLots')} <Link to="/lots" className="text-forest dark:text-forest-light underline">{t('dashboard.createOne')} →</Link></p>
              ) : (
                <div className="space-y-2">
                  {activeLots.slice(0, 3).map(l => (
                    <div key={l.id} className="text-xs border border-black/5 dark:border-white/10 rounded-lg px-3 py-2">
                      <div className="font-semibold">{l.lot_number}</div>
                      <div className="text-ink/50 dark:text-paper/50">{l.crop} · {l.quantity_kg.toLocaleString()} kg · {t('dashboard.grade')} {l.grade}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Quick actions -- unchanged destinations, Lucide icons instead of emoji */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Link to="/lots" className="bg-white dark:bg-white/5 border border-black/5 dark:border-white/10 shadow-card rounded-2xl p-4 hover:-translate-y-0.5 transition-transform motion-reduce:hover:translate-y-0">
          <span className="w-8 h-8 rounded-lg bg-forest/8 dark:bg-white/10 flex items-center justify-center mb-2">
            <Package size={16} className="text-forest dark:text-forest-light" />
          </span>
          <div className="font-semibold text-sm">{t('dashboard.myLots')}</div>
          <div className="text-xs text-ink/50 dark:text-paper/50 mt-0.5">{t('dashboard.manageLots')}</div>
        </Link>
        <Link to="/farmpool" className="bg-white dark:bg-white/5 border border-black/5 dark:border-white/10 shadow-card rounded-2xl p-4 hover:-translate-y-0.5 transition-transform motion-reduce:hover:translate-y-0">
          <span className="w-8 h-8 rounded-lg bg-forest/8 dark:bg-white/10 flex items-center justify-center mb-2">
            <Truck size={16} className="text-forest dark:text-forest-light" />
          </span>
          <div className="font-semibold text-sm">{t('dashboard.farmPool')}</div>
          <div className="text-xs text-ink/50 dark:text-paper/50 mt-0.5">{t('dashboard.shareTransport')}</div>
        </Link>
        <Link to="/group-selling" className="bg-white dark:bg-white/5 border border-black/5 dark:border-white/10 shadow-card rounded-2xl p-4 hover:-translate-y-0.5 transition-transform motion-reduce:hover:translate-y-0">
          <span className="w-8 h-8 rounded-lg bg-forest/8 dark:bg-white/10 flex items-center justify-center mb-2">
            <Handshake size={16} className="text-forest dark:text-forest-light" />
          </span>
          <div className="font-semibold text-sm">{t('dashboard.groupSelling')}</div>
          <div className="text-xs text-ink/50 dark:text-paper/50 mt-0.5">{t('dashboard.sellWithFpo')}</div>
        </Link>
        <Link to="/profit-calculator" className="bg-white dark:bg-white/5 border border-black/5 dark:border-white/10 shadow-card rounded-2xl p-4 hover:-translate-y-0.5 transition-transform motion-reduce:hover:translate-y-0">
          <span className="w-8 h-8 rounded-lg bg-forest/8 dark:bg-white/10 flex items-center justify-center mb-2">
            <Calculator size={16} className="text-forest dark:text-forest-light" />
          </span>
          <div className="font-semibold text-sm">{t('dashboard.profitCalculator')}</div>
          <div className="text-xs text-ink/50 dark:text-paper/50 mt-0.5">{t('dashboard.compareOptions')}</div>
        </Link>
      </div>
    </div>
  )
}
