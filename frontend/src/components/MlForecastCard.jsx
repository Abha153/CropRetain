import React from 'react'
import { Link } from 'react-router-dom'
import { Info, AlertTriangle, ArrowRight, Cpu } from 'lucide-react'
import Badge from './Badge'
import { useI18n } from '../i18n/I18nContext'

/**
 * 7-day ML price forecast for the farmer dashboard.
 *
 * It only DISPLAYS what GET /forecast/ml(/compare) returns. When the backend
 * answers `available: false` the card says WHY (unsupported crop, ML libraries
 * not installed, no live history, ...) and shows no number. Replayed historical
 * data is shown only under an explicit "not a prediction for next week" banner.
 * Nothing is ever estimated here. `status` is GET /forecast/ml/status, used for
 * the model line so anyone can verify what is actually running.
 */
const fmt = (n) => Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })
const KNOWN_REASONS = ['unsupported_crop', 'ml_dependencies_missing', 'artifacts_missing',
  'insufficient_history', 'stale_history', 'unknown_market', 'request_failed']

export default function MlForecastCard({ forecast, status, crop, market, loading }) {
  const { t } = useI18n()
  const shell = 'bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5 md:p-6'
  const replay = !!forecast?.available && !!forecast.is_historical_replay

  // Backend warning codes -> readable text (unknown codes are shown as sent).
  const warningText = (w) => {
    if (w === 'model_did_not_beat_persistence_baseline_on_test_split') return t('dashboard.mlForecast.warn.baseline')
    const age = /^historical_replay.*?(\d+)\s*days old/.exec(w)
    if (age) return t('dashboard.mlForecast.warn.replayAge', { days: age[1] })
    return w
  }

  const reason = forecast?.reason
  const reasonText = KNOWN_REASONS.includes(reason)
    ? t(`dashboard.mlForecast.reason.${reason}`, { crop: crop || '' })
    : t('dashboard.mlForecast.unavailableNote')

  return (
    <div className={shell} data-testid="ml-forecast-card">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
        <h2 className="font-display font-semibold text-lg">
          {t('dashboard.mlForecast.title')}{crop && market ? ` · ${crop}, ${market}` : ''}
        </h2>
        {forecast?.available && (
          <Badge tone={replay ? 'warning' : 'success'}>
            {replay ? t('dashboard.mlForecast.replay') : t('dashboard.mlForecast.live')}
          </Badge>
        )}
      </div>

      {loading ? (
        <p className="text-sm text-ink/40 dark:text-paper/40 py-6 text-center">{t('common.loading')}</p>
      ) : !forecast || !forecast.available ? (
        <div className="mt-3 flex items-start gap-2 text-sm bg-wheat/50 dark:bg-white/5 rounded-xl px-4 py-3" data-testid="ml-unavailable">
          <Info size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          <div>
            <div className="font-semibold">{t('dashboard.mlForecast.unavailable')}</div>
            <div className="text-ink/70 dark:text-paper/70 mt-0.5">{reasonText}</div>
            {reason === 'unsupported_crop' && status?.crops?.length > 0 && (
              <div className="text-xs text-ink/50 dark:text-paper/50 mt-1">
                {t('dashboard.mlForecast.covers', { crops: status.crops.join(', ') })}
              </div>
            )}
          </div>
        </div>
      ) : (
        <>
          {replay && (
            <div className="mt-3 flex items-start gap-2 text-sm bg-amber-50 dark:bg-amber-500/10 text-amber-900 dark:text-amber-200 rounded-xl px-4 py-3" data-testid="ml-replay-banner">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
              <span>{t('dashboard.mlForecast.replayBanner', { asOf: forecast.forecast.as_of_date })}</span>
            </div>
          )}
          <div className={`grid sm:grid-cols-2 gap-x-8 gap-y-4 mt-3 ${replay ? 'opacity-70' : ''}`}>
            <div>
              <div className="text-xs text-ink/50 dark:text-paper/50">
                {t('dashboard.mlForecast.predicted', { date: forecast.forecast.target_date })}
              </div>
              <div className="font-display font-mono-data text-3xl font-bold">
                ₹{fmt(forecast.forecast.predicted_price_per_kg)}<span className="text-base font-medium text-ink/50 dark:text-paper/50">/kg</span>
              </div>
            </div>
            <div>
              <div className="text-xs text-ink/50 dark:text-paper/50">{t('dashboard.mlForecast.range')}</div>
              <div className="font-mono-data text-lg font-semibold">
                ₹{fmt(forecast.forecast.predicted_price_low / 100)}–{fmt(forecast.forecast.predicted_price_high / 100)}/kg
              </div>
            </div>
          </div>
          {forecast.forecast.warnings?.length > 0 && (
            <ul className="text-xs text-amber-800 dark:text-amber-300 mt-3 space-y-1">
              {forecast.forecast.warnings.map((w) => (
                <li key={w} className="flex items-start gap-1.5">
                  <AlertTriangle size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
                  <span>{warningText(w)}</span>
                </li>
              ))}
            </ul>
          )}
          {forecast.model?.test_mae_inr_per_quintal != null && (
            <p className="text-xs text-ink/50 dark:text-paper/50 mt-3">
              {t('dashboard.mlForecast.error', { mae: fmt(forecast.model.test_mae_inr_per_quintal) })}
            </p>
          )}
          <p className="text-[11px] text-ink/40 dark:text-paper/40 mt-1">{t('dashboard.mlForecast.caution')}</p>
        </>
      )}

      {/* Verifiable model line: what is actually running on THIS server */}
      <p className="flex items-start gap-1.5 text-[11px] text-ink/50 dark:text-paper/50 mt-3" data-testid="ml-model-line">
        <Cpu size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
        <span>
          {status?.available
            ? t('dashboard.mlForecast.modelLine', { label: status.model_label, days: status.horizon_days, until: status.data_date_range?.[1] || '—' })
            : t('dashboard.mlForecast.statusDown', { reason: status?.reason || 'unreachable' })}
        </span>
      </p>

      <Link to="/forecast" className="inline-flex items-center gap-1 text-sm font-semibold text-forest dark:text-forest-light hover:underline mt-3">
        {t('dashboard.mlForecast.fullForecast')} <ArrowRight size={14} />
      </Link>
    </div>
  )
}
