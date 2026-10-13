import React, { useEffect, useState, useCallback } from 'react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../i18n/I18nContext'
import Badge from '../components/Badge'
import LoadingSpinner from '../components/LoadingSpinner'
import VerificationBadge from '../components/VerificationBadge'
import OfferNegotiation from '../components/OfferNegotiation'

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
  AVAILABLE: 'success', UNDER_OFFER: 'info', DRAFT: 'neutral',
  SOLD: 'forest', IN_TRANSIT: 'marigold', DELIVERED: 'forest', CANCELLED: 'neutral'
}

const LIFECYCLE = [
  'OFFER_CREATED', 'OFFER_ACCEPTED', 'ORDER_CONFIRMED', 'LOGISTICS_PENDING',
  'LOGISTICS_CONFIRMED', 'PICKED_UP', 'IN_TRANSIT', 'DELIVERED',
  'PAYMENT_PENDING', 'PAYMENT_INITIATED', 'PAYMENT_RECEIVED', 'COMPLETED'
]

function QualityBadge({ grade, score, demo }) {
  const { t } = useI18n()
  const tone = grade === 'A' ? 'success' : grade === 'B' ? 'info' : 'neutral'
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <Badge tone={tone}>{t('lots.grade')} {grade}</Badge>
      <span className="text-xs font-mono-data text-ink/60 dark:text-paper/60">{score}% {t('lots.aiScore')}</span>
      {demo && <Badge tone="warning">{t('lots.demoAi')}</Badge>}
    </div>
  )
}

