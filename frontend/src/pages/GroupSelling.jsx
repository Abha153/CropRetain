import React, { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'
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

export default function GroupSelling() {
  const { user } = useAuth()
  const { t } = useI18n()
  const [crops, setCrops] = useState([])
  const [pools, setPools] = useState(null)
  const [crop, setCrop] = useState('Chana (Gram)')
  const [quantity, setQuantity] = useState(500)
  const [fpoName, setFpoName] = useState('')
  const [joining, setJoining] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => { api.getCrops().then(setCrops) }, [])

  async function loadPools() {
    setPools(null)
    try {
      const data = await api.getGroupPools()
      setPools(data)
    } catch (e) {
      setPools([])
    }
  }
  useEffect(() => { loadPools() }, [])

  async function join(e) {
    e.preventDefault()
    setJoining(true)
    setMessage('')
    try {
      const res = await api.joinGroupPool({ crop, quantity_kg: quantity, fpo_name: fpoName || undefined })
      setMessage(t('groupSelling.joined', {
        fpoName: res.fpo_name,
        memberCount: res.member_count,
        totalQuantity: res.total_quantity_kg.toLocaleString(),
      }))
      loadPools()
    } catch (e) {
      setMessage(e.message)
    } finally {
      setJoining(false)
    }
  }

  return (
    <div>
      <h1 className="font-display text-3xl font-bold mb-1">🤝 {t('groupSelling.title')}</h1>
      <p className="text-ink/60 dark:text-paper/60 mb-6">{t('groupSelling.subtitle')}</p>

      <form onSubmit={join} className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5 mb-6 grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('common.crop')}</label>
          <select value={crop} onChange={e => setCrop(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-white/5 dark:text-paper">
            {crops.map(c => <option key={c.name} value={c.name}>{c.emoji} {getLocalizedCropName(c.name, t)}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('groupSelling.yourQuantityKg')}</label>
          <input type="number" min="1" value={quantity} onChange={e => setQuantity(Number(e.target.value))} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-white/5 dark:text-paper" />
        </div>
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('groupSelling.fpoGroupName')}</label>
          <input value={fpoName} onChange={e => setFpoName(e.target.value)} placeholder={user?.fpo_group || t('groupSelling.fpoNamePlaceholder')} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-white/5 dark:text-paper" />
        </div>
        <button disabled={joining} className="bg-forest text-paper font-semibold rounded-lg py-2.5 hover:bg-forest-dark transition-colors disabled:opacity-60">
          {joining ? t('groupSelling.joining') : t('groupSelling.joinOrCreate')}
        </button>
      </form>

      {message && <div className="bg-marigold/10 border border-marigold/30 text-marigold-dark text-sm rounded-lg px-4 py-2.5 mb-6">{message}</div>}

      {pools === null ? <LoadingSpinner label={t('groupSelling.loadingPools')} /> : pools.length === 0 ? (
        <p className="text-sm text-ink/50 dark:text-paper/50">{t('groupSelling.noOpenPools')}</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {pools.map(p => (
            <div key={p.id} className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-display font-semibold text-lg">{getLocalizedCropName(p.crop, t)}</h3>
                <span className="text-xs text-ink/50 dark:text-paper/50">{p.fpo_name}</span>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm mb-3">
                <div><div className="text-xs text-ink/40 dark:text-paper/40">{t('groupSelling.members')}</div><div className="font-semibold">{p.member_count}</div></div>
                <div><div className="text-xs text-ink/40 dark:text-paper/40">{t('groupSelling.totalQuantity')}</div><div className="font-mono-data font-semibold">{p.total_quantity_kg.toLocaleString()} kg</div></div>
              </div>
              <div className="bg-forest/5 rounded-lg px-3 py-2 text-sm">
                <span className="font-semibold text-forest">+{p.estimated_price_improvement_pct}%</span> {t('groupSelling.priceImprovementNote', { buyers: p.potential_bulk_buyers })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
