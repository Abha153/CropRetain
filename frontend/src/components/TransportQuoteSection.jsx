import React, { useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nContext'
import Badge from './Badge'
import { formatTimestamp } from '../utils/datetime'

/**
 * Estimate -> transporter quote -> (optional counter) -> agreed price.
 *
 * There is no transporter login in this codebase (only farmer/buyer/admin
 * roles), so the quote is recorded by the farmer who owns the trip -- the
 * same way driver_name/driver_contact already are. Accept/reject/agree are
 * resolved and stored server-side (backend/app/routers/transport.py); this
 * component only ever sends the number the farmer typed for a NEW quote or
 * counter, never a self-reported "agreed" amount.
 */

const QUOTE_BADGE_TONE = {
  AWAITING_QUOTE: 'neutral',
  QUOTED: 'info',
  COUNTERED: 'warning',
  ACCEPTED: 'success',
  REJECTED: 'neutral',
}

export default function TransportQuoteSection({ trip, onUpdated }) {
  const { t } = useI18n()
  const [quoteInput, setQuoteInput] = useState('')
  const [counterInput, setCounterInput] = useState('')
  const [showCounter, setShowCounter] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (!trip || trip.status === 'CANCELLED') return null

  const qs = trip.quote_status || 'AWAITING_QUOTE'

  async function run(fn) {
    setError('')
    setBusy(true)
    try {
      const updated = await fn()
      onUpdated(updated)
      setQuoteInput('')
      setCounterInput('')
      setShowCounter(false)
    } catch (e) {
      setError(e?.message || t('transport.quote.actionFailed'))
    } finally {
      setBusy(false)
    }
  }

  function submitQuote(e) {
    e.preventDefault()
    const val = parseFloat(quoteInput)
    if (!val || val <= 0) { setError(t('transport.quote.invalidAmount')); return }
    run(() => api.submitTransportQuote(trip.id, val))
  }

  function submitCounter(e) {
    e.preventDefault()
    const val = parseFloat(counterInput)
    if (!val || val <= 0) { setError(t('transport.quote.invalidAmount')); return }
    run(() => api.counterTransportOffer(trip.id, val))
  }

  const inputClass = "w-32 border border-black/10 dark:border-white/15 rounded-lg px-2 py-1.5 text-sm bg-white dark:bg-white/5 dark:text-paper"

  return (
    <div className="mt-4 pt-4 border-t border-black/5 dark:border-white/10">
      <p className="text-xs font-bold uppercase tracking-wide text-ink/50 dark:text-paper/50 mb-2">
        {t('transport.quote.sectionTitle')}
      </p>

      {error && <p className="text-xs text-red-500 mb-2">{error}</p>}

      {/* ESTIMATE -- CropRetain's own pre-trip estimate. Never the payable amount. */}
      {trip.estimated_cost != null && (
        <div className="flex items-center justify-between text-sm py-1">
          <span className="text-ink/60 dark:text-paper/60">{t('transport.estimatedCost')}</span>
          <span className="font-semibold">₹{trip.estimated_cost.toLocaleString('en-IN')}</span>
        </div>
      )}

      {/* No quote yet -- record one from the transporter */}
      {qs === 'AWAITING_QUOTE' && (
        <form onSubmit={submitQuote} className="flex flex-wrap items-center gap-2 mt-2">
          <span className="text-xs text-ink/50 dark:text-paper/50 flex-1 min-w-[140px]">{t('transport.quote.waitingForQuote')}</span>
          <input type="number" step="0.01" min="0" value={quoteInput} onChange={e => setQuoteInput(e.target.value)}
            placeholder={t('transport.quote.quoteAmountLabel')} disabled={busy} className={inputClass} />
          <button type="submit" disabled={busy}
            className="bg-forest text-paper px-3 py-1.5 rounded-lg text-xs font-semibold hover:bg-forest/90 disabled:opacity-50">
            {busy ? t('transport.quote.submitting') : t('transport.quote.submitQuote')}
          </button>
        </form>
      )}

      {/* ACTUAL TRANSPORTER QUOTE, once one exists */}
      {qs !== 'AWAITING_QUOTE' && trip.quoted_price != null && (
        <>
          <div className="flex items-center justify-between text-sm py-1">
            <span className="text-ink/60 dark:text-paper/60">{t('transport.quote.transporterQuote')}</span>
            <span className="flex items-center gap-2">
              <span className="font-bold text-forest dark:text-forest-light">₹{trip.quoted_price.toLocaleString('en-IN')}</span>
              <Badge tone={QUOTE_BADGE_TONE[qs] || 'neutral'}>{t(`transport.quote.statusLabel.${qs}`)}</Badge>
            </span>
          </div>
          {formatTimestamp(trip.quoted_at) && (
            <p className="text-[11px] text-ink/40 dark:text-paper/40">
              {t('transport.quote.quoted')} · {formatTimestamp(trip.quoted_at)}
            </p>
          )}
        </>
      )}

      {qs === 'COUNTERED' && trip.counter_price != null && (
        <p className="text-xs text-amber-700 dark:text-amber-400 mt-1">
          {t('transport.quote.counterOffer')}: ₹{trip.counter_price.toLocaleString('en-IN')}
          {formatTimestamp(trip.counter_at) && ` · ${formatTimestamp(trip.counter_at)}`}
        </p>
      )}

      {/* Farmer decision on a live quote */}
      {qs === 'QUOTED' && (
        <div className="mt-2 space-y-2">
          <div className="flex flex-wrap gap-2">
            <button onClick={() => run(() => api.acceptTransportQuote(trip.id))} disabled={busy}
              className="bg-forest text-paper px-3 py-1.5 rounded-lg text-xs font-semibold hover:bg-forest/90 disabled:opacity-50">
              {t('transport.quote.acceptQuote')}
            </button>
            <button onClick={() => run(() => api.rejectTransportQuote(trip.id))} disabled={busy}
              className="border border-red-200 text-red-500 px-3 py-1.5 rounded-lg text-xs font-semibold hover:bg-red-50 disabled:opacity-50">
              {t('transport.quote.rejectQuote')}
            </button>
            <button type="button" onClick={() => setShowCounter(s => !s)} disabled={busy}
              className="border border-black/10 dark:border-white/15 px-3 py-1.5 rounded-lg text-xs font-semibold">
              {t('transport.quote.counterOffer')}
            </button>
          </div>
          {showCounter && (
            <form onSubmit={submitCounter} className="flex flex-wrap items-center gap-2">
              <input type="number" step="0.01" min="0" value={counterInput} onChange={e => setCounterInput(e.target.value)}
                placeholder={t('transport.quote.counterAmountLabel')} disabled={busy} className={inputClass} />
              <button type="submit" disabled={busy}
                className="bg-marigold text-ink px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-50">
                {t('transport.quote.submitCounter')}
              </button>
            </form>
          )}
        </div>
      )}

      {/* Transporter (recorded by the farmer) revises the price after a counter */}
      {qs === 'COUNTERED' && (
        <form onSubmit={submitQuote} className="flex flex-wrap items-center gap-2 mt-2">
          <input type="number" step="0.01" min="0" value={quoteInput} onChange={e => setQuoteInput(e.target.value)}
            placeholder={t('transport.quote.quoteAmountLabel')} disabled={busy} className={inputClass} />
          <button type="submit" disabled={busy}
            className="bg-forest text-paper px-3 py-1.5 rounded-lg text-xs font-semibold hover:bg-forest/90 disabled:opacity-50">
            {busy ? t('transport.quote.submitting') : t('transport.quote.submitQuote')}
          </button>
        </form>
      )}

      {/* AGREED PRICE -- authoritative, server-stored */}
      {qs === 'ACCEPTED' && trip.agreed_price != null && (
        <div className="mt-2 bg-forest/5 dark:bg-forest-light/10 rounded-lg px-3 py-2">
          <p className="text-xs text-ink/50 dark:text-paper/50">{t('transport.quote.agreedTransportCost')}</p>
          <p className="font-bold text-lg text-forest dark:text-forest-light">₹{trip.agreed_price.toLocaleString('en-IN')}</p>
          {formatTimestamp(trip.agreed_at) && (
            <p className="text-[11px] text-ink/40 dark:text-paper/40">{t('transport.quote.confirmed')} · {formatTimestamp(trip.agreed_at)}</p>
          )}
        </div>
      )}
    </div>
  )
}
