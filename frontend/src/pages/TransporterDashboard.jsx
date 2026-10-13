import React, { useEffect, useState, useCallback } from 'react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'
import Badge from '../components/Badge'
import { useI18n } from '../i18n/I18nContext'
import { formatTimestamp } from '../utils/datetime'

const STATUS_TONE = {
  REQUESTED: 'info', MATCHED: 'marigold', CONFIRMED: 'forest',
  PICKED_UP: 'warning', IN_TRANSIT: 'warning', DELIVERED: 'success',
  COMPLETED: 'success', CANCELLED: 'neutral',
}
const NEXT_TRANSPORTER_STATUS = {
  CONFIRMED: 'PICKED_UP', MATCHED: 'PICKED_UP',
  PICKED_UP: 'IN_TRANSIT', IN_TRANSIT: 'DELIVERED', DELIVERED: 'COMPLETED',
}

function RequestCard({ r, selected, onSelect, t }) {
  return (
    <button onClick={() => onSelect(r.id)} className={`w-full text-left bg-white dark:bg-white/5 rounded-2xl border p-4 transition-colors ${selected ? 'border-forest ring-1 ring-forest' : 'border-black/5 dark:border-white/10 hover:border-forest/40'}`}>
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="font-semibold text-sm">{r.pickup_location} → {r.destination}</span>
        <Badge tone={STATUS_TONE[r.status] || 'neutral'}>{r.status}</Badge>
      </div>
      <div className="text-xs text-ink/60 dark:text-paper/60">
        {r.quantity_kg ? `${r.quantity_kg} kg` : ''} {r.pickup_date ? `· ${r.pickup_date}` : ''}
      </div>
      {r.transporter_agreed_price != null && (
        <div className="text-sm font-semibold text-forest mt-1">{t('transporter.agreed')}: ₹{r.transporter_agreed_price}</div>
      )}
    </button>
  )
}

function OfferHistory({ offers, t }) {
  if (!offers || offers.length === 0) return <p className="text-sm text-ink/50 dark:text-paper/50">{t('transporter.noOffersYet')}</p>
  return (
    <div className="space-y-2">
      {offers.map(o => (
        <div key={o.id} className={`flex items-center justify-between text-sm rounded-lg px-3 py-2 ${o.status === 'ACCEPTED' ? 'bg-forest/10 border border-forest/30' : 'bg-mist dark:bg-white/5'}`}>
          <span>
            <strong>₹{o.amount}</strong> — {o.sender_role === 'transporter' ? t('transporter.you') : t('transporter.farmer')}
            {o.status === 'ACCEPTED' && <span className="ml-2 text-forest">✅ {t('transporter.agreedLabel')}</span>}
            {o.status === 'REJECTED' && <span className="ml-2 text-ink/40">{t('transporter.rejectedLabel')}</span>}
          </span>
          <span className="text-xs text-ink/50 dark:text-paper/50">{formatTimestamp(o.created_at)}</span>
        </div>
      ))}
    </div>
  )
}

function ChatPanel({ requestId, t }) {
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try { setMessages(await api.listTransportMessages(requestId)) } catch (e) { setError(e.message) }
  }, [requestId])

  useEffect(() => { load() }, [load])

  async function send() {
    if (!text.trim()) return
    setBusy(true); setError('')
    try {
      await api.sendTransportMessage(requestId, text.trim())
      setText('')
      await load()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="bg-mist dark:bg-white/5 rounded-xl p-3">
      <div className="max-h-48 overflow-y-auto space-y-1.5 mb-2">
        {messages.length === 0 && <p className="text-xs text-ink/40 dark:text-paper/40">{t('transporter.noMessagesYet')}</p>}
        {messages.map(m => (
          <div key={m.id} className={`text-sm px-2.5 py-1.5 rounded-lg max-w-[85%] ${m.sender_role === 'transporter' ? 'bg-forest text-paper ml-auto' : 'bg-white dark:bg-white/10'}`}>
            {m.message}
            <div className="text-[10px] opacity-60 mt-0.5">{formatTimestamp(m.created_at)}</div>
          </div>
        ))}
      </div>
      {error && <div className="text-xs text-red-600 mb-1">{error}</div>}
      <div className="flex gap-2">
        <input
          name="transport-chat-message" id="transport-chat-message"
          value={text} onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder={t('transporter.chatPlaceholder')}
          className="flex-1 border border-black/10 dark:border-white/15 rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-white/5"
        />
        <button disabled={busy} onClick={send} className="bg-forest text-paper text-sm font-semibold px-3 py-1.5 rounded-lg disabled:opacity-60">{t('transporter.send')}</button>
      </div>
    </div>
  )
}

