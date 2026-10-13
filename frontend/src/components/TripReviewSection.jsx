import React, { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nContext'
import { formatTimestamp } from '../utils/datetime'

/**
 * Post-trip review UI for the FarmPool / shared-logistics trust layer.
 *
 * Renders only for a DELIVERED trip. Covers three review types, matching
 * the backend contract in routers/trip_reviews.py exactly:
 *   TRANSPORTER -- always available
 *   JOURNEY     -- always available
 *   FPO         -- only when the trip carries a pool_id
 *
 * Eligibility is ALWAYS decided server-side. This component hides options
 * the farmer has already used purely as a UX nicety; a duplicate that slips
 * through is still rejected by the backend (409) and surfaced as an error.
 * Ratings and counts shown here come from stored rows only -- never faked.
 */

const STAR_VALUES = [1, 2, 3, 4, 5]

function StarRow({ label, value, onChange, disabled }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <span className="text-sm text-ink/70 dark:text-paper/70">{label}</span>
      <div className="flex gap-0.5">
        {STAR_VALUES.map((v) => (
          <button
            key={v}
            type="button"
            disabled={disabled}
            onClick={() => onChange(v)}
            aria-label={`${label}: ${v}`}
            className={`text-lg leading-none transition-transform ${
              disabled ? 'cursor-default' : 'hover:scale-110'
            } ${v <= (value || 0) ? 'text-marigold' : 'text-black/20 dark:text-white/20'}`}
          >
            ★
          </button>
        ))}
      </div>
    </div>
  )
}

const ASPECTS = {
  TRANSPORTER: [
    { key: 'punctuality', labelKey: 'tripReview.punctuality' },
    { key: 'communication', labelKey: 'tripReview.communication' },
    { key: 'handling', labelKey: 'tripReview.handling' },
  ],
  JOURNEY: [
    { key: 'coordination', labelKey: 'tripReview.coordination' },
    { key: 'punctuality', labelKey: 'tripReview.punctuality' },
  ],
  FPO: [
    { key: 'coordination', labelKey: 'tripReview.coordination' },
    { key: 'communication', labelKey: 'tripReview.communication' },
  ],
}

const TITLE_KEYS = {
  TRANSPORTER: 'tripReview.rateTransporter',
  JOURNEY: 'tripReview.rateJourney',
  FPO: 'tripReview.rateFpo',
}

