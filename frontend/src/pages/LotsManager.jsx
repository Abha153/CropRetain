import React, { useEffect, useState, useCallback } from 'react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Badge from '../components/Badge'
import LoadingSpinner from '../components/LoadingSpinner'
import { useI18n } from '../i18n/I18nContext'

// NOTE: these are real crop names exchanged with the backend (`crop` field
// on the lot payload), not UI copy -- intentionally left untranslated per
// the CropRetain i18n policy on data identifiers/proper nouns. The visible
// dropdown/label chrome around them is translated below.
const CROPS = [
  'Tomato', 'Onion', 'Potato', 'Wheat', 'Paddy (Rice)', 'Maize',
  'Soybean', 'Chana (Gram)', 'Groundnut', 'Mustard'
]

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

const STATUS_TONE = {
  AVAILABLE: 'success', DRAFT: 'neutral', UNDER_OFFER: 'info',
  SOLD: 'forest', IN_TRANSIT: 'info', DELIVERED: 'success',
  CANCELLED: 'neutral'
}

function LotCard({ lot, role, onCancel }) {
  const { t } = useI18n()
  return (
    <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
      <div className="flex items-start justify-between mb-3 gap-2 flex-wrap">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-display font-bold text-lg">{getLocalizedCropName(lot.crop, t)}</span>
            <Badge tone={STATUS_TONE[lot.status] || 'neutral'}>{t(`lots.status.${lot.status}`)}</Badge>
          </div>
          <div className="text-xs text-ink/50 dark:text-paper/50 mt-0.5">
            {lot.lot_number} · {lot.location}
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono-data font-bold text-forest text-lg">
            ₹{(lot.expected_price * 100).toFixed(0)}/q
          </div>
          {lot.minimum_price && (
            <div className="text-xs text-ink/40 dark:text-paper/40">
              {t('lots.minPriceShort', { price: (lot.minimum_price * 100).toFixed(0) })}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm mb-3">
        <div>
          <div className="text-xs text-ink/40 dark:text-paper/40">{t('grievance.category.QUANTITY')}</div>
          <div className="font-semibold">{lot.quantity_kg.toLocaleString()} kg</div>
        </div>
        <div>
          <div className="text-xs text-ink/40 dark:text-paper/40">{t('lots.grade')}</div>
          <div className="font-semibold">{t('buyerDashboard.gradeLabel', { grade: lot.grade })}</div>
        </div>
        <div>
          <div className="text-xs text-ink/40 dark:text-paper/40">{t('lots.aiScore')}</div>
          <div className="font-semibold">{lot.quality_score}%</div>
        </div>
        {lot.available_date && (
          <div>
            <div className="text-xs text-ink/40 dark:text-paper/40">{t('lots.available')}</div>
            <div className="font-semibold">{lot.available_date}</div>
          </div>
        )}
      </div>

      {lot.quality_report?.analysis_method && (
        <div className="text-[11px] text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 rounded px-2 py-1 mb-3">
          ⚠ {lot.quality_report.analysis_method}
        </div>
      )}

      {lot.note && (
        <div className="text-xs text-ink/60 dark:text-paper/60 mb-3">{lot.note}</div>
      )}

      {role === 'farmer' && !['SOLD', 'IN_TRANSIT', 'DELIVERED', 'CANCELLED'].includes(lot.status) && (
        <button
          onClick={() => onCancel(lot.id, lot.lot_number)}
          className="text-xs text-red-500 hover:underline"
        >
          {t('lots.cancelLot')}
        </button>
      )}
    </div>
  )
}

function CreateLotForm({ onCreated, onClose }) {
  const { user } = useAuth()
  const { t } = useI18n()
  const [form, setForm] = useState({
    crop: 'Tomato',
    quantity_kg: 1000,
    grade: 'B',
    quality_score: 75,
    expected_price: '',
    minimum_price: '',
    available_date: '',
    harvest_date: '',
    location: user?.location || '',
    note: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  function set(field) { return e => setForm(f => ({ ...f, [field]: e.target.value })) }

  async function submit(e) {
    e.preventDefault()
    setError('')
    if (!form.expected_price || Number(form.expected_price) <= 0) {
      setError(t('lots.expectedPriceError'))
      return
    }
    setSubmitting(true)
    try {
      const payload = {
        crop: form.crop,
        quantity_kg: Number(form.quantity_kg),
        grade: form.grade,
        quality_score: Number(form.quality_score),
        expected_price: Number(form.expected_price) / 100, // convert ₹/q to ₹/kg
        minimum_price: form.minimum_price ? Number(form.minimum_price) / 100 : null,
        available_date: form.available_date || null,
        harvest_date: form.harvest_date || null,
        location: form.location || null,
        note: form.note || null,
      }
      await api.createLot(payload)
      onCreated()
    } catch (e) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const inp = 'w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper'
  const lbl = 'text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1'

  return (
    <form onSubmit={submit} className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5 mb-6 space-y-4">
      <h2 className="font-display font-semibold text-lg">{t('lots.createNewLot')}</h2>
      {error && (
        <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 text-red-700 dark:text-red-300 text-sm rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <label className={lbl}>{t('common.crop')}</label>
          <select value={form.crop} onChange={set('crop')} className={inp}>
            {CROPS.map(c => <option key={c}>{getLocalizedCropName(c, t)}</option>)}
          </select>
        </div>
        <div>
          <label className={lbl}>{t('common.quantityKg')}</label>
          <input type="number" min="1" value={form.quantity_kg} onChange={set('quantity_kg')} className={inp} required />
        </div>
        <div>
          <label className={lbl}>{t('lots.expectedPriceQuintal')}</label>
          <input type="number" min="1" value={form.expected_price} onChange={set('expected_price')} className={inp} placeholder={t('lots.examplePrice')} required />
        </div>
        <div>
          <label className={lbl}>{t('lots.minPriceQuintal')}</label>
          <input type="number" min="0" value={form.minimum_price} onChange={set('minimum_price')} className={inp} placeholder={t('ui.optional')} />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <label className={lbl}>{t('lots.grade')}</label>
          <select value={form.grade} onChange={set('grade')} className={inp}>
            <option>A</option><option>B</option><option>C</option>
          </select>
        </div>
        <div>
          <label className={lbl}>{t('lots.aiQualityScorePct')}</label>
          <input type="number" min="0" max="100" value={form.quality_score} onChange={set('quality_score')} className={inp} />
        </div>
        <div>
          <label className={lbl}>{t('lots.harvestDate')}</label>
          <input type="date" value={form.harvest_date} onChange={set('harvest_date')} className={inp} />
        </div>
        <div>
          <label className={lbl}>{t('lots.availableDate')}</label>
          <input type="date" value={form.available_date} onChange={set('available_date')} className={inp} />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className={lbl}>{t('common.location')}</label>
          <input value={form.location} onChange={set('location')} className={inp} placeholder={t('lots.exampleLocation')} />
        </div>
        <div>
          <label className={lbl}>{t('lots.noteOptional')}</label>
          <input value={form.note} onChange={set('note')} className={inp} placeholder={t('lots.anyAdditionalNotes')} />
        </div>
      </div>

      <div className="text-xs text-amber-700 dark:text-amber-400">
        ⚠ {t('lots.aiEstimatedNotice')}
      </div>

      <div className="flex items-center gap-3">
        <button
          disabled={submitting}
          className="bg-marigold hover:bg-amber-400 text-ink font-semibold rounded-lg px-5 py-2.5 disabled:opacity-60"
        >
          {submitting ? t('lots.creating') : t('lots.createLot')}
        </button>
        <button type="button" onClick={onClose} className="text-sm text-ink/50 hover:underline">
          {t('cancel')}
        </button>
      </div>
    </form>
  )
}

export default function LotsManager() {
  const { role } = useAuth()
  const { t } = useI18n()
  const [lots, setLots] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [cropFilter, setCropFilter] = useState('')
  const [toast, setToast] = useState('')
  const [error, setError] = useState('')

  const loadLots = useCallback(async () => {
    setError('')
    try {
      const params = {}
      if (cropFilter) params.crop = cropFilter
      const data = role === 'farmer'
        ? await api.myLots()
        : await api.getLots({ ...params, status: 'AVAILABLE' })
      setLots(data)
    } catch (e) {
      setError(e.message)
      setLots([])
    }
  }, [role, cropFilter])

  useEffect(() => { loadLots() }, [loadLots])

  async function handleCancel(id, lotNumber) {
    if (!window.confirm(t('lots.cancelConfirm', { lotNumber }))) return
    try {
      await api.cancelLot(id)
      setToast(t('lots.cancelledToast', { lotNumber }))
      loadLots()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
        <div>
          <h1 className="font-display text-3xl font-bold">📦 {t('lots.title')}</h1>
          <p className="text-ink/60 dark:text-paper/60 text-sm mt-0.5">
            {role === 'farmer'
              ? t('lots.farmerSubtitle')
              : t('lots.buyerSubtitle')}
          </p>
        </div>
        {role === 'farmer' && (
          <button
            onClick={() => setShowForm(s => !s)}
            className="bg-marigold hover:bg-amber-400 text-ink font-semibold rounded-lg px-4 py-2 text-sm"
          >
            {showForm ? t('ui.close') : `+ ${t('lots.createLot')}`}
          </button>
        )}
      </div>

      {toast && (
        <div className="mt-3 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 text-emerald-700 dark:text-emerald-300 text-sm rounded-lg px-3 py-2">
          {toast} <button onClick={() => setToast('')} className="ml-2 underline text-xs">{t('ui.dismiss')}</button>
        </div>
      )}
      {error && (
        <div className="mt-3 bg-red-50 dark:bg-red-950/40 border border-red-200 text-red-700 dark:text-red-300 text-sm rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {showForm && role === 'farmer' && (
        <div className="mt-4">
          <CreateLotForm
            onCreated={() => { setShowForm(false); setToast(t('lots.createdSuccessfully')); loadLots() }}
            onClose={() => setShowForm(false)}
          />
        </div>
      )}

      {role === 'buyer' && (
        <div className="flex items-center gap-3 mt-4 mb-4 flex-wrap">
          <select
            value={cropFilter}
            onChange={e => setCropFilter(e.target.value)}
            className="border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper"
          >
            <option value="">{t('storage.allCrops')}</option>
            {CROPS.map(c => <option key={c}>{c}</option>)}
          </select>
        </div>
      )}

      {lots === null ? (
        <LoadingSpinner label={t('lots.loadingLots')} />
      ) : lots.length === 0 ? (
        <div className="mt-6 text-sm text-ink/50 dark:text-paper/50">
          {role === 'farmer'
            ? t('lots.noLotsYetFarmer')
            : t('lots.noLotsYetBuyer')}
        </div>
      ) : (
        <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-4">
          {lots.map(lot => (
            <LotCard
              key={lot.id}
              lot={lot}
              role={role}
              onCancel={handleCancel}
            />
          ))}
        </div>
      )}
    </div>
  )
}
