import React, { useEffect, useMemo, useState } from 'react'
import { TrendingUp, TrendingDown, Minus, AlertTriangle, Info } from 'lucide-react'
import { ComposedChart, Line, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine } from 'recharts'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { resolveDefaultLocation } from '../utils/location'
import { useTheme } from '../context/ThemeContext'
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

// ML forecast panel copy. NOTE: kept local (English) on purpose so adding the
// panel does not break the locale key-parity check (npm run i18n:validate)
// while translation batches are in progress. Move into en.json + the other
// locales once the wording is final.
const ML_COPY = {
  heading: 'ML forecast',
  sub: '7 days ahead, trained on historical mandi prices',
  live: 'Live price history',
  replay: 'Historical replay (not live)',
  target: (target, asOf) => `Expected on ${target}, from the price recorded on ${asOf}`,
  range: 'Likely range (about 80%)',
  evidence: 'Error on held-out recent data, all markets (lower is better)',
  model: 'This model',
  naive: 'If price stays the same',
  perQuintal: 'per quintal',
  caution: 'Measured on past data. It cannot see weather, policy or sudden supply shocks.',
  unavailableTitle: 'No ML forecast for this crop and market yet',
  reasons: {
    insufficient_history: 'Needs at least 6 recorded prices in the last 28 days for this market. Prices build up as the app fetches live mandi data.',
    stale_history: 'The latest recorded price is too old to forecast from safely.',
    artifacts_missing: 'The model has not been trained on this server yet.',
    artifacts_invalid: 'The saved model does not match this version of the app. Retrain it.',
    unsupported_crop: 'The model was not trained for this crop.',
    invalid_history: 'The recorded prices could not be used.',
    ml_dependencies_missing: 'The ML packages are not installed on the server.',
  },
  warnings: {
    market_not_in_training_data: 'This market was not in the training data; the forecast uses only its own recent prices.',
    model_did_not_beat_persistence_baseline_on_test_split: 'On test data this model did not beat the “price stays the same” baseline.',
    historical_replay: 'Replay of older data for demonstration.',
  },
}

function warningText(w) {
  const code = String(w).split(':')[0]
  const hit = Object.keys(ML_COPY.warnings).find(k => code.startsWith(k))
  return hit ? ML_COPY.warnings[hit] : null
}

const fmt = (n, d = 2) => (typeof n === 'number' && isFinite(n) ? n.toFixed(d) : '–')

