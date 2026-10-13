import React, { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../i18n/I18nContext'
import { resolveDefaultLocation } from '../utils/location'
import LoadingSpinner from '../components/LoadingSpinner'

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

export default function FarmPool() {
  const { user } = useAuth()
  const { t } = useI18n()
  const [crops, setCrops] = useState([])
  const [markets, setMarkets] = useState([])
  const [crop, setCrop] = useState('Tomato')
  const [location, setLocation] = useState(() => resolveDefaultLocation(user))
  const [quantity, setQuantity] = useState(500)
  const [destination, setDestination] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  // Real TransportRequest this pool calc can be linked to. Only requests
  // that have actually reached a transporter agreement
  // (transporter_agreed_price set) are offered here, since linking a
  // still-negotiating request would have no effect on cost_basis anyway.
  const [agreedRequests, setAgreedRequests] = useState([])
  const [linkedRequestId, setLinkedRequestId] = useState('')

  useEffect(() => {
    api.getCrops().then(setCrops)
    api.getMarkets().then(setMarkets)
    api.myTransportRequests().then(reqs => {
      setAgreedRequests((reqs || []).filter(r => r.transporter_agreed_price != null))
    }).catch(() => {})
  }, [])
  useEffect(() => { if (user?.location) setLocation(user.location) }, [user])

  async function run(e) {
    e?.preventDefault()
    setLoading(true)
    setError('')
    try {
      const data = await api.farmPool({
        crop, location, quantity_kg: quantity, destination_market: destination || undefined,
        transport_request_id: linkedRequestId ? Number(linkedRequestId) : undefined,
      })
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h1 className="font-display text-3xl font-bold mb-1">🚚 {t('farmpool.title')}</h1>
      <p className="text-ink/60 dark:text-paper/60 mb-6">{t('farmpool.subtitle')}</p>

      <form onSubmit={run} className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5 mb-6 grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('farmpool.cropLabel')}</label>
          <select value={crop} onChange={e => setCrop(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-white/5 dark:text-paper">
            {crops.map(c => <option key={c.name} value={c.name}>{c.emoji} {getLocalizedCropName(c.name, t)}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('farmpool.locationLabel')}</label>
          <input value={location} onChange={e => setLocation(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-white/5 dark:text-paper" />
        </div>
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('farmpool.quantityLabel')}</label>
          <input type="number" min="1" value={quantity} onChange={e => setQuantity(Number(e.target.value))} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-white/5 dark:text-paper" />
        </div>
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('farmpool.destinationLabel')}</label>
          <select value={destination} onChange={e => setDestination(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-white/5 dark:text-paper">
            <option value="">{t('farmpool.nearestMarket')}</option>
            {markets.map(m => <option key={m.name} value={m.name}>{m.name}</option>)}
          </select>
        </div>
        <button disabled={loading} className="bg-forest text-paper font-semibold rounded-lg py-2.5 hover:bg-forest-dark transition-colors disabled:opacity-60">
          {loading ? t('farmpool.finding') : t('farmpool.findButton')}
        </button>
      </form>

      {agreedRequests.length > 0 && (
        <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5 mb-6">
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">
            {t('farmpool.linkAgreedRequestLabel')}
          </label>
          <select
            value={linkedRequestId}
            onChange={e => setLinkedRequestId(e.target.value)}
            className="w-full md:w-1/2 border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-white/5 dark:text-paper"
          >
            <option value="">{t('farmpool.noLinkedRequest')}</option>
            {agreedRequests.map(r => (
              <option key={r.id} value={r.id}>
                #{r.id} — {r.pickup_location} → {r.destination} — ₹{r.transporter_agreed_price}
              </option>
            ))}
          </select>
          <p className="text-xs text-ink/50 dark:text-paper/50 mt-2">{t('farmpool.linkAgreedRequestHint')}</p>
        </div>
      )}

      {error && <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 text-sm rounded-lg px-3 py-2 mb-4">{error}</div>}
      {loading && <LoadingSpinner label={t('farmpool.looking')} />}

      {result && !loading && (
        <div className="space-y-6">
          <div className={`text-xs font-semibold rounded-lg px-3 py-2 ${
            result.cost_basis === 'AGREED'
              ? 'bg-forest/10 text-forest-dark border border-forest/30'
              : 'bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 text-amber-700 dark:text-amber-300'
          }`}>
            {result.cost_basis === 'AGREED'
              ? t('farmpool.basisAgreed', { price: result.transporter_agreed_price })
              : t('farmpool.basisEstimated')}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
              <div className="text-xs text-ink/50 dark:text-paper/50 mb-1">{t('farmpool.individualCost')}</div>
              <div className="font-mono-data text-2xl font-semibold">₹{result.your_individual_transport_cost.toLocaleString()}</div>
            </div>
            <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
              <div className="text-xs text-ink/50 dark:text-paper/50 mb-1">
                {result.cost_basis === 'AGREED' ? t('farmpool.sharedCostAgreed') : t('farmpool.sharedCost')}
              </div>
              <div className="font-mono-data text-2xl font-semibold">₹{result.your_shared_transport_cost.toLocaleString()}</div>
              {result.cost_basis === 'AGREED' && (
                <div className="text-[11px] text-ink/40 dark:text-paper/40 mt-1">
                  {t('farmpool.estimatedShareWas', { amount: result.your_estimated_shared_share.toLocaleString() })}
                </div>
              )}
            </div>
            <div className="bg-forest text-paper rounded-2xl p-5">
              <div className="text-xs text-marigold-light mb-1">{t('farmpool.youSave')}</div>
              <div className="font-mono-data text-2xl font-semibold">₹{result.estimated_savings.toLocaleString()} ({result.savings_pct}%)</div>
            </div>
          </div>

          <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
            <h2 className="font-display font-semibold text-lg mb-1">{t('farmpool.poolTo', { market: result.destination_market, distance: result.distance_km })}</h2>
            <p className="text-sm text-ink/50 dark:text-paper/50 mb-4">{t('farmpool.totalPooled', { quantity: result.total_pool_quantity_kg.toLocaleString() })}</p>
            {result.pool_partners_are_simulated && (
              <div className="mb-4 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg text-amber-700 dark:text-amber-300 text-xs">
                {t('farmpool.simulatedPartnersDisclaimer')}
              </div>
            )}
            <div className="space-y-2">
              <div className="flex items-center justify-between bg-marigold/10 rounded-lg px-3 py-2 text-sm font-semibold">
                <span>{t('farmpool.you')}</span><span className="font-mono-data">{result.your_quantity_kg.toLocaleString()} kg</span>
              </div>
              {result.pool_partners.map((p, i) => (
                <div key={i} className="flex items-center justify-between bg-wheat/50 rounded-lg px-3 py-2 text-sm">
                  <span>{t('farmpool.partnerDistance', { name: p.farmer_name, distance: p.distance_from_you_km })}</span>
                  <span className="font-mono-data">{p.quantity_kg.toLocaleString()} kg</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
