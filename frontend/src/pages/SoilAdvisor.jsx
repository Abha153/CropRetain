import React, { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { resolveDefaultLocation } from '../utils/location'
import LoadingSpinner from '../components/LoadingSpinner'
import Badge from '../components/Badge'
import { useI18n } from '../i18n/I18nContext'

/**
 * Soil Advisor -- explainable, cited crop screening linked to the existing
 * market-comparison / net-return logic (all money figures come from the
 * backend's existing net_profit_breakdown; nothing is computed here).
 *
 * Honesty: results are labelled ESTIMATED; price data is LIVE or DEMO per
 * the backend; crops without cited rules are shown as UNAVAILABLE.
 */

const LABEL_TONE = { LIVE: 'success', DEMO: 'warning', ESTIMATED: 'info', UNAVAILABLE: 'neutral' }

const selectCls = 'border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper'
const labelCls = 'text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1'

function LabelBadge({ label, t }) {
  return <Badge tone={LABEL_TONE[label] || 'neutral'}>{t(`soil.label.${label}`)}</Badge>
}

function CheckRow({ check, t, sourceById }) {
  const ok = check.status === 'match'
  return (
    <li className="py-2 border-t border-black/5 dark:border-white/10 first:border-t-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold">{t(`soil.factor.${check.factor}`)}</span>
        <Badge tone={ok ? 'success' : 'warning'}>{ok ? t('soil.match') : t('soil.mismatch')}</Badge>
      </div>
      {check.factor === 'ph' && (
        <ul className="mt-1 space-y-0.5 text-xs text-ink/70 dark:text-paper/70">
          {check.ranges.map((r, i) => (
            <li key={i}>
              {r.within ? '✓' : '✗'}{' '}
              {t('soil.reportedRange', {
                source: sourceById[r.source]?.publisher || r.source, min: r.min, max: r.max,
              })}
            </li>
          ))}
          {check.sources_disagree && (
            <li className="text-amber-700 dark:text-amber-300">{t('soil.sourcesDisagree')}</li>
          )}
        </ul>
      )}
      {check.factor === 'texture' && (
        <p className="mt-1 text-xs text-ink/70 dark:text-paper/70">
          {t('soil.listedIn', { classes: check.listed_classes.map(c => t(`soil.texture.${c}`)).join(', ') })}
          {check.supporting.some(s => s.interpreted) && ` ${t('soil.interpreted')}`}
        </p>
      )}
      {check.factor === 'season' && (
        <p className="mt-1 text-xs text-ink/70 dark:text-paper/70">
          {t('soil.listedIn', { classes: check.listed_seasons.map(s => t(`soil.season.${s}`)).join(', ') })}
        </p>
      )}
    </li>
  )
}

function Financial({ fin, t }) {
  if (!fin || !fin.available) {
    return (
      <div className="mt-3 flex items-center gap-2 text-xs text-ink/60 dark:text-paper/60">
        <LabelBadge label="UNAVAILABLE" t={t} /> {t('soil.financial.unavailable')}
      </div>
    )
  }
  return (
    <div className="mt-3 rounded-xl bg-forest/5 dark:bg-white/5 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2 mb-1">
        <span className="font-semibold">{t('soil.financial.title')}</span>
        <LabelBadge label="ESTIMATED" t={t} />
        <LabelBadge label={fin.price_data_label} t={t} />
      </div>
      <p>{t('soil.financial.line', { market: fin.best_market, distance: fin.distance_km, price: fin.modal_price_per_kg })}</p>
      <p className="font-display text-lg font-bold">{t('soil.financial.net', { net: Math.round(fin.estimated_net_return).toLocaleString('en-IN') })}</p>
      <p className="text-xs text-ink/70 dark:text-paper/70">
        {t('soil.financial.breakdown', {
          gross: Math.round(fin.gross_revenue).toLocaleString('en-IN'),
          transport: Math.round(fin.transport_cost).toLocaleString('en-IN'),
          mandi: Math.round(fin.mandi_charges).toLocaleString('en-IN'),
          handling: Math.round(fin.handling_cost).toLocaleString('en-IN'),
        })}
      </p>
      {fin.gain_vs_nearest_market > 0 && (
        <p className="text-xs text-forest dark:text-forest-light font-semibold">
          {t('soil.financial.gain', { gain: Math.round(fin.gain_vs_nearest_market).toLocaleString('en-IN') })}
        </p>
      )}
    </div>
  )
}

export default function SoilAdvisor() {
  const { user } = useAuth()
  const { t } = useI18n()
  const [options, setOptions] = useState(null)
  const [ph, setPh] = useState('')
  const [texture, setTexture] = useState('')
  const [season, setSeason] = useState('')
  const [irrigation, setIrrigation] = useState('')
  const [quantity, setQuantity] = useState('')
  const [location, setLocation] = useState(() => resolveDefaultLocation(user))
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => { api.getSoilOptions().then(setOptions).catch(() => {}) }, [])
  useEffect(() => { if (user?.location) setLocation(user.location) }, [user])

  async function analyse() {
    setError('')
    if (ph === '' && !texture && !season) {
      setError(t('soil.needInput'))
      return
    }
    const payload = {}
    if (ph !== '') payload.soil_ph = Number(ph)
    if (texture) payload.soil_texture = texture
    if (season) payload.season = season
    if (irrigation) payload.irrigation = irrigation
    if (quantity !== '' && Number(quantity) > 0) {
      payload.quantity_kg = Number(quantity)
      payload.location = location
    }
    setLoading(true)
    try {
      setResult(await api.soilAdvise(payload))
    } catch (e) {
      setResult(null)
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const sourceById = Object.fromEntries((result?.sources || []).map(s => [s.id, s]))

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-bold">{t('soil.title')}</h1>
        <p className="text-sm text-ink/70 dark:text-paper/70">{t('soil.subtitle')}</p>
      </div>

      <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5 mb-6">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className={labelCls}>{t('soil.ph')}</label>
            <input type="number" step="0.1" min="0" max="14" value={ph} onChange={e => setPh(e.target.value)}
              className={`${selectCls} w-24`} />
          </div>
          <div>
            <label className={labelCls}>{t('soil.texture')}</label>
            <select value={texture} onChange={e => setTexture(e.target.value)} className={selectCls}>
              <option value="">{t('soil.skip')}</option>
              {(options?.soil_texture || []).map(c => <option key={c} value={c}>{t(`soil.texture.${c}`)}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls}>{t('soil.season')}</label>
            <select value={season} onChange={e => setSeason(e.target.value)} className={selectCls}>
              <option value="">{t('soil.skip')}</option>
              {(options?.season || []).map(c => <option key={c} value={c}>{t(`soil.season.${c}`)}</option>)}
            </select>
          </div>
          <div>
            <label className={labelCls}>{t('soil.irrigation')}</label>
            <select value={irrigation} onChange={e => setIrrigation(e.target.value)} className={selectCls}>
              <option value="">{t('soil.skip')}</option>
              {(options?.irrigation || []).map(c => <option key={c} value={c}>{t(`soil.irrigation.${c}`)}</option>)}
            </select>
          </div>
        </div>
        <p className="text-xs text-ink/60 dark:text-paper/60 mt-4 mb-2">{t('soil.moneyHint')}</p>
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className={labelCls}>{t('common.quantityKg')}</label>
            <input type="number" min="1" value={quantity} onChange={e => setQuantity(e.target.value)}
              className={`${selectCls} w-28`} />
          </div>
          <div>
            <label className={labelCls}>{t('bestOption.location')}</label>
            <select value={location} onChange={e => setLocation(e.target.value)} className={selectCls}>
              {(options?.locations || []).map(n => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
          <button onClick={analyse} disabled={loading}
            className="bg-forest text-paper px-4 py-2 rounded-lg text-sm font-semibold hover:bg-forest/90 disabled:opacity-60">
            {t('soil.analyse')}
          </button>
        </div>
      </div>

      {loading && <LoadingSpinner />}
      {error && <div className="text-red-500 text-sm mb-4">{error}</div>}

      {!loading && result && (
        <>
          <div className="flex items-center gap-2 mb-4">
            <LabelBadge label={result.data_quality} t={t} />
          </div>

          {result.recommendations.length === 0 && (
            <p className="text-sm mb-4">{t('soil.noneMatched')}</p>
          )}

          <div className="grid md:grid-cols-2 gap-4 mb-6">
            {result.recommendations.map(rec => (
              <div key={rec.crop} className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="font-display text-lg font-bold">{rec.emoji} {rec.crop}</h2>
                  <Badge tone={rec.checks_passed === rec.checks_assessed ? 'success' : 'warning'}>
                    {t('soil.checksMatched', { passed: rec.checks_passed, assessed: rec.checks_assessed })}
                  </Badge>
                </div>
                <ul>
                  {rec.checks.map(c => <CheckRow key={c.factor} check={c} t={t} sourceById={sourceById} />)}
                </ul>
                {rec.not_assessed_factors.length > 0 && (
                  <p className="mt-2 text-xs text-ink/60 dark:text-paper/60">
                    {t('soil.notAssessed', { factors: rec.not_assessed_factors.map(f => t(`soil.factor.${f}`)).join(', ') })}
                  </p>
                )}
                {rec.notes.map(n => (
                  <p key={n.code} className="mt-2 text-xs text-amber-700 dark:text-amber-300">{t(`soil.note.${n.code}`, n.params)}</p>
                ))}
                <Financial fin={rec.financial} t={t} />
              </div>
            ))}
          </div>

          {result.financial_assumptions.length > 0 && (
            <p className="text-xs text-ink/60 dark:text-paper/60 mb-4">{t('soil.assumptions')}</p>
          )}

          {result.unavailable_crops.length > 0 && (
            <div className="mb-6">
              <h3 className="font-semibold text-sm mb-1">{t('soil.unavailableTitle')}</h3>
              <p className="text-xs text-ink/60 dark:text-paper/60 mb-2">{t('soil.unavailableDesc')}</p>
              <div className="flex flex-wrap gap-2">
                {result.unavailable_crops.map(u => (
                  <Badge key={u.crop} tone="neutral">{u.crop}</Badge>
                ))}
              </div>
            </div>
          )}

          <div className="mb-6">
            <h3 className="font-semibold text-sm mb-1">{t('soil.sources')}</h3>
            <ul className="text-xs space-y-1">
              {result.sources.map(s => (
                <li key={s.id}>
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="underline text-forest dark:text-forest-light">{s.title}</a>
                  <span className="text-ink/60 dark:text-paper/60"> — {s.publisher}</span>
                </li>
              ))}
            </ul>
          </div>

          <p className="text-xs text-ink/70 dark:text-paper/70 border-t border-black/10 dark:border-white/10 pt-3">{t('soil.limits')}</p>
        </>
      )}
    </div>
  )
}