function ReviewForm({ requestId, reviews, t, onSubmitted }) {
  const [rating, setRating] = useState(5)
  const [comment, setComment] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const alreadyReviewed = reviews.some(r => r.reviewer_role === 'transporter')

  async function submit() {
    setBusy(true); setError('')
    try {
      await api.submitTransportReview(requestId, { rating, comment })
      onSubmitted()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (alreadyReviewed) return <p className="text-sm text-ink/50 dark:text-paper/50">{t('transporter.alreadyReviewed')}</p>

  return (
    <div className="space-y-2">
      <div className="flex gap-1">
        {[1, 2, 3, 4, 5].map(n => (
          <button key={n} onClick={() => setRating(n)} className={`text-2xl ${n <= rating ? 'text-marigold' : 'text-black/15 dark:text-white/15'}`}>★</button>
        ))}
      </div>
      <textarea name="review-comment" id="review-comment" value={comment} onChange={e => setComment(e.target.value)} placeholder={t('transporter.reviewCommentPlaceholder')} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5" rows={2} />
      {error && <div className="text-xs text-red-600">{error}</div>}
      <button disabled={busy} onClick={submit} className="bg-marigold text-ink font-semibold text-sm px-4 py-2 rounded-lg disabled:opacity-60">{t('transporter.submitReview')}</button>
    </div>
  )
}

export default function TransporterDashboard() {
  const { user } = useAuth()
  const { t } = useI18n()
  const [tab, setTab] = useState('available')
  const [available, setAvailable] = useState(null)
  const [mine, setMine] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [offers, setOffers] = useState([])
  const [reviews, setReviews] = useState([])
  const [offerAmount, setOfferAmount] = useState('')
  const [offerMsg, setOfferMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const loadLists = useCallback(async () => {
    try {
      const [a, m] = await Promise.all([api.transporterAvailableRequests(), api.transporterMyRequests()])
      setAvailable(a); setMine(m)
    } catch (e) { setError(e.message) }
  }, [])

  useEffect(() => { loadLists() }, [loadLists])

  const loadDetail = useCallback(async (id) => {
    try {
      const [d, o, rv] = await Promise.all([
        api.transporterRequestDetail(id), api.listTransportOffers(id), api.listTransportReviews(id),
      ])
      setDetail(d); setOffers(o); setReviews(rv)
    } catch (e) { setError(e.message) }
  }, [])

  function selectRequest(id) {
    setSelectedId(id)
    loadDetail(id)
  }

  async function claim(id) {
    setBusy(true); setError('')
    try {
      await api.transporterClaimRequest(id)
      await loadLists()
      setTab('mine')
      selectRequest(id)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function makeOffer() {
    if (!offerAmount) return
    setBusy(true); setError('')
    try {
      await api.makeTransportOffer(selectedId, { amount: Number(offerAmount), message: offerMsg || null })
      setOfferAmount(''); setOfferMsg('')
      await loadDetail(selectedId)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function acceptOffer(offerId) {
    setBusy(true); setError('')
    try {
      await api.acceptTransportOffer(selectedId, offerId)
      await loadDetail(selectedId)
      await loadLists()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function advanceStatus() {
    const next = NEXT_TRANSPORTER_STATUS[detail?.status]
    if (!next) return
    setBusy(true); setError('')
    try {
      await api.updateTransportStatus(selectedId, next)
      await loadDetail(selectedId)
      await loadLists()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (available === null || mine === null) return <LoadingSpinner />

  const list = tab === 'available' ? available : mine

  return (
    <div className="p-4 md:p-8 max-w-[1500px] w-full mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-display font-bold">{t('transporter.dashboardTitle')}</h1>
        <p className="text-sm text-ink/60 dark:text-paper/60">{t('transporter.dashboardSubtitle', { name: user?.name || '' })}</p>
      </div>

      {error && <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 text-sm rounded-lg px-3 py-2">{error}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        <div className="lg:col-span-1 space-y-3">
          <div className="flex bg-mist dark:bg-white/5 rounded-xl p-1">
            <button onClick={() => setTab('available')} className={`flex-1 py-1.5 rounded-lg text-sm font-semibold ${tab === 'available' ? 'bg-forest text-paper' : 'text-ink/60 dark:text-paper/60'}`}>{t('transporter.available')} ({available.length})</button>
            <button onClick={() => setTab('mine')} className={`flex-1 py-1.5 rounded-lg text-sm font-semibold ${tab === 'mine' ? 'bg-forest text-paper' : 'text-ink/60 dark:text-paper/60'}`}>{t('transporter.myRequests')} ({mine.length})</button>
          </div>
          {list.length === 0 && <p className="text-sm text-ink/50 dark:text-paper/50 px-1">{t('transporter.noRequests')}</p>}
          {list.map(r => (
            <div key={r.id}>
              <RequestCard r={r} selected={selectedId === r.id} onSelect={selectRequest} t={t} />
              {tab === 'available' && (
                <button disabled={busy} onClick={() => claim(r.id)} className="mt-1 w-full text-xs font-semibold bg-marigold hover:bg-marigold-dark text-ink py-1.5 rounded-lg disabled:opacity-60">
                  {t('transporter.claimRequest')}
                </button>
              )}
            </div>
          ))}
        </div>

        <div className="lg:col-span-2">
          {!detail ? (
            <div className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-8 text-center text-sm text-ink/50 dark:text-paper/50">
              {t('transporter.selectRequestHint')}
            </div>
          ) : (
            <div className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-5 space-y-5">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold">{detail.pickup_location} → {detail.destination}</div>
                  <div className="text-xs text-ink/60 dark:text-paper/60">
                    {detail.quantity_kg ? `${detail.quantity_kg} kg` : ''} {detail.pickup_date ? `· ${detail.pickup_date} ${detail.pickup_time || ''}` : ''}
                    {detail.estimated_cost != null && ` · ${t('transporter.estimate')} ₹${detail.estimated_cost}`}
                  </div>
                  {detail.farmer && <div className="text-xs text-ink/50 dark:text-paper/50 mt-1">{t('transporter.farmerLabel')}: {detail.farmer.name} ({detail.farmer.location})</div>}
                </div>
                <Badge tone={STATUS_TONE[detail.status] || 'neutral'}>{detail.status}</Badge>
              </div>

              {detail.transporter_id && (
                <section>
                  <h3 className="text-sm font-semibold mb-2">{t('transporter.negotiationHistory')}</h3>
                  <OfferHistory offers={offers} t={t} />
                  {detail.negotiation_status !== 'AGREED' && detail.negotiation_status !== 'DECLINED' && (
                    <div className="mt-3 space-y-2">
                      {offers.length > 0 && offers[offers.length - 1].status === 'PENDING' && offers[offers.length - 1].sender_role === 'farmer' && (
                        <button disabled={busy} onClick={() => acceptOffer(offers[offers.length - 1].id)} className="text-xs font-semibold bg-forest text-paper px-3 py-1.5 rounded-lg disabled:opacity-60">
                          {t('transporter.acceptOffer')} ₹{offers[offers.length - 1].amount}
                        </button>
                      )}
                      <div className="flex gap-2">
                        <input name="offer-amount" id="offer-amount" type="number" value={offerAmount} onChange={e => setOfferAmount(e.target.value)} placeholder={t('transporter.yourOfferPlaceholder')} className="w-32 border border-black/10 dark:border-white/15 rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-white/5" />
                        <input name="offer-message" id="offer-message" value={offerMsg} onChange={e => setOfferMsg(e.target.value)} placeholder={t('transporter.offerNotePlaceholder')} className="flex-1 border border-black/10 dark:border-white/15 rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-white/5" />
                        <button disabled={busy} onClick={makeOffer} className="text-xs font-semibold bg-marigold hover:bg-marigold-dark text-ink px-3 py-1.5 rounded-lg disabled:opacity-60">{t('transporter.sendOffer')}</button>
                      </div>
                    </div>
                  )}
                </section>
              )}

              {detail.transporter_id && (
                <section>
                  <h3 className="text-sm font-semibold mb-2">{t('transporter.chat')}</h3>
                  <ChatPanel requestId={selectedId} t={t} />
                </section>
              )}

              {detail.negotiation_status === 'AGREED' && NEXT_TRANSPORTER_STATUS[detail.status] && (
                <button disabled={busy} onClick={advanceStatus} className="text-sm font-semibold bg-forest text-paper px-4 py-2 rounded-lg disabled:opacity-60">
                  {t('transporter.markAs')} {NEXT_TRANSPORTER_STATUS[detail.status]}
                </button>
              )}

              {(detail.status === 'DELIVERED' || detail.status === 'COMPLETED') && (
                <section>
                  <h3 className="text-sm font-semibold mb-2">{t('transporter.rateFarmer')}</h3>
                  <ReviewForm requestId={selectedId} reviews={reviews} t={t} onSubmitted={() => loadDetail(selectedId)} />
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
