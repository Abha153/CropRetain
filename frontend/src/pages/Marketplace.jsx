import React, { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Badge from '../components/Badge'
import OfferNegotiation from '../components/OfferNegotiation'
import LoadingSpinner from '../components/LoadingSpinner'
import { useI18n } from '../i18n/I18nContext'

const MAX_IMAGE_MB = 8
const ALLOWED_TYPES = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']

function QualityImageUpload({ crop, grading, setGrading }) {
  const { t } = useI18n()
  const [file, setFile] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const inputRef = React.useRef(null)

  function handleFile(selected) {
    setUploadError('')
    setGrading(null)
    if (!selected) return
    if (!ALLOWED_TYPES.includes(selected.type)) {
      setUploadError(t('marketplace.uploadTypeError'))
      return
    }
    if (selected.size > MAX_IMAGE_MB * 1024 * 1024) {
      setUploadError(t('marketplace.uploadSizeError', { size: (selected.size / 1_048_576).toFixed(1), max: MAX_IMAGE_MB }))
      return
    }
    setFile(selected)
    setPreviewUrl(URL.createObjectURL(selected))
  }

  function removeImage() {
    setFile(null)
    setPreviewUrl(null)
    setGrading(null)
    setUploadError('')
    if (inputRef.current) inputRef.current.value = ''
  }

  async function analyze() {
    if (!file) return
    setAnalyzing(true)
    setUploadError('')
    try {
      const res = await api.analyzeQualityImage(crop, file)
      setGrading(res)
    } catch (e) {
      setUploadError(e.message)
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <div className="border border-dashed border-black/15 rounded-xl p-4">
      <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-2">{t('marketplace.cropPhotoLabel')}</label>
      {uploadError && <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 text-xs rounded-lg px-3 py-2 mb-3">{uploadError}</div>}

      {!previewUrl ? (
        <label className="flex flex-col items-center justify-center gap-1.5 border-2 border-dashed border-black/10 dark:border-white/15 rounded-lg py-6 cursor-pointer hover:bg-wheat/40 transition-colors">
          <span className="text-2xl">📷</span>
          <span className="text-sm text-ink/60 dark:text-paper/60">{t('marketplace.tapToUpload', { crop })}</span>
          <span className="text-xs text-ink/35 dark:text-paper/35">{t('marketplace.uploadHint', { max: MAX_IMAGE_MB })}</span>
          <input
            ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp"
            className="hidden" onChange={e => handleFile(e.target.files?.[0])}
          />
        </label>
      ) : (
        <div className="flex flex-col sm:flex-row gap-4 items-start">
          <img src={previewUrl} alt={t('marketplace.previewAlt', { crop })} className="w-full sm:w-32 h-32 object-cover rounded-lg border border-black/10 dark:border-white/15" />
          <div className="flex-1 space-y-2">
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={analyze} disabled={analyzing} className="text-sm bg-forest text-paper rounded-lg px-4 py-2 font-medium disabled:opacity-60">
                {analyzing ? t('marketplace.analyzingPhoto') : `🔍 ${t('marketplace.analyzeThisPhoto')}`}
              </button>
              <label className="text-sm bg-white dark:bg-white/5 border border-black/10 dark:border-white/15 rounded-lg px-4 py-2 font-medium cursor-pointer hover:bg-wheat dark:bg-white/5">
                {t('marketplace.replace')}
                <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={e => handleFile(e.target.files?.[0])} />
              </label>
              <button type="button" onClick={removeImage} className="text-sm text-red-500 dark:text-red-400 hover:underline px-2">{t('marketplace.remove')}</button>
            </div>
            {grading && (
              <div className="text-sm bg-wheat/50 rounded-lg p-3 space-y-1">
                <div className="flex items-center gap-2">
                  <Badge tone="forest">{t('buyerDashboard.gradeLabel', { grade: grading.quality_grade })}</Badge>
                  <span className="font-mono-data text-xs text-ink/60 dark:text-paper/60">{t('marketplace.scorePct', { score: grading.visual_quality_score })}</span>
                  {grading.demo_mode && <Badge tone="warning">{t('marketplace.demoAiAssessment')}</Badge>}
                </div>
                <ul className="text-xs text-ink/60 dark:text-paper/60 list-disc list-inside space-y-0.5">
                  {grading.detected_notes.map((n, i) => <li key={i}>{n}</li>)}
                </ul>
                <p className="text-[11px] text-ink/40 dark:text-paper/40 italic">{grading.analysis_method}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function NewListingForm({ crops, onCreated, onClose }) {
  const { t } = useI18n()
  const [crop, setCrop] = useState('Tomato')
  const [quantity, setQuantity] = useState(1000)
  const [price, setPrice] = useState(20)
  const [availableDate, setAvailableDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [minPrice, setMinPrice] = useState('')
  const [grading, setGrading] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})

  function validate() {
    const errs = {}
    if (!quantity || quantity <= 0) errs.quantity = t('marketplace.errQuantityPositive')
    if (quantity > 100000) errs.quantity = t('marketplace.errQuantityUnrealistic')
    if (!price || price <= 0) errs.price = t('marketplace.errPricePositive')
    if (minPrice && Number(minPrice) <= 0) errs.minPrice = t('marketplace.errMinPricePositive')
    if (minPrice && Number(minPrice) > price) errs.minPrice = t('marketplace.errMinPriceTooHigh')
    if (!availableDate) errs.availableDate = t('marketplace.errAvailableDateRequired')
    setFieldErrors(errs)
    return Object.keys(errs).length === 0
  }

  async function submit(e) {
    e.preventDefault()
    setError('')
    if (!validate()) return
    setSubmitting(true)
    try {
      await api.createListing({
        crop, quantity_kg: quantity, expected_price_per_kg: price,
        available_date: availableDate,
        quality_grade: grading?.quality_grade || 'B',
        quality_score: grading?.visual_quality_score || 75,
        min_acceptable_price: minPrice ? Number(minPrice) : undefined,
      })
      onCreated()
    } catch (e) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={submit} className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5 mb-6 space-y-4">
      <h2 className="font-display font-semibold text-lg">{t('marketplace.postYourHarvest')}</h2>
      {error && <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 text-sm rounded-lg px-3 py-2">{error}</div>}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('common.crop')}</label>
          <select value={crop} onChange={e => { setCrop(e.target.value); setGrading(null) }} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-white/5 dark:text-paper">
            {crops.map(c => <option key={c.name} value={c.name}>{c.emoji} {c.name}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('common.quantityKg')}</label>
          <input type="number" min="1" value={quantity} onChange={e => setQuantity(Number(e.target.value))} className={`w-full border rounded-lg px-3 py-2.5 text-sm ${fieldErrors.quantity ? 'border-red-400' : 'border-black/10 dark:border-white/15'}`} />
          {fieldErrors.quantity && <p className="text-xs text-red-600 mt-1">{fieldErrors.quantity}</p>}
        </div>
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('marketplace.expectedPriceKg')}</label>
          <input type="number" min="1" value={price} onChange={e => setPrice(Number(e.target.value))} className={`w-full border rounded-lg px-3 py-2.5 text-sm ${fieldErrors.price ? 'border-red-400' : 'border-black/10 dark:border-white/15'}`} />
          {fieldErrors.price && <p className="text-xs text-red-600 mt-1">{fieldErrors.price}</p>}
        </div>
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('marketplace.availableFrom')}</label>
          <input type="date" value={availableDate} onChange={e => setAvailableDate(e.target.value)} className={`w-full border rounded-lg px-3 py-2.5 text-sm ${fieldErrors.availableDate ? 'border-red-400' : 'border-black/10 dark:border-white/15'}`} />
        </div>
      </div>
      <div>
        <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('marketplace.minAcceptablePrice')}</label>
        <input type="number" min="0" value={minPrice} onChange={e => setMinPrice(e.target.value)} placeholder={t('marketplace.minAcceptablePricePlaceholder')} className={`w-full sm:w-64 border rounded-lg px-3 py-2.5 text-sm ${fieldErrors.minPrice ? 'border-red-400' : 'border-black/10 dark:border-white/15'}`} />
        {fieldErrors.minPrice && <p className="text-xs text-red-600 mt-1">{fieldErrors.minPrice}</p>}
      </div>

      <QualityImageUpload crop={crop} grading={grading} setGrading={setGrading} />

      <div className="flex items-center gap-3">
        <button disabled={submitting} className="bg-marigold hover:bg-marigold-dark text-ink dark:text-paper font-semibold rounded-lg px-5 py-2.5 transition-colors disabled:opacity-60">
          {submitting ? t('marketplace.posting') : t('marketplace.postListing')}
        </button>
        <button type="button" onClick={onClose} className="text-sm text-ink/50 dark:text-paper/50 hover:underline">{t('cancel')}</button>
      </div>
    </form>
  )
}

function OffersPanel({ listing, onChanged }) {
  const { t } = useI18n()
  const [offers, setOffers] = useState(null)
  const [matches, setMatches] = useState(null)
  const [matchError, setMatchError] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [confirmAction, setConfirmAction] = useState(null) // { id, type: 'accept'|'reject' }
  const [successMsg, setSuccessMsg] = useState('')
  const [openThread, setOpenThread] = useState(null) // offer id whose negotiation thread is expanded

  useEffect(() => {
    api.offersForListing(listing.id).then(setOffers).catch(() => setOffers([]))
    api.matchBuyers(listing.id).then(r => setMatches(r.matches)).catch(e => { setMatches([]); setMatchError(e.message) })
  }, [listing.id])

  async function accept(id) {
    setBusyId(id)
    setConfirmAction(null)
    try {
      await api.acceptOffer(id)
      setSuccessMsg(t('marketplace.offerAccepted'))
      onChanged()
    } catch (e) {
      setSuccessMsg('')
      setMatchError(e.message)
    } finally {
      setBusyId(null)
    }
  }
  async function reject(id) {
    setBusyId(id)
    setConfirmAction(null)
    try {
      await api.rejectOffer(id)
      setSuccessMsg(t('marketplace.offerRejected'))
      const fresh = await api.offersForListing(listing.id)
      setOffers(fresh)
    } catch (e) {
      setMatchError(e.message)
    } finally {
      setBusyId(null)
    }
  }

  const ACTION_KEY = { accept: 'verification.approve', reject: 'verification.reject' }

  return (
    <div className="bg-wheat/50 rounded-xl p-4 mt-3 space-y-4">
      {successMsg && <div className="bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 text-emerald-700 dark:text-emerald-300 text-xs rounded-lg px-3 py-2">{successMsg}</div>}
      {matchError && <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 text-xs rounded-lg px-3 py-2">{matchError}</div>}

      {confirmAction && (
        <div className="bg-white dark:bg-white/5 border border-black/10 dark:border-white/15 rounded-lg p-3 text-sm space-y-2">
          <p>{t(`marketplace.confirmActionQuestion.${confirmAction.type}`)}</p>
          <div className="flex gap-2">
            <button
              onClick={() => confirmAction.type === 'accept' ? accept(confirmAction.id) : reject(confirmAction.id)}
              className={`text-xs rounded-lg px-3 py-1.5 font-semibold text-paper ${confirmAction.type === 'accept' ? 'bg-forest' : 'bg-red-500'}`}
            >
              {t(`marketplace.yesConfirmAction.${confirmAction.type}`)}
            </button>
            <button onClick={() => setConfirmAction(null)} className="text-xs bg-white dark:bg-white/5 border border-black/10 dark:border-white/15 rounded-lg px-3 py-1.5 font-semibold">{t('cancel')}</button>
          </div>
        </div>
      )}

      <div>
        <h4 className="text-sm font-semibold mb-2">{t('marketplace.offersReceived')} {offers ? `(${offers.length})` : ''}</h4>
        {offers === null ? <p className="text-xs text-ink/50 dark:text-paper/50">{t('common.loading')}</p> : offers.length === 0 ? (
          <p className="text-xs text-ink/50 dark:text-paper/50">{t('marketplace.noOffersYetShare')}</p>
        ) : (
          <div className="space-y-2">
            {offers.map(o => (
              <div key={o.id} className="bg-white dark:bg-white/5 rounded-lg px-3 py-2 text-sm space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">₹{o.offered_price_per_kg}/kg · {o.quantity_kg.toLocaleString()} kg</div>
                  {o.message && <div className="text-xs text-ink/50 dark:text-paper/50">"{o.message}"</div>}
                  {o.status === 'pending' && o.round_count > 1 && <div className="text-xs text-ink/50 dark:text-paper/50">{t('negotiation.round', { n: o.round_count })}</div>}
                </div>
                {o.status === 'pending' && o.awaiting_role === 'buyer' ? (
                  <Badge tone="info">{t('negotiation.awaiting.buyer')}</Badge>
                ) : o.status === 'pending' ? (
                  <div className="flex gap-2">
                    <button disabled={busyId === o.id} onClick={() => setConfirmAction({ id: o.id, type: 'accept' })} className="text-xs bg-forest text-paper rounded-lg px-3 py-1.5 font-semibold disabled:opacity-60">
                      {busyId === o.id ? t('marketplace.working') : t('marketplace.acceptShort')}
                    </button>
                    <button disabled={busyId === o.id} onClick={() => setConfirmAction({ id: o.id, type: 'reject' })} className="text-xs bg-white dark:bg-white/5 border border-black/10 dark:border-white/15 rounded-lg px-3 py-1.5 font-semibold disabled:opacity-60">
                      {t('marketplace.rejectShort')}
                    </button>
                  </div>
                ) : <Badge tone={o.status === 'accepted' ? 'success' : 'neutral'}>{t(`offer.status.${o.status}`)}</Badge>}
              </div>
              <button onClick={() => setOpenThread(openThread === o.id ? null : o.id)} className="text-xs text-forest font-semibold hover:underline">
                {openThread === o.id ? t('negotiation.hide') : t('negotiation.open')}
              </button>
              {openThread === o.id && <OfferNegotiation offerId={o.id} onChanged={() => { api.offersForListing(listing.id).then(setOffers).catch(() => {}); onChanged() }} />}
              </div>
            ))}
          </div>
        )}
      </div>
      <div>
        <h4 className="text-sm font-semibold mb-2">⭐ {t('marketplace.smartBuyerMatches')}</h4>
        {matches === null ? <p className="text-xs text-ink/50 dark:text-paper/50">{t('common.loading')}</p> : matches.length === 0 ? (
          <p className="text-xs text-ink/50 dark:text-paper/50">{t('marketplace.noBuyerMatches')}</p>
        ) : (
          <div className="space-y-2">
            {matches.map(m => (
              <div key={m.buyer_id} className="bg-white dark:bg-white/5 rounded-lg px-3 py-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium">#{m.rank} {m.company_name}</span>
                  <span className="font-mono-data font-semibold text-forest">{t('marketplace.matchPct', { pct: m.match_score })}</span>
                </div>
                {/* m.reasons are generated server-side (buyer_matcher.py) as
                    English sentences with embedded numbers; localizing them
                    requires the backend to emit structured reason codes
                    instead of prose. Tracked as a known follow-up. */}
                <div className="text-xs text-ink/50 dark:text-paper/50">{m.reasons.join(' · ')}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function MakeOfferForm({ listing, onDone }) {
  const { t } = useI18n()
  const [price, setPrice] = useState(listing.expected_price_per_kg)
  const [qty, setQty] = useState(listing.quantity_kg)
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [confirming, setConfirming] = useState(false)

  function validate() {
    const errs = {}
    if (!price || price <= 0) errs.price = t('marketplace.errOfferPricePositive')
    if (!qty || qty <= 0) errs.qty = t('marketplace.errQuantityPositive')
    if (qty > listing.quantity_kg) errs.qty = t('marketplace.errQuantityExceedsListed', { quantity: listing.quantity_kg.toLocaleString() })
    setFieldErrors(errs)
    return Object.keys(errs).length === 0
  }

  function handleSubmitClick(e) {
    e.preventDefault()
    setError('')
    if (!validate()) return
    setConfirming(true)
  }

  async function confirmSubmit() {
    setConfirming(false)
    setSubmitting(true)
    setError('')
    try {
      await api.createOffer({ listing_id: listing.id, offered_price_per_kg: price, quantity_kg: qty, message })
      onDone()
    } catch (e) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmitClick} className="bg-wheat/50 rounded-xl p-4 mt-3 space-y-3">
      {error && <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 text-xs rounded-lg px-3 py-2">{error}</div>}
      {confirming && (
        <div className="bg-white dark:bg-white/5 border border-black/10 dark:border-white/15 rounded-lg p-3 text-sm space-y-2">
          <p>{t('marketplace.confirmSendOffer', { price, qty: qty.toLocaleString() })}</p>
          <div className="flex gap-2">
            <button type="button" onClick={confirmSubmit} disabled={submitting} className="text-xs bg-forest text-paper rounded-lg px-3 py-1.5 font-semibold disabled:opacity-60">
              {submitting ? t('marketplace.sending') : t('marketplace.yesSendOffer')}
            </button>
            <button type="button" onClick={() => setConfirming(false)} className="text-xs bg-white dark:bg-white/5 border border-black/10 dark:border-white/15 rounded-lg px-3 py-1.5 font-semibold">{t('cancel')}</button>
          </div>
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('marketplace.yourOfferKg')}</label>
          <input type="number" value={price} onChange={e => setPrice(Number(e.target.value))} className={`w-full border rounded-lg px-3 py-2 text-sm ${fieldErrors.price ? 'border-red-400' : 'border-black/10 dark:border-white/15'}`} />
          {fieldErrors.price && <p className="text-xs text-red-600 mt-1">{fieldErrors.price}</p>}
        </div>
        <div>
          <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('common.quantityKg')}</label>
          <input type="number" value={qty} onChange={e => setQty(Number(e.target.value))} max={listing.quantity_kg} className={`w-full border rounded-lg px-3 py-2 text-sm ${fieldErrors.qty ? 'border-red-400' : 'border-black/10 dark:border-white/15'}`} />
          {fieldErrors.qty && <p className="text-xs text-red-600 mt-1">{fieldErrors.qty}</p>}
        </div>
      </div>

      <input value={message} onChange={e => setMessage(e.target.value)} placeholder={t('marketplace.messageToFarmer')} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper" />
      <button disabled={submitting} className="bg-forest text-paper text-sm font-semibold rounded-lg px-4 py-2 disabled:opacity-60">
        {submitting ? t('marketplace.sending') : t('marketplace.sendOffer')}
      </button>
    </form>
  )
}

export default function Marketplace() {
  const { role } = useAuth()
  const { t } = useI18n()
  const [crops, setCrops] = useState([])
  const [listings, setListings] = useState(null)
  const [cropFilter, setCropFilter] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [expandedId, setExpandedId] = useState(null)
  const [scope, setScope] = useState('all') // all | mine

  useEffect(() => { api.getCrops().then(setCrops) }, [])

  async function loadListings() {
    setListings(null)
    try {
      const data = scope === 'mine' && role === 'farmer'
        ? await api.myListings()
        : await api.getListings(cropFilter ? { crop: cropFilter } : {})
      setListings(data)
    } catch (e) {
      setListings([])
    }
  }

  useEffect(() => { loadListings() }, [cropFilter, scope]) // eslint-disable-line

  return (
    <div>
      <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
        <h1 className="font-display text-3xl font-bold">🌾 {t('navMarketplace')}</h1>
        {role === 'farmer' && (
          <button onClick={() => setShowForm(s => !s)} className="bg-marigold hover:bg-marigold-dark text-ink dark:text-paper font-semibold rounded-lg px-4 py-2 text-sm transition-colors">
            {showForm ? t('marketplace.closeForm') : `+ ${t('marketplace.postHarvest')}`}
          </button>
        )}
      </div>
      <p className="text-ink/60 dark:text-paper/60 mb-6">{t('marketplace.subtitle')}</p>

      {showForm && role === 'farmer' && (
        <NewListingForm crops={crops} onCreated={() => { setShowForm(false); setScope('mine'); loadListings() }} onClose={() => setShowForm(false)} />
      )}

      <div className="flex flex-wrap items-center gap-3 mb-6">
        {role === 'farmer' && (
          <div className="flex bg-white dark:bg-white/5 border border-black/10 dark:border-white/15 rounded-lg p-1 text-sm">
            <button onClick={() => setScope('all')} className={`px-3 py-1.5 rounded-md font-medium ${scope === 'all' ? 'bg-forest text-paper' : 'text-ink/60 dark:text-paper/60'}`}>{t('marketplace.allListings')}</button>
            <button onClick={() => setScope('mine')} className={`px-3 py-1.5 rounded-md font-medium ${scope === 'mine' ? 'bg-forest text-paper' : 'text-ink/60 dark:text-paper/60'}`}>{t('marketplace.myListings')}</button>
          </div>
        )}
        <select value={cropFilter} onChange={e => setCropFilter(e.target.value)} className="border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm">
          <option value="">{t('storage.allCrops')}</option>
          {crops.map(c => <option key={c.name} value={c.name}>{c.emoji} {c.name}</option>)}
        </select>
      </div>

      {listings === null ? <LoadingSpinner label={t('marketplace.loadingListings')} /> : listings.length === 0 ? (
        <p className="text-sm text-ink/50 dark:text-paper/50">{t('marketplace.noListingsFound')}</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {listings.map(l => (
            <div key={l.id} className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="font-display font-semibold text-lg">{l.crop}</div>
                  <div className="text-xs text-ink/50 dark:text-paper/50">{l.location} · {t('marketplace.availableOn', { date: l.available_date })}</div>
                </div>
                <Badge tone={l.status === 'active' ? 'success' : l.status === 'sold' ? 'forest' : 'neutral'}>{t(`marketplace.listingStatus.${l.status}`)}</Badge>
              </div>
              <div className="grid grid-cols-3 gap-2 text-sm mb-3">
                <div><div className="text-xs text-ink/40 dark:text-paper/40">{t('grievance.category.QUANTITY')}</div><div className="font-mono-data font-semibold">{l.quantity_kg.toLocaleString()} kg</div></div>
                <div><div className="text-xs text-ink/40 dark:text-paper/40">{t('lots.grade')}</div><div className="font-semibold">{l.quality_grade} ({l.quality_score}%)</div></div>
                <div><div className="text-xs text-ink/40 dark:text-paper/40">{t('marketplace.expected')}</div><div className="font-mono-data font-semibold">₹{l.expected_price_per_kg}/kg</div></div>
              </div>

              {role === 'buyer' && l.status === 'active' && (
                expandedId === l.id ? <MakeOfferForm listing={l} onDone={() => { setExpandedId(null); loadListings() }} /> : (
                  <button onClick={() => setExpandedId(l.id)} className="text-sm bg-forest text-paper font-semibold rounded-lg px-4 py-2">{t('marketplace.makeAnOffer')}</button>
                )
              )}

              {role === 'farmer' && scope === 'mine' && (
                <button onClick={() => setExpandedId(expandedId === l.id ? null : l.id)} className="text-sm text-forest font-semibold hover:underline">
                  {expandedId === l.id ? t('marketplace.hideOffersMatches') : `${t('marketplace.viewOffersMatches')} →`}
                </button>
              )}
              {role === 'farmer' && scope === 'mine' && expandedId === l.id && (
                <OffersPanel listing={l} onChanged={loadListings} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
