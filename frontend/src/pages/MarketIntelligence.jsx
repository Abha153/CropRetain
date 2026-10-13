import React, { useEffect, useState } from 'react'
import { BarChart3, MapPin, ShieldCheck, AlertTriangle } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import Badge from '../components/Badge'
import LoadingSpinner from '../components/LoadingSpinner'
import { resolveDefaultLocation, useGeolocatedMarket } from '../utils/location'
import { formatTimestamp } from '../utils/datetime'
import { useI18n } from '../i18n/I18nContext'

const CROP_KEY_MAP = {
  Tomato: 'auth.crop.tomato',
  Onion: 'auth.crop.onion',
  Potato: 'auth.crop.potato',
  Wheat: 'auth.crop.wheat',
  'Paddy (Rice)': 'auth.crop.paddyRice',
  Maize: 'auth.crop.maize',
  Soybean: 'auth.crop.soybean',
  'Chana (Gram)': 'auth.crop.chanaGram',
  Groundnut: 'auth.crop.groundnut',
  Mustard: 'auth.crop.mustard',
  Sugarcane: 'auth.crop.sugarcane',
}

function getLocalizedCropName(name, t) {
  const key = CROP_KEY_MAP[name]
  return key ? t(key) : name
}

export default function MarketIntelligence() {
  const { user, role } = useAuth()
  const { t } = useI18n()
  const { theme } = useTheme()
  const axisColor = theme === 'dark' ? '#EEF0FB' : '#1B2140'
  const gridColor = theme === 'dark' ? 'rgba(247,243,234,0.12)' : '#eee'
  const [crops, setCrops] = useState([])
  const [markets, setMarkets] = useState([])
  const [crop, setCrop] = useState('Tomato')
  const [quantity, setQuantity] = useState(1000)
  // Was hardcoded to 'Bilaspur' regardless of the signed-in user's profile
  // location -- meant updating Profile -> location never actually changed
  // what this page compared against. Precedence: saved profile location,
  // else the pan-India demo default (see utils/location.js).
  const [location, setLocation] = useState(() => resolveDefaultLocation(user))
  const geo = useGeolocatedMarket(api, (r) => setLocation(r.market))
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [sourceStatus, setSourceStatus] = useState(null)

  useEffect(() => {
    api.getCrops().then(setCrops)
    api.getMarkets().then(setMarkets)
    api.getDataSourceStatus().then(setSourceStatus).catch(() => {})
  }, [])

  useEffect(() => {
    if (role === 'farmer' && user?.location) setLocation(user.location)
  }, [user, role])

  async function runCompare(e) {
    e?.preventDefault()
    setLoading(true)
    setError('')
    try {
      const data = await api.compareMarkets(crop, quantity, location)
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { runCompare() }, []) // eslint-disable-line

  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <BarChart3 size={22} className="text-forest" />
        <h1 className="font-display text-3xl font-bold">{t('market.title')}</h1>
      </div>
      {sourceStatus && (
        <p className={`text-xs mb-1 ${sourceStatus.live_data_configured ? 'text-emerald-600 dark:text-emerald-400' : 'text-ink/40 dark:text-paper/40'}`}>
          {sourceStatus.live_data_configured
            ? t('market.liveDataEnabled')
            : t('market.demoDataNotice')}
        </p>
      )}
      <p className="text-ink/60 dark:text-paper/60 mb-6">{t('market.subtitle')}</p>

      <form onSubmit={runCompare} className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5 mb-6 grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('common.crop')}</label>
          <select value={crop} onChange={e => setCrop(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-white/5 dark:text-paper">
            {crops.map(c => <option key={c.name} value={c.name}>{c.emoji} {getLocalizedCropName(c.name, t)}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('common.quantityKg')}</label>
          <input type="number" min="1" value={quantity} onChange={e => setQuantity(Number(e.target.value))} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-white/5 dark:text-paper" />
        </div>
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1 flex items-center justify-between">
            <span>{t('market.yourLocation')}</span>
            <button
              type="button"
              disabled={geo.isDetecting}
              onClick={geo.detect}
              className="inline-flex items-center gap-1 text-[11px] font-semibold text-forest hover:underline disabled:opacity-50"
            >
              <MapPin size={12} /> {geo.isDetecting ? t('location.detecting') : t('location.useMyLocation')}
            </button>
          </label>
          {geo.isFailure && (
            <p className="text-[11px] text-ink/50 dark:text-paper/50 mt-1">
              {t(geo.messageKey)} {t('market.selectionKept')}
            </p>
          )}
          <select value={location} onChange={e => setLocation(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-white/5 dark:text-paper">
            {markets.map(m => <option key={m.name} value={m.name}>{m.name}</option>)}
          </select>
        </div>
        <button disabled={loading} className="bg-forest text-paper font-semibold rounded-lg py-2.5 hover:bg-forest-dark transition-colors disabled:opacity-60">
          {loading ? t('market.comparing') : t('market.compare')}
        </button>
      </form>

      {error && <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 text-sm rounded-lg px-3 py-2 mb-4">{error}</div>}
      {loading && <LoadingSpinner label={t('market.loading')} />}

      {result && !loading && (
        <>
          {result.insufficient_data ? (
            <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 text-amber-800 dark:text-amber-300 text-sm rounded-xl px-4 py-3 mb-6 inline-flex items-center gap-2">
              <AlertTriangle size={16} /> {t('market.insufficientData')}
            </div>
          ) : (
          <>
          <div className="bg-forest text-paper rounded-2xl p-5 mb-3 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-wide text-marigold-light font-semibold mb-1">{t('market.recommended')}</div>
              <div className="font-display text-2xl font-bold inline-flex items-center gap-2"><ShieldCheck size={18} className="text-marigold-light" /> {result.recommended_market}</div>
            </div>
            <div className="text-right">
              <div className="text-xs text-paper/70">{t('market.extraProfit')}</div>
              <div className="font-mono-data text-xl font-semibold text-marigold-light">
                +₹{result.profit_gain_vs_nearest_market.toLocaleString()}
              </div>
            </div>
          </div>

          {result.why && (
            <div className="bg-wheat/50 border border-black/5 dark:border-white/10 rounded-xl px-4 py-3 mb-6 text-sm text-ink/80 dark:text-paper/80">
              <span className="font-semibold">{t('market.why')}</span> {result.why}
            </div>
          )}

          <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5 mb-6">
            <h2 className="font-display font-semibold mb-4">{t('market.estimatedProfitByMarket')}</h2>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={result.options} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                <XAxis dataKey="market" tick={{ fontSize: 12, fill: axisColor }} />
                <YAxis tick={{ fontSize: 12, fill: axisColor }} />
                <Tooltip
                  formatter={(v) => `₹${v.toLocaleString()}`}
                  contentStyle={theme === 'dark' ? { background: '#27358A', border: '1px solid rgba(255,255,255,0.15)', color: '#EEF0FB' } : undefined}
                  labelStyle={theme === 'dark' ? { color: '#EEF0FB' } : undefined}
                />
                <Bar dataKey="net_profit" radius={[6, 6, 0, 0]}>
                  {result.options.map((entry, i) => (
                    <Cell key={i} fill={entry.market === result.recommended_market ? '#EBA91B' : '#27358A'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="bg-wheat dark:bg-white/5 text-ink/70 dark:text-paper/70">
                <tr>
                  <th className="text-left px-4 py-3 font-semibold">{t('ui.market')}</th>
                  <th className="text-center px-4 py-3 font-semibold">{t('dashboard.source')}</th>
                  <th className="text-right px-4 py-3 font-semibold">{t('market.pricePerKg')}</th>
                  <th className="text-right px-4 py-3 font-semibold">{t('dashboard.distance')}</th>
                  <th className="text-right px-4 py-3 font-semibold">{t('market.transportEstimate')}</th>
                  <th className="text-right px-4 py-3 font-semibold">{t('market.mandiHandlingEstimate')}</th>
                  <th className="text-right px-4 py-3 font-semibold">{t('market.netProfit')}</th>
                  <th className="text-right px-4 py-3 font-semibold">{t('market.asOf')}</th>
                </tr>
              </thead>
              <tbody>
                {result.options.map(o => {
                  const isMandi = o.data_source === 'live' && o.source_resource === 'market'
                  const isDistrict = o.data_source === 'live' && o.source_resource === 'district_variety'
                  return (
                  <tr key={o.market} className={`border-t border-black/5 dark:border-white/10 ${o.market === result.recommended_market ? 'bg-marigold/10' : ''}`}>
                    <td className="px-4 py-3 font-medium">
                      {o.market === result.recommended_market && '🟢 '}{o.market}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Badge tone={isMandi ? 'success' : isDistrict ? 'district' : 'neutral'}>
                        {isMandi ? `🟢 ${t('market.sourceGovernmentMandi')}` : isDistrict ? `🟣 ${t('market.sourceDistrictReference')}` : `🟡 ${t('market.sourceDemoData')}`}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-right font-mono-data">₹{o.modal_price_per_kg}</td>
                    <td className="px-4 py-3 text-right">{o.distance_km} km</td>
                    <td className="px-4 py-3 text-right font-mono-data">₹{o.transport_cost.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-mono-data">₹{(o.mandi_charges + o.handling_cost).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-mono-data font-semibold">₹{o.net_profit.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right text-xs text-ink/50 dark:text-paper/50">
                      {/* observed_at: when the SOURCE recorded the price. */}
                      <div>{o.as_of_date || '—'}</div>
                      {/* fetched_at: when CropRetain retrieved it. Only ever
                          present for live rows -- demo rows return null from
                          the backend, so nothing is rendered and no
                          timestamp is invented. */}
                      {formatTimestamp(o.fetched_at) && (
                        <div className="text-[10px] text-ink/40 dark:text-paper/40 mt-0.5">
                          {t('market.fetchedAt')}: {formatTimestamp(o.fetched_at)}
                        </div>
                      )}
                    </td>
                  </tr>
                )})}
              </tbody>
            </table>
            <div className="px-4 py-2 space-y-1">
              <p className="text-[11px] text-ink/40 dark:text-paper/40">{t('market.estimateDisclaimer')}</p>
              {result.options.some(o => o.source_resource === 'district_variety') && (
                <p className="text-[11px] text-ink/40 dark:text-paper/40">
                  🟣 {t('market.districtReferenceNote')}
                </p>
              )}
              {(result.data_source_summary === 'demo' || result.data_source_summary === 'mixed') && (
                <p className="text-[11px] text-ink/40 dark:text-paper/40">
                  {result.data_source_summary === 'mixed'
                    ? `🟡 ${t('market.mixedDataNote')}`
                    : `🟡 ${t('market.demoDataSummary')}`}
                </p>
              )}
            </div>
          </div>

          {result.unavailable_markets && result.unavailable_markets.length > 0 && (
            <div className="bg-sky-50 dark:bg-sky-950/40 border border-sky-200 dark:border-sky-900 text-sky-800 dark:text-sky-300 text-xs rounded-lg px-3 py-2 mb-3 mt-3 flex items-center justify-between gap-2 flex-wrap">
              ℹ️ {t('market.unavailableGovernmentRecord', { markets: result.unavailable_markets.map(m => m.market).join(', ') })}
            </div>
          )}
          </>
          )}
        </>
      )}
    </div>
  )
}