export default function PriceForecast() {
  const { user } = useAuth()
  const { t } = useI18n()
  const { theme } = useTheme()
  const dark = theme === 'dark'
  const c = {
    axis: dark ? 'rgba(238,240,251,0.7)' : 'rgba(27,33,64,0.65)',
    grid: dark ? 'rgba(238,240,251,0.1)' : 'rgba(27,33,90,0.08)',
    history: dark ? '#9AA8FF' : '#27358A',
    forecast: '#EBA91B',
    today: dark ? 'rgba(238,240,251,0.5)' : 'rgba(27,33,64,0.45)',
  }

  const [crops, setCrops] = useState([])
  const [markets, setMarkets] = useState([])
  const [crop, setCrop] = useState('Tomato')
  const [market, setMarket] = useState(() => resolveDefaultLocation(user))
  const [showDemo, setShowDemo] = useState(false)
  const [result, setResult] = useState(null)
  const [ml, setMl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getCrops().then(setCrops)
    api.getMarkets().then(setMarkets)
  }, [])

  async function run(e) {
    e?.preventDefault()
    setLoading(true)
    setError('')
    // ML forecast is additive: if the route is missing or fails, the page still works.
    const mlPromise = api.getMlForecast(crop, market, showDemo).then(setMl).catch(() => setMl(null))
    try {
      const data = await api.getForecast(crop, market, showDemo)
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      await mlPromise
      setLoading(false)
    }
  }

  useEffect(() => { run() }, [showDemo]) // eslint-disable-line

  const ok = result?.available

  // History line + a forecast "cone": the band is zero-width today and widens
  // linearly to the low/high the API gives for day 7 (the API only supplies the
  // day-7 range, so the in-between shape is an illustration of growing uncertainty).
  const { chartData, domain } = useMemo(() => {
    if (!ok) return { chartData: [], domain: ['auto', 'auto'] }
    const hist = result.history.map(h => ({ date: h.date, actual: h.modal_price }))
    const last = hist[hist.length - 1]
    const n = result.forecast_series.length || 1
    const lo7 = result.predicted_price_low
    const hi7 = result.predicted_price_high
    const joined = { ...last, predicted: last.actual, band: [last.actual, last.actual] }
    const future = result.forecast_series.map((f, i) => {
      const k = (i + 1) / n
      return {
        date: f.date,
        predicted: f.predicted_price,
        band: [
          +(last.actual + (lo7 - last.actual) * k).toFixed(2),
          +(last.actual + (hi7 - last.actual) * k).toFixed(2),
        ],
      }
    })
    const data = [...hist.slice(0, -1), joined, ...future]
    const all = data.flatMap(d => [d.actual, d.predicted, ...(d.band || [])]).filter(v => typeof v === 'number')
    const min = Math.min(...all), max = Math.max(...all), pad = (max - min) * 0.1 || 1
    return { chartData: data, domain: [Math.floor(min - pad), Math.ceil(max + pad)] }
  }, [ok, result])

  const current = result?.current_price
  const mid = result?.predicted_price_mid
  const deltaPct = ok && current ? ((mid - current) / current) * 100 : null
  const trend = result?.trend_direction
  const TrendIcon = trend === 'increasing' ? TrendingUp : trend === 'decreasing' ? TrendingDown : Minus
  const trendTone = trend === 'increasing' ? 'text-gain' : trend === 'decreasing' ? 'text-loss' : 'text-ink/60'

  return (
    <div className="max-w-[1180px]">
      {/* Title + one control strip: the question is "which crop, which market" */}
      <header className="mb-6 flex flex-col gap-1">
        <h1 className="font-display text-3xl md:text-4xl font-bold">{t('forecast.title')}</h1>
        <p className="text-ink/60 max-w-[60ch]">{t('forecast.subtitle')}</p>
      </header>

      <form onSubmit={run} className="mb-8 flex flex-col md:flex-row md:items-end gap-3 md:gap-4 border-y border-black/5 py-4">
        <div className="flex-1">
          <label htmlFor="pf-crop" className="text-xs font-semibold text-ink/60 block mb-1">{t('common.crop')}</label>
          <select id="pf-crop" value={crop} onChange={e => setCrop(e.target.value)} className="w-full border border-black/10 rounded-lg px-3 py-2.5 text-sm bg-white">
            {crops.map(cr => <option key={cr.name} value={cr.name}>{cr.emoji} {getLocalizedCropName(cr.name, t)}</option>)}
          </select>
        </div>
        <div className="flex-1">
          <label htmlFor="pf-market" className="text-xs font-semibold text-ink/60 block mb-1">{t('ui.market')}</label>
          <select id="pf-market" value={market} onChange={e => setMarket(e.target.value)} className="w-full border border-black/10 rounded-lg px-3 py-2.5 text-sm bg-white">
            {markets.map(m => <option key={m.name} value={m.name}>{m.name}</option>)}
          </select>
        </div>
        <button disabled={loading} className="bg-forest text-paper font-semibold rounded-lg px-6 py-2.5 hover:bg-forest-dark transition-colors disabled:opacity-60 md:min-w-[160px]">
          {loading ? t('forecast.loading') : t('forecast.getForecast')}
        </button>
        <label className="flex items-start gap-2 text-xs text-ink/60 select-none md:max-w-[240px] md:pb-1 cursor-pointer">
          <input type="checkbox" className="mt-0.5 accent-[#27358A]" checked={showDemo} onChange={e => setShowDemo(e.target.checked)} />
          <span>{t('forecast.demoToggle')}</span>
        </label>
      </form>

      {error && <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 text-sm rounded-lg px-3 py-2 mb-4" role="alert">{error}</div>}
      {loading && <LoadingSpinner label={t('forecast.running')} />}

      {result && !loading && !ok && (
        <div className="bg-wheat/50 border border-black/5 text-ink/60 text-sm rounded-xl px-4 py-4 mb-8 flex items-start gap-2">
          <Info size={16} className="mt-0.5 shrink-0" />
          <div>
            {t('forecast.historyUnavailable')}
            {!showDemo && <div className="mt-2 text-xs text-ink/50">{t('forecast.noHistoryHelp')}</div>}
          </div>
        </div>
      )}

      {ok && !loading && (
        <>
          {result.is_demo && (
            <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 text-amber-800 dark:text-amber-300 text-xs rounded-lg px-4 py-2 mb-6">
              <strong className="font-semibold">{t('forecast.demoSimulationLabel')}</strong> — {result.demo_disclaimer || t('forecast.demoDisclaimerDefault')}
            </div>
          )}

          {/* Headline: today -> day 7, then the chart that explains it */}
          <section className="grid lg:grid-cols-[1fr_300px] gap-x-10 gap-y-6 mb-10">
            <div>
              <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2 mb-4">
                <div>
                  <div className="text-xs text-ink/50">{t('forecast.currentPrice')}</div>
                  <div className="font-display font-mono-data text-3xl font-bold">₹{current}<span className="text-base font-medium text-ink/50">/kg</span></div>
                </div>
                <div>
                  <div className="text-xs text-ink/50">{t('forecast.predicted7Days')}</div>
                  <div className="font-display font-mono-data text-3xl font-bold">
                    ₹{result.predicted_price_low}–{result.predicted_price_high}
                    <span className="text-base font-medium text-ink/50">/kg</span>
                  </div>
                </div>
                {deltaPct !== null && (
                  <div className={`flex items-center gap-1 text-sm font-semibold ${trendTone}`}>
                    <TrendIcon size={18} aria-hidden="true" />
                    {deltaPct > 0 ? '+' : ''}{deltaPct.toFixed(1)}%
                    <span className="font-normal text-ink/50">· {t(`forecast.trendDirection.${trend}`)}</span>
                  </div>
                )}
              </div>

              <div role="img" aria-label={`${t('forecast.title')}: ${current} to ${result.predicted_price_low}–${result.predicted_price_high} rupees per kg`}>
                <ResponsiveContainer width="100%" height={340}>
                  <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke={c.grid} />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: c.axis }} tickLine={false} axisLine={{ stroke: c.grid }}
                      interval={Math.max(Math.floor(chartData.length / 6), 1)} tickFormatter={d => String(d).slice(5)} />
                    <YAxis tick={{ fontSize: 11, fill: c.axis }} tickLine={false} axisLine={false} domain={domain} width={44} tickFormatter={v => `₹${v}`} />
                    <Tooltip content={<ChartTip t={t} dark={dark} />} />
                    <ReferenceLine x={result.history[result.history.length - 1]?.date} stroke={c.today} strokeDasharray="3 4"
                      label={{ value: t('forecast.today'), fontSize: 11, fill: c.axis, position: 'insideTopLeft' }} />
                    <Area type="monotone" dataKey="band" stroke="none" fill={c.forecast} fillOpacity={0.28} isAnimationActive={false} />
                    <Line type="monotone" dataKey="actual" name={t('forecast.historicalPrice')} stroke={c.history} strokeWidth={2.25} dot={false} />
                    <Line type="monotone" dataKey="predicted" name={t('forecast.predictedPrice')} stroke={c.forecast} strokeWidth={2.5} strokeDasharray="6 4" dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink/60 mt-2">
                <span className="inline-flex items-center gap-1.5"><i className="inline-block w-4 h-0.5" style={{ background: c.history }} />{t('forecast.historicalPrice')}</span>
                <span className="inline-flex items-center gap-1.5"><i className="inline-block w-4 h-0.5 border-t-2 border-dashed" style={{ borderColor: c.forecast }} />{t('forecast.predictedPrice')}</span>
                <span className="inline-flex items-center gap-1.5"><i className="inline-block w-4 h-2.5 rounded-sm" style={{ background: c.forecast, opacity: 0.35 }} />{t('forecast.predicted7Days')}</span>
              </div>
            </div>

            {/* Side rail: how far to trust it, and where the data came from */}
            <aside className="lg:border-l lg:border-black/5 lg:pl-8 space-y-6">
              <div>
                <div className="flex items-baseline justify-between mb-2">
                  <span className="text-xs text-ink/50">{t('forecast.confidence')}</span>
                  <span className="font-display font-mono-data text-2xl font-bold">{result.confidence_pct}%</span>
                </div>
                <div className="h-2 rounded-full bg-forest/10 overflow-hidden" role="progressbar" aria-valuenow={result.confidence_pct} aria-valuemin={0} aria-valuemax={100}>
                  <div className="h-full rounded-full bg-marigold" style={{ width: `${Math.min(Math.max(result.confidence_pct, 0), 100)}%` }} />
                </div>
              </div>

              <dl className="text-sm space-y-3">
                <Row label={t('forecast.dataSource')} value={result.is_demo ? t('forecast.demoDataset') : t('forecast.govDataSource')} />
                <Row label={t('forecast.horizon')} value={`${result.methodology.forecast_horizon_days} ${t('forecast.days')}`} />
                <Row label={t('forecast.historyUsed')} value={`${result.methodology.historical_records_used} ${t('forecast.dailyRecords')}`} />
                <Row label={t('forecast.method')} value={result.methodology.model_type} />
                <Row label={t('forecast.machineLearning')} value={result.methodology.is_machine_learning ? t('forecast.yes') : t('forecast.no')} />
              </dl>

              {result.backtested_accuracy ? (
                <div>
                  <div className="text-xs font-semibold mb-2">{t('forecast.backtestedAccuracy', { count: result.backtested_accuracy.backtested_predictions })}</div>
                  <div className="grid grid-cols-3 gap-2">
                    <Stat label="MAE" value={`₹${result.backtested_accuracy.mae}`} />
                    <Stat label="RMSE" value={`₹${result.backtested_accuracy.rmse}`} />
                    <Stat label="MAPE" value={`${result.backtested_accuracy.mape_pct}%`} />
                  </div>
                </div>
              ) : (
                <p className="text-xs text-ink/40">{t('forecast.noBacktestData')}</p>
              )}
            </aside>
          </section>

          <div className="text-xs text-ink/60 mb-10 flex items-start gap-2 max-w-[80ch]">
            <AlertTriangle size={14} className="mt-0.5 shrink-0 text-marigold-dark" aria-hidden="true" /> {t('forecast.rangeDisclaimer')}
          </div>
        </>
      )}

      {!loading && ml && <MlPanel ml={ml} currentKg={ok ? current : null} />}
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-ink/50">{label}</dt>
      <dd className="font-medium text-right">{value}</dd>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="rounded-lg bg-wheat/60 px-2 py-2 text-center">
      <div className="font-display font-mono-data text-base font-bold">{value}</div>
      <div className="text-[11px] text-ink/50">{label}</div>
    </div>
  )
}

