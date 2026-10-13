import React, { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nContext'
import Badge from './Badge'
import { formatTimestamp } from '../utils/datetime'

/**
 * Multi-round negotiation thread for ONE crop offer (buyer <-> farmer).
 *
 * Everything shown and every permission comes from the server
 * (GET /offers/{id}: rounds, can_act, awaiting_role). The component never
 * sends sender/receiver/buyer/farmer ids -- only price / quantity / message
 * for a counter, and the round id for accept/reject (the server re-checks
 * that it is still the current round and that it is this user's turn).
 */

const ROUND_TONE = { PENDING: 'info', COUNTERED: 'neutral', ACCEPTED: 'success', REJECTED: 'warning', WITHDRAWN: 'neutral' }

export default function OfferNegotiation({ offerId, onChanged }) {
  const { t } = useI18n()
  const [thread, setThread] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(null) // 'accept' | 'reject' | 'withdraw'
  const [showCounter, setShowCounter] = useState(false)
  const [price, setPrice] = useState('')
  const [qty, setQty] = useState('')
  const [message, setMessage] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})

  const load = useCallback(async () => {
    setLoadError('')
    try {
      const data = await api.offerThread(offerId)
      setThread(data)
      return data
    } catch (e) {
      setLoadError(e?.message || t('negotiation.loadFailed'))
      return null
    }
  }, [offerId, t])

  useEffect(() => { setThread(null); load() }, [load])

  const rounds = thread?.rounds || []
  const current = rounds.length ? rounds[rounds.length - 1] : null
  const can = thread?.can_act || {}

  function openCounter() {
    setPrice(current ? String(current.price_per_kg) : '')
    setQty(current ? String(current.quantity_kg) : '')
    setMessage('')
    setFieldErrors({})
    setShowCounter(true)
    setConfirm(null)
  }

  async function run(fn, successKey) {
    setActionError(''); setNotice(''); setBusy(true)
    try {
      await fn()
      setNotice(t(successKey))
      setConfirm(null); setShowCounter(false)
      await load()
      onChanged && onChanged()
    } catch (e) {
      if (e?.status === 409) {           // stale round / concurrent response: show the latest state
        await load()
        setNotice(t('negotiation.staleReloaded'))
        setConfirm(null); setShowCounter(false)
      } else {
        setActionError(e?.message || t('negotiation.actionFailed'))
      }
    } finally {
      setBusy(false)
    }
  }

  function submitCounter() {
    const p = parseFloat(price)
    const q = parseFloat(qty)
    const errs = {}
    if (!(p > 0)) errs.price = t('negotiation.errPricePositive')
    if (!(q > 0)) errs.qty = t('negotiation.errQtyPositive')
    else if (thread?.target?.quantity_kg != null && q > thread.target.quantity_kg) {
      errs.qty = t('negotiation.errQtyMax', { max: thread.target.quantity_kg })
    }
    setFieldErrors(errs)
    if (Object.keys(errs).length) return
    run(() => api.counterOffer(offerId, {
      price_per_kg: p, quantity_kg: q, message: message.trim() || null, based_on_round_id: current?.id,
    }), 'negotiation.counterSentToast')
  }

  if (loadError && !thread) {
    return (
      <div className="rounded-lg border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300 text-xs px-3 py-2 flex items-center justify-between gap-3">
        <span>{loadError}</span>
        <button onClick={load} className="font-semibold underline">{t('negotiation.retry')}</button>
      </div>
    )
  }
  if (!thread) return <p className="text-xs text-ink/50 dark:text-paper/50">{t('negotiation.loading')}</p>

  const offer = thread.offer
  const open = offer.status === 'pending'
  const who = (role) => (role === 'buyer' ? t('negotiation.buyer') : t('negotiation.farmer'))
  const confirmText = confirm && current ? t(`negotiation.confirm.${confirm}`, { price: current.price_per_kg, qty: current.quantity_kg }) : ''

  return (
    <div className="rounded-xl border border-black/10 dark:border-white/15 bg-white dark:bg-white/5 p-3 space-y-3 text-xs" data-testid="offer-negotiation">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="font-semibold text-sm">{t('negotiation.history')}</div>
          {thread.target && (
            <div className="text-ink/50 dark:text-paper/50">
              {t('negotiation.target', { crop: thread.target.crop, location: thread.target.location, qty: Number(thread.target.quantity_kg).toLocaleString() })}
            </div>
          )}
        </div>
        {open
          ? <Badge tone={thread.awaiting_role && can.accept ? 'warning' : 'info'}>
              {can.accept ? t('negotiation.awaitingYou') : t(`negotiation.awaiting.${thread.awaiting_role || 'farmer'}`)}
            </Badge>
          : <Badge tone={offer.status === 'accepted' ? 'success' : 'neutral'}>{t(`offer.status.${offer.status}`)}</Badge>}
      </div>

      {notice && <div className="bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 text-emerald-700 dark:text-emerald-300 rounded-lg px-3 py-2">{notice}</div>}
      {actionError && <div role="alert" className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 rounded-lg px-3 py-2">{actionError}</div>}

      {rounds.length === 0 ? (
        <p className="text-ink/50 dark:text-paper/50">{t('negotiation.noRounds')}</p>
      ) : (
        <ol className="space-y-2">
          {rounds.map(r => (
            <li key={r.id} className={`rounded-lg px-3 py-2 border ${r.status === 'PENDING' ? 'border-sky-300 dark:border-sky-800 bg-sky-50/60 dark:bg-sky-950/20' : 'border-black/5 dark:border-white/10 bg-wheat/40 dark:bg-white/5'}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold">{t('negotiation.round', { n: r.sequence })} · {who(r.sender_role)}</span>
                <Badge tone={ROUND_TONE[r.status] || 'neutral'}>{t(`negotiation.roundStatus.${r.status}`)}</Badge>
              </div>
              <div className="mt-1 font-mono-data text-sm">
                {t('negotiation.terms', { price: r.price_per_kg, qty: Number(r.quantity_kg).toLocaleString() })}
                <span className="text-ink/50 dark:text-paper/50"> · {t('negotiation.total', { total: Math.round(r.price_per_kg * r.quantity_kg).toLocaleString() })}</span>
              </div>
              {r.message && <div className="text-ink/60 dark:text-paper/60 mt-0.5">“{r.message}”</div>}
              <div className="text-ink/40 dark:text-paper/40 mt-0.5">{formatTimestamp(r.created_at)}</div>
            </li>
          ))}
        </ol>
      )}

      {offer.status === 'accepted' && (
        <div className="rounded-lg bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 px-3 py-2 flex flex-wrap items-center justify-between gap-2">
          <span className="font-semibold text-emerald-800 dark:text-emerald-300">
            {t('negotiation.dealAgreed', { price: offer.agreed_price_per_kg, qty: Number(offer.agreed_quantity_kg).toLocaleString() })}
          </span>
          {thread.transaction_id && <Link to={`/transactions/${thread.transaction_id}`} className="underline font-semibold text-forest">{t('negotiation.viewTransaction')}</Link>}
        </div>
      )}
      {!open && offer.status !== 'accepted' && <p className="text-ink/50 dark:text-paper/50">{t('negotiation.closed', { status: t(`offer.status.${offer.status}`) })}</p>}

      {open && !can.accept && can.withdraw && <p className="text-ink/60 dark:text-paper/60">{t('negotiation.waitingOther')}</p>}

      {confirm && (
        <div className="rounded-lg border border-black/10 dark:border-white/15 p-3 space-y-2">
          <p className="text-sm">{confirmText}</p>
          <div className="flex gap-2">
            <button disabled={busy} onClick={() => {
              if (confirm === 'accept') run(() => api.acceptOfferRound(offerId, current.id), 'negotiation.acceptedToast')
              else if (confirm === 'reject') run(() => api.rejectOfferRound(offerId, current.id), 'negotiation.rejectedToast')
              else run(() => api.withdrawOffer(offerId), 'negotiation.withdrawnToast')
            }} className={`rounded-lg px-3 py-1.5 font-semibold text-paper disabled:opacity-60 ${confirm === 'accept' ? 'bg-forest' : 'bg-red-500'}`}>
              {busy ? t('negotiation.working') : t('negotiation.yesConfirm')}
            </button>
            <button disabled={busy} onClick={() => setConfirm(null)} className="rounded-lg px-3 py-1.5 font-semibold border border-black/10 dark:border-white/15">{t('cancel')}</button>
          </div>
        </div>
      )}

      {showCounter && (
        <div className="rounded-lg border border-black/10 dark:border-white/15 p-3 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="block font-semibold mb-1">{t('negotiation.counterPrice')}</span>
              <input type="number" min="0" step="0.01" value={price} onChange={e => setPrice(e.target.value)} className="w-full rounded-lg border border-black/10 dark:border-white/15 bg-transparent px-2 py-1.5" />
              {fieldErrors.price && <span className="text-red-600">{fieldErrors.price}</span>}
            </label>
            <label className="block">
              <span className="block font-semibold mb-1">{t('negotiation.counterQty')}</span>
              <input type="number" min="0" step="1" value={qty} onChange={e => setQty(e.target.value)} className="w-full rounded-lg border border-black/10 dark:border-white/15 bg-transparent px-2 py-1.5" />
              {fieldErrors.qty && <span className="text-red-600">{fieldErrors.qty}</span>}
            </label>
          </div>
          <label className="block">
            <span className="block font-semibold mb-1">{t('negotiation.counterMessage')}</span>
            <input type="text" maxLength={2000} value={message} onChange={e => setMessage(e.target.value)} className="w-full rounded-lg border border-black/10 dark:border-white/15 bg-transparent px-2 py-1.5" />
          </label>
          <div className="flex gap-2">
            <button disabled={busy} onClick={submitCounter} className="rounded-lg px-3 py-1.5 font-semibold text-paper bg-forest disabled:opacity-60">{busy ? t('negotiation.working') : t('negotiation.sendCounter')}</button>
            <button disabled={busy} onClick={() => setShowCounter(false)} className="rounded-lg px-3 py-1.5 font-semibold border border-black/10 dark:border-white/15">{t('cancel')}</button>
          </div>
        </div>
      )}

      {open && !confirm && !showCounter && (can.accept || can.withdraw) && (
        <div className="flex flex-wrap gap-2">
          {can.accept && <button disabled={busy} onClick={() => { setConfirm('accept'); setShowCounter(false) }} className="rounded-lg px-3 py-1.5 font-semibold text-paper bg-forest disabled:opacity-60">{t('negotiation.accept')}</button>}
          {can.counter && <button disabled={busy} onClick={openCounter} className="rounded-lg px-3 py-1.5 font-semibold border border-forest text-forest disabled:opacity-60">{t('negotiation.counter')}</button>}
          {can.reject && <button disabled={busy} onClick={() => { setConfirm('reject'); setShowCounter(false) }} className="rounded-lg px-3 py-1.5 font-semibold border border-red-200 text-red-500 disabled:opacity-60">{t('negotiation.reject')}</button>}
          {can.withdraw && <button disabled={busy} onClick={() => { setConfirm('withdraw'); setShowCounter(false) }} className="rounded-lg px-3 py-1.5 font-semibold border border-black/10 dark:border-white/15 disabled:opacity-60">{t('negotiation.withdraw')}</button>}
        </div>
      )}
    </div>
  )
}