function QualityReport({ report }) {
  const { t } = useI18n()
  if (!report) return null
  return (
    <div className="bg-wheat/50 dark:bg-white/5 rounded-xl p-3 mt-3 text-xs space-y-1.5">
      <div className="font-semibold text-sm mb-1">{t('lots.aiQualityReport')}</div>
      <p className="text-amber-700 dark:text-amber-400 italic">{report.analysis_method}</p>
      {report.moisture_pct != null && (
        <div className="flex items-center justify-between">
          <span className="text-ink/60 dark:text-paper/60">{t('buyerDemands.moisture')}</span>
          <span className="font-mono-data">{report.moisture_pct}%</span>
        </div>
      )}
      {report.foreign_matter_pct != null && (
        <div className="flex items-center justify-between">
          <span className="text-ink/60 dark:text-paper/60">{t('lots.foreignMatter')}</span>
          <span className="font-mono-data">{report.foreign_matter_pct}%</span>
        </div>
      )}
      {report.damaged_pct != null && (
        <div className="flex items-center justify-between">
          <span className="text-ink/60 dark:text-paper/60">{t('lots.damagedGrains')}</span>
          <span className="font-mono-data">{report.damaged_pct}%</span>
        </div>
      )}
      {report.detected_notes?.length > 0 && (
        <ul className="list-disc list-inside text-ink/50 dark:text-paper/50 space-y-0.5">
          {report.detected_notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
    </div>
  )
}

function LotCard({ lot, mine, onCancelled, onOfferAccepted }) {
  const { t } = useI18n()
  const [expanded, setExpanded] = useState(false)
  const [matches, setMatches] = useState(null)
  const [cancelling, setCancelling] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [offers, setOffers] = useState(null)
  const [showOffers, setShowOffers] = useState(false)
  const [offerBusy, setOfferBusy] = useState(null)
  const [offerError, setOfferError] = useState('')
  const [openThread, setOpenThread] = useState(null)

  async function loadMatches() {
    if (matches) { setExpanded(e => !e); return }
    try {
      const result = await api.matchBuyersForLot(lot.id)
      setMatches(result.matches || [])
      setExpanded(true)
    } catch {
      setMatches([])
      setExpanded(true)
    }
  }

  async function loadOffers() {
    if (showOffers) { setShowOffers(false); return }
    try {
      const result = await api.offersForLot(lot.id)
      setOffers(result)
      setShowOffers(true)
    } catch (e) {
      setOfferError(e.message)
      setOffers([])
      setShowOffers(true)
    }
  }

  async function respondOffer(offerId, action) {
    setOfferBusy(offerId); setOfferError('')
    try {
      if (action === 'accept') await api.acceptOffer(offerId)
      else await api.rejectOffer(offerId)
      const result = await api.offersForLot(lot.id)
      setOffers(result)
      if (action === 'accept') onOfferAccepted()
    } catch (e) {
      setOfferError(e.message)
    } finally {
      setOfferBusy(null)
    }
  }

  async function cancelLot() {
    setCancelling(true)
    try {
      await api.cancelLot(lot.id)
      onCancelled(lot.id)
    } catch (e) {
      alert(e.message)
    } finally {
      setCancelling(false); setConfirm(false)
    }
  }

  return (
    <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
      <div className="flex items-start justify-between mb-2 gap-2 flex-wrap">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-display font-bold text-lg">{getLocalizedCropName(lot.crop, t)}</span>
            <Badge tone={STATUS_TONE[lot.status] || 'neutral'}>{t(`lots.status.${lot.status}`)}</Badge>
          </div>
          <div className="text-xs text-ink/50 dark:text-paper/50 font-mono-data mt-0.5">
            {lot.lot_number} · {lot.location}
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono-data font-bold text-forest text-lg">₹{(lot.expected_price * 100).toFixed(0)}/q</div>
          {lot.minimum_price && <div className="text-xs text-ink/40">{t('lots.minPriceShort', { price: (lot.minimum_price * 100).toFixed(0) })}</div>}
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm mb-3">
        <div>
          <div className="text-xs text-ink/40 dark:text-paper/40">{t('lots.quantity')}</div>
          <div className="font-semibold">{lot.quantity_kg.toLocaleString()} kg</div>
        </div>
        <div>
          <div className="text-xs text-ink/40 dark:text-paper/40">{t('lots.aiGrade')}</div>
          <QualityBadge grade={lot.grade} score={lot.quality_score} demo={lot.quality_report?.demo_mode} />
        </div>
        {lot.harvest_date && (
          <div>
            <div className="text-xs text-ink/40 dark:text-paper/40">{t('lots.harvested')}</div>
            <div className="font-semibold">{lot.harvest_date}</div>
          </div>
        )}
        {lot.available_date && (
          <div>
            <div className="text-xs text-ink/40 dark:text-paper/40">{t('lots.available')}</div>
            <div className="font-semibold">{lot.available_date}</div>
          </div>
        )}
      </div>

      {lot.note && <p className="text-xs text-ink/50 dark:text-paper/50 mb-3">{lot.note}</p>}

      {expanded && lot.quality_report && <QualityReport report={lot.quality_report} />}

      <div className="flex items-center gap-3 mt-3 flex-wrap">
        {lot.quality_report && (
          <button onClick={() => setExpanded(e => !e)} className="text-xs text-forest font-semibold hover:underline">
            {expanded ? t('lots.hideQualityReport') : t('lots.viewQualityReport')}
          </button>
        )}
        {mine && lot.status === 'AVAILABLE' && (
          <button onClick={loadMatches} className="text-xs text-forest font-semibold hover:underline">
            {expanded && matches ? t('lots.hideBuyerDemands') : t('lots.findBuyerDemands')}
          </button>
        )}
        {mine && ['AVAILABLE', 'UNDER_OFFER'].includes(lot.status) && (
          <button onClick={loadOffers} className="text-xs text-forest font-semibold hover:underline">
            {showOffers ? t('lots.hideOffers') : t('lots.viewOffers')}
          </button>
        )}
        {mine && !['SOLD', 'IN_TRANSIT', 'DELIVERED', 'CANCELLED'].includes(lot.status) && (
          confirm ? (
            <span className="text-xs">
              {t('lots.cancelLotQuestion')}{' '}
              <button onClick={cancelLot} disabled={cancelling} className="text-red-600 font-semibold underline">{t('lots.yes')}</button>
              {' / '}
              <button onClick={() => setConfirm(false)} className="underline">{t('lots.no')}</button>
            </span>
          ) : (
            <button onClick={() => setConfirm(true)} className="text-xs text-red-500 hover:underline">
              {t('lots.cancelLot')}
            </button>
          )
        )}
      </div>

      {expanded && matches && mine && (
      <div className="mt-4 border-t border-black/5 dark:border-white/10 pt-4">
        <h4 className="text-sm font-semibold mb-2">{t('lots.topBuyerMatches')}</h4>
        {matches.length === 0 ? (
          <p className="text-xs text-ink/50 dark:text-paper/50">{t('lots.noBuyerMatches')}</p>
        ) : (
          <div className="space-y-2">
            {matches.map(m => (
              <div key={m.buyer_id} className="bg-wheat/40 dark:bg-white/5 rounded-lg px-3 py-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold">#{m.rank} {m.company_name}</span>
                  <span className="font-mono-data font-bold text-forest">{m.match_score}%</span>
                </div>
                <div className="text-ink/50 dark:text-paper/50 flex items-center gap-1 flex-wrap">
                  <VerificationBadge buyerId={m.buyer_id} compact />
                  {m.location} · ₹{m.estimated_price_per_kg}/kg est.
                  {m.matched_demand_id && ` · ${t('lots.activeDemand')}`}
                </div>
                {m.score_breakdown && (
                  <div className="grid grid-cols-4 gap-1 mt-1 text-ink/40 dark:text-paper/40">
                    {Object.entries(m.score_breakdown).slice(0, 4).map(([k, v]) => (
                      <div key={k} title={k.replace(/_/g, ' ')}>
                        <div className="text-[10px] truncate">{k.replace(/_/g, ' ')}</div>
                        <div className="font-mono-data">{v}%</div>
                      </div>
                    ))}
                  </div>
                )}
                {m.reasons?.length > 0 && (
                  <div className="text-ink/40 dark:text-paper/40 mt-0.5 truncate">{m.reasons[0]}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    )}

    {showOffers && mine && (
      <div className="mt-4 border-t border-black/5 dark:border-white/10 pt-4">
        <h4 className="text-sm font-semibold mb-2">{t('lots.offersOnThisLot')}</h4>
        {offerError && <p className="text-xs text-red-600 mb-2">{offerError}</p>}
        {!offers || offers.length === 0 ? (
          <p className="text-xs text-ink/50 dark:text-paper/50">{t('lots.noOffersYet')}</p>
        ) : (
          <div className="space-y-2">
            {offers.map(o => (
              <div key={o.id} className="bg-wheat/40 dark:bg-white/5 rounded-lg px-3 py-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold">₹{o.offered_price_per_kg}/kg × {o.quantity_kg.toLocaleString()} kg</span>
                  <Badge tone={o.status === 'accepted' ? 'success' : o.status === 'rejected' ? 'neutral' : 'info'}>{t(`lots.offerStatus.${o.status}`)}</Badge>
                </div>
                {o.message && <div className="text-ink/50 dark:text-paper/50 mt-0.5">{o.message}</div>}
                {o.status === 'pending' && o.awaiting_role === 'buyer' && (
                  <div className="mt-1"><Badge tone="info">{t('negotiation.awaiting.buyer')}</Badge></div>
                )}
                {o.status === 'pending' && o.awaiting_role !== 'buyer' && (
                  <div className="flex gap-2 mt-2">
                    <button disabled={offerBusy === o.id} onClick={() => respondOffer(o.id, 'accept')}
                      className="bg-forest text-paper font-semibold rounded px-2 py-1 disabled:opacity-60">
                      {offerBusy === o.id ? t('lots.working') : t('lots.accept')}
                    </button>
                    <button disabled={offerBusy === o.id} onClick={() => respondOffer(o.id, 'reject')}
                      className="border border-red-200 text-red-500 font-semibold rounded px-2 py-1 disabled:opacity-60">
                      {t('lots.reject')}
                    </button>
                  </div>
                )}
                <button onClick={() => setOpenThread(openThread === o.id ? null : o.id)} className="mt-2 text-forest font-semibold hover:underline">
                  {openThread === o.id ? t('negotiation.hide') : t('negotiation.open')}
                </button>
                {openThread === o.id && (
                  <div className="mt-2"><OfferNegotiation offerId={o.id} onChanged={async () => { try { setOffers(await api.offersForLot(lot.id)) } catch (e) {} onOfferAccepted && onOfferAccepted() }} /></div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    )}
    </div>
  )
}

function CreateLotForm({ onCreated, onClose }) {
  const { t } = useI18n()
  const [form, setForm] = useState({
    crop: 'Tomato',
    quantity_kg: 1000,
    grade: 'B',
    quality_score: 75,
    expected_price: 20,
    minimum_price: '',
    harvest_date: '',
    available_date: new Date().toISOString().slice(0, 10),
    note: '',
  })
  const [grading, setGrading] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)

  function set(field) { return e => setForm(f => ({ ...f, [field]: e.target.value })) }

  async function analyzeImage() {
    if (!file) return
    setAnalyzing(true)
    try {
      const res = await api.analyzeQualityImage(form.crop, file)
      setGrading(res)
      setForm(f => ({ ...f, grade: res.quality_grade, quality_score: res.visual_quality_score }))
    } catch (e) {
      alert(e.message)
    } finally {
      setAnalyzing(false)
    }
  }

  async function submit(e) {
    e.preventDefault()
    setError('')
    if (form.quantity_kg <= 0) { setError(t('lots.quantityError')); return }
    if (form.expected_price <= 0) { setError(t('lots.expectedPriceError')); return }
    setSubmitting(true)
    try {
      await api.createLot({
        crop: form.crop,
        quantity_kg: Number(form.quantity_kg),
        grade: form.grade,
        quality_score: Number(form.quality_score),
        quality_report: grading ? {
          quality_grade: grading.quality_grade,
          visual_quality_score: grading.visual_quality_score,
          detected_notes: grading.detected_notes,
          analysis_method: grading.analysis_method,
          demo_mode: grading.demo_mode ?? false,
        } : null,
        harvest_date: form.harvest_date || null,
        available_date: form.available_date,
        expected_price: Number(form.expected_price),
        minimum_price: form.minimum_price ? Number(form.minimum_price) : null,
        note: form.note || null,
      })
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
      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-3 py-2">{error}</div>}

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <label className={lbl}>{t('common.crop')}</label>
          <select value={form.crop} onChange={set('crop')} className={inp}>
            {CROPS.map(c => <option key={c}>{getLocalizedCropName(c, t)}</option>)}
          </select>
        </div>
        <div>
          <label className={lbl}>{t('buyerDemands.requiredQuantity')}</label>
          <input type="number" min="1" value={form.quantity_kg} onChange={set('quantity_kg')} className={inp} required />
        </div>
        <div>
          <label className={lbl}>{t('lots.expectedPriceQuintal')}</label>
          <input type="number" min="0.1" step="0.1" value={form.expected_price} onChange={set('expected_price')} className={inp} required />
        </div>
        <div>
          <label className={lbl}>{t('lots.minPriceQuintal')}</label>
          <input type="number" min="0" step="0.1" value={form.minimum_price} onChange={set('minimum_price')} className={inp} placeholder={t('buyerDemands.optional')} />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <label className={lbl}>{t('lots.aiGrade')}</label>
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
          <input type="date" value={form.available_date} onChange={set('available_date')} className={inp} required />
        </div>
      </div>

      {/* Inline quality photo analysis */}
      <div className="border border-dashed border-black/15 dark:border-white/15 rounded-xl p-4">
        <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-2">
          {t('lots.cropPhotoLabel')}
        </label>
        {previewUrl ? (
          <div className="flex gap-4 flex-wrap">
            <img src={previewUrl} alt={t('lots.cropPreviewAlt')} className="w-28 h-28 object-cover rounded-lg border" />
            <div className="flex-1 space-y-2">
              <button type="button" onClick={analyzeImage} disabled={analyzing}
                className="text-sm bg-forest text-paper rounded-lg px-4 py-2 font-medium disabled:opacity-60">
                {analyzing ? t('lots.analyzing') : `🔍 ${t('lots.analyzePhoto')}`}
              </button>
              {grading && (
                <div className="text-xs bg-wheat/50 rounded-lg p-2 space-y-1">
                  <div className="flex gap-2 flex-wrap">
                    <Badge tone={grading.quality_grade === 'A' ? 'success' : 'info'}>{t('lots.aiGrade')} {grading.quality_grade}</Badge>
                    <span className="text-ink/60">{grading.visual_quality_score}% {t('lots.score')}</span>
                    {grading.demo_mode && <Badge tone="warning">{t('lots.demoAi')}</Badge>}
                  </div>
                  <p className="text-ink/40 italic">{grading.analysis_method}</p>
                </div>
              )}
            </div>
          </div>
        ) : (
          <label className="flex flex-col items-center justify-center gap-1.5 border-2 border-dashed border-black/10 dark:border-white/15 rounded-lg py-5 cursor-pointer hover:bg-wheat/30">
            <span className="text-xl">📷</span>
            <span className="text-xs text-ink/50">{t('lots.uploadPhotoOf', { crop: getLocalizedCropName(form.crop, t) })}</span>
            <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
              onChange={e => {
                const f = e.target.files?.[0]
                if (f) { setFile(f); setPreviewUrl(URL.createObjectURL(f)) }
              }} />
          </label>
        )}
      </div>

      <div>
        <label className={lbl}>{t('lots.noteOptional')}</label>
        <input value={form.note} onChange={set('note')} className={inp} placeholder={t('lots.anyAdditionalNotes')} />
      </div>

      <div className="flex items-center gap-3">
        <button disabled={submitting} className="bg-marigold hover:bg-amber-400 text-ink font-semibold rounded-lg px-5 py-2.5 disabled:opacity-60">
          {submitting ? t('lots.creating') : t('lots.createLot')}
        </button>
        <button type="button" onClick={onClose} className="text-sm text-ink/50 hover:underline">{t('common.cancel')}</button>
      </div>
    </form>
  )
}

export default function Lots() {
  const { role } = useAuth()
  const { t } = useI18n()
  const [lots, setLots] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [scopeMine, setScopeMine] = useState(role === 'farmer')
  const [cropFilter, setCropFilter] = useState('')
  const [toast, setToast] = useState('')
  const [error, setError] = useState('')

  const loadLots = useCallback(async () => {
    setError('')
    try {
      const data = (role === 'farmer' && scopeMine)
        ? await api.myLots()
        : await api.getLots(cropFilter ? { crop: cropFilter } : {})
      setLots(data)
    } catch (e) {
      setError(e.message); setLots([])
    }
  }, [role, scopeMine, cropFilter])

  useEffect(() => { loadLots() }, [loadLots])

  function handleCancelled(id) {
    setLots(prev => prev.map(l => l.id === id ? { ...l, status: 'CANCELLED' } : l))
    setToast(t('lots.lotCancelledToast'))
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
        <div>
          <h1 className="font-display text-3xl font-bold">📦 {t('lots.title')}</h1>
          <p className="text-ink/60 dark:text-paper/60 text-sm mt-0.5">
            {role === 'farmer' ? t('lots.farmerSubtitle') : t('lots.buyerSubtitle')}
          </p>
        </div>
        {role === 'farmer' && (
          <button onClick={() => setShowForm(s => !s)} className="bg-marigold hover:bg-amber-400 text-ink font-semibold rounded-lg px-4 py-2 text-sm">
            {showForm ? t('common.close') : `+ ${t('lots.createLot')}`}
          </button>
        )}
      </div>

      {toast && (
        <div className="mt-3 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 text-emerald-700 dark:text-emerald-300 text-sm rounded-lg px-3 py-2">
          {toast} <button onClick={() => setToast('')} className="ml-2 underline text-xs">{t('common.dismiss')}</button>
        </div>
      )}
      {error && <div className="mt-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-3 py-2">{error}</div>}

      {showForm && role === 'farmer' && (
        <div className="mt-4">
          <CreateLotForm
            onCreated={() => { setShowForm(false); setToast(t('lots.createdSuccessfully')); setScopeMine(true); loadLots() }}
            onClose={() => setShowForm(false)}
          />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 mt-4 mb-4">
        {role === 'farmer' && (
          <div className="flex bg-white dark:bg-white/5 border border-black/10 dark:border-white/15 rounded-lg p-1 text-sm">
            <button onClick={() => setScopeMine(true)} className={`px-3 py-1.5 rounded-md font-medium ${scopeMine ? 'bg-forest text-paper' : 'text-ink/60 dark:text-paper/60'}`}>{t('lots.myLots')}</button>
            <button onClick={() => setScopeMine(false)} className={`px-3 py-1.5 rounded-md font-medium ${!scopeMine ? 'bg-forest text-paper' : 'text-ink/60 dark:text-paper/60'}`}>{t('lots.allLots')}</button>
          </div>
        )}
        <select value={cropFilter} onChange={e => setCropFilter(e.target.value)} className="border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper">
          <option value="">{t('storage.allCrops')}</option>
          {CROPS.map(c => <option key={c}>{getLocalizedCropName(c, t)}</option>)}
        </select>
      </div>

      {lots === null ? (
        <LoadingSpinner label={t('lots.loadingLots')} />
      ) : lots.length === 0 ? (
        <div className="text-sm text-ink/50 dark:text-paper/50">
          {role === 'farmer' && scopeMine ? t('lots.noLotsYetFarmer') : t('lots.noLotsYetBuyer')}
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {lots.map(l => (
            <LotCard key={l.id} lot={l} mine={role === 'farmer' && scopeMine} onCancelled={handleCancelled} onOfferAccepted={() => { setToast(t('lots.offerAcceptedToast')); loadLots() }} />
          ))}
        </div>
      )}
    </div>
  )
}