function ReviewForm({ trip, reviewType, onSubmitted }) {
  const { t } = useI18n()
  const [overall, setOverall] = useState(0)
  const [aspects, setAspects] = useState({})
  const [comment, setComment] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    setError('')
    setSubmitting(true)
    try {
      // Send only fields the backend accepts. `verified` is never sent --
      // the server sets it after proving eligibility.
      const payload = {
        transport_request_id: trip.id,
        review_type: reviewType,
        rating: overall,
        comment: comment.trim() || undefined,
        ...aspects,
      }
      if (reviewType === 'FPO' && trip.pool_id) payload.pool_id = trip.pool_id
      const saved = await api.submitTripReview(payload)
      onSubmitted(saved)
    } catch (e) {
      setError(e?.message || t('tripReview.submitFailed'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="border border-black/5 dark:border-white/10 rounded-xl p-4 bg-paper/40 dark:bg-white/5">
      <p className="font-semibold text-sm mb-2">{t(TITLE_KEYS[reviewType])}</p>

      <StarRow
        label={t('tripReview.overall')}
        value={overall}
        onChange={setOverall}
        disabled={submitting}
      />
      {ASPECTS[reviewType].map((a) => (
        <StarRow
          key={a.key}
          label={t(a.labelKey)}
          value={aspects[a.key]}
          onChange={(v) => setAspects((prev) => ({ ...prev, [a.key]: v }))}
          disabled={submitting}
        />
      ))}

      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        disabled={submitting}
        rows={2}
        placeholder={t('tripReview.comment')}
        className="w-full mt-2 border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper"
      />

      {error && <p className="text-xs text-red-500 mt-2">{error}</p>}

      <button
        type="button"
        onClick={submit}
        disabled={submitting || !overall}
        className="mt-3 bg-forest text-paper px-4 py-2 rounded-lg text-xs font-semibold hover:bg-forest/90 disabled:opacity-50"
      >
        {submitting ? t('tripReview.submitting') : t('tripReview.submit')}
      </button>
    </div>
  )
}

export default function TripReviewSection({ trip }) {
  const { t } = useI18n()
  const [submittedTypes, setSubmittedTypes] = useState([])
  const [myReviews, setMyReviews] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  const isDelivered = trip?.status === 'DELIVERED'

  useEffect(() => {
    if (!isDelivered) { setLoading(false); return }
    let cancelled = false
    setLoading(true)
    Promise.all([
      api.myTripReviews(trip.id).catch(() => ({ submitted_types: [], reviews: [] })),
      api.tripReviewsForTrip(trip.id).catch(() => null),
    ])
      .then(([mine, all]) => {
        if (cancelled) return
        setSubmittedTypes(mine?.submitted_types || [])
        setMyReviews(mine?.reviews || [])
        setSummary(all?.summary || null)
      })
      .catch(() => { if (!cancelled) setLoadError(t('tripReview.submitFailed')) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [trip?.id, isDelivered])

  // A trip that hasn't finished is simply not reviewable -- render nothing
  // rather than showing a disabled shell.
  if (!isDelivered) return null

  const availableTypes = ['TRANSPORTER', 'JOURNEY']
  if (trip.pool_id) availableTypes.push('FPO')
  const pending = availableTypes.filter((tp) => !submittedTypes.includes(tp))

  function handleSubmitted(saved) {
    setSubmittedTypes((prev) => [...prev, saved.review_type])
    setMyReviews((prev) => [...prev, saved])
    api.tripReviewsForTrip(trip.id).then((d) => setSummary(d?.summary || null)).catch(() => {})
  }

  return (
    <div className="mt-4 pt-4 border-t border-black/5 dark:border-white/10">
      <p className="text-xs font-bold uppercase tracking-wide text-ink/50 dark:text-paper/50 mb-2">
        {t('tripReview.sectionTitle')}
      </p>

      {loading && (
        <p className="text-xs text-ink/50 dark:text-paper/50">{t('tripReview.loading')}</p>
      )}
      {loadError && <p className="text-xs text-red-500">{loadError}</p>}

      {!loading && (
        <>
          {/* Aggregates, shown only when real reviews exist. */}
          {summary && availableTypes.some((tp) => summary[tp]?.count > 0) && (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-3">
              {availableTypes.map((tp) => {
                const s = summary[tp]
                if (!s?.count) return null
                return (
                  <div key={tp} className="bg-white dark:bg-white/5 rounded-lg px-3 py-2 border border-black/5 dark:border-white/10">
                    <p className="text-[11px] text-ink/50 dark:text-paper/50">{t(TITLE_KEYS[tp])}</p>
                    <p className="font-bold text-sm">
                      ★ {s.overall}
                      <span className="font-normal text-[11px] text-ink/50 dark:text-paper/50 ml-1">
                        · {s.verified_count ?? s.count} {t('tripReview.verifiedReviews')}
                      </span>
                    </p>
                  </div>
                )
              })}
            </div>
          )}

          {/* Already-submitted reviews, with server timestamps. */}
          {myReviews.map((r) => (
            <div key={r.id} className="flex items-center justify-between gap-2 text-xs py-1">
              <span className="text-ink/70 dark:text-paper/70">
                {t(TITLE_KEYS[r.review_type])} · ★ {r.rating}
              </span>
              {formatTimestamp(r.created_at) && (
                <span className="text-ink/40 dark:text-paper/40">
                  {t('tripReview.reviewSubmittedAt')}: {formatTimestamp(r.created_at)}
                </span>
              )}
            </div>
          ))}

          {pending.length > 0 ? (
            <div className="space-y-3 mt-2">
              <p className="text-sm font-semibold">{t('tripReview.title')}</p>
              {pending.map((tp) => (
                <ReviewForm
                  key={tp}
                  trip={trip}
                  reviewType={tp}
                  onSubmitted={handleSubmitted}
                />
              ))}
            </div>
          ) : (
            <p className="text-xs text-forest dark:text-forest-light mt-1">
              {t('tripReview.thanks')}
            </p>
          )}
        </>
      )}
    </div>
  )
}