function ChartTip({ active, payload, label, t, dark }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload
  const price = row.actual ?? row.predicted
  const isForecast = row.actual === undefined
  return (
    <div className="rounded-lg px-3 py-2 text-xs shadow-lifted border"
      style={{ background: dark ? '#1C2347' : '#fff', borderColor: dark ? 'rgba(220,226,255,0.2)' : 'rgba(27,33,90,0.12)', color: dark ? '#EEF0FB' : '#1B2140' }}>
      <div className="font-semibold mb-0.5">{label}</div>
      <div>{isForecast ? t('forecast.predictedPrice') : t('forecast.historicalPrice')}: <strong>₹{price}/kg</strong></div>
      {isForecast && row.band && <div className="opacity-70">₹{row.band[0]}–{row.band[1]}/kg</div>}
    </div>
  )
}

function MlPanel({ ml, currentKg }) {
  const fc = ml.forecast
  return (
    <section className="border-t border-black/5 pt-8 mb-10" aria-labelledby="ml-heading">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-5">
        <h2 id="ml-heading" className="font-display text-xl font-bold">{ML_COPY.heading}</h2>
        <span className="text-sm text-ink/50">{ML_COPY.sub}</span>
        {ml.available && (
          <span className={`text-xs font-semibold rounded-full px-2.5 py-0.5 ${ml.is_historical_replay ? 'bg-amber-100 text-amber-800' : 'bg-gain/15 text-gain'}`}>
            {ml.is_historical_replay ? ML_COPY.replay : ML_COPY.live}
          </span>
        )}
      </div>

      {!ml.available ? (
        <div className="bg-wheat/50 border border-black/5 rounded-xl px-4 py-4 text-sm flex items-start gap-2 max-w-[80ch]">
          <Info size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          <div>
            <div className="font-semibold">{ML_COPY.unavailableTitle}</div>
            <div className="text-ink/60 mt-1">{ML_COPY.reasons[ml.reason] || ml.message}</div>
          </div>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-x-10 gap-y-6">
          <div>
            <div className="font-display font-mono-data text-4xl font-bold">
              ₹{fmt(fc.predicted_price_per_kg)}<span className="text-base font-medium text-ink/50">/kg</span>
            </div>
            <div className="text-sm text-ink/60 mt-1">{ML_COPY.target(fc.target_date, fc.as_of_date)}</div>
            <div className="text-sm mt-3">
              <span className="text-ink/50">{ML_COPY.range}: </span>
              <strong className="font-mono-data">₹{fmt(fc.predicted_price_low / 100)}–{fmt(fc.predicted_price_high / 100)}/kg</strong>
            </div>
            {currentKg ? (
              <div className="text-xs text-ink/50 mt-1">
                ₹{fmt(fc.predicted_price)} {ML_COPY.perQuintal}
              </div>
            ) : null}
            {fc.warnings?.map(w => {
              const txt = warningText(w)
              return txt ? (
                <div key={w} className="text-xs text-amber-800 dark:text-amber-300 mt-3 flex items-start gap-1.5">
                  <AlertTriangle size={13} className="mt-0.5 shrink-0" aria-hidden="true" /> {txt}
                </div>
              ) : null
            })}
          </div>

          <div>
            <div className="text-xs text-ink/50 mb-3">{ML_COPY.evidence}</div>
            <ErrorBar label={ML_COPY.model} value={ml.model.test_mae_inr_per_quintal} max={Math.max(ml.model.test_mae_inr_per_quintal, ml.model.persistence_baseline_test_mae)} accent />
            <ErrorBar label={ML_COPY.naive} value={ml.model.persistence_baseline_test_mae} max={Math.max(ml.model.test_mae_inr_per_quintal, ml.model.persistence_baseline_test_mae)} />
            <p className="text-xs text-ink/50 mt-3 max-w-[48ch]">{ML_COPY.caution}</p>
          </div>
        </div>
      )}
    </section>
  )
}

function ErrorBar({ label, value, max, accent }) {
  const w = max > 0 ? Math.max((value / max) * 100, 2) : 2
  return (
    <div className="mb-2.5">
      <div className="flex justify-between text-xs mb-1">
        <span>{label}</span>
        <span className="font-mono-data font-semibold">₹{fmt(value)} / quintal</span>
      </div>
      <div className="h-2 rounded-full bg-forest/10 overflow-hidden">
        <div className={`h-full rounded-full ${accent ? 'bg-marigold' : 'bg-forest/40'}`} style={{ width: `${w}%` }} />
      </div>
    </div>
  )
}
