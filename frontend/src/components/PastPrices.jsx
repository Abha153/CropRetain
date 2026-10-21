import React, { useEffect, useMemo, useState } from 'react'
import { TrendingUp, TrendingDown, Minus, AlertTriangle } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceArea } from 'recharts'
import { api } from '../api/client'
import { useTheme } from '../context/ThemeContext'
import LoadingSpinner from './LoadingSpinner'

/*
 * "Past prices": what this crop actually sold for in this market, as recorded. Read from
 * /market/past-prices (bundled recorded history + any live rows). Nothing is estimated here: a stretch
 * with no record is drawn as a gap. Copy is local English, like the other ML panels, so it does not
 * disturb the locale parity check.
 */

const PAL = {
  light: { line: '#3A4BB0', axis: 'rgba(27,33,64,0.65)', grid: 'rgba(27,33,90,0.08)', surface: '#FFFFFF', ink: '#1B2140', gap: 'rgba(27,33,90,0.06)' },
  dark: { line: '#7686F0', axis: 'rgba(238,240,251,0.7)', grid: 'rgba(238,240,251,0.1)', surface: '#151B3A', ink: '#EEF0FB', gap: 'rgba(238,240,251,0.07)' },
}

const RANGES = [
  { value: 90, label: '3 months' },
  { value: 365, label: '1 year' },
  { value: 730, label: '2 years' },
  { value: 0, label: 'All' },
]

const DAY = 86400000
const ts = d => new Date(`${d}T00:00:00Z`).getTime()
const kg = q => q / 100
const money = q => `₹${kg(q).toLocaleString('en-IN', { maximumFractionDigits: 1, minimumFractionDigits: kg(q) < 10 ? 1 : 0 })}`
const fmtDate = (d, opts) => new Date(`${d}T00:00:00Z`).toLocaleDateString('en-IN', { timeZone: 'UTC', ...(opts || { day: 'numeric', month: 'short', year: 'numeric' }) })
const sourceName = s => ({ history: 'Recorded mandi history', snapshot: 'Mandi snapshot', live: 'Live mandi data', state_average: 'Statewide average' }[s] || s)

function ageText(days) {
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 60) return `${days} days ago`
  if (days < 700) return `${Math.round(days / 30)} months ago`
  return `${(days / 365).toFixed(1)} years ago`
}

function Segmented({ value, onChange, options, label }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg border border-black/10 p-0.5 text-xs bg-white dark:bg-transparent">
      {options.map(o => (
        <button key={o.value} type="button" onClick={() => onChange(o.value)} aria-pressed={value === o.value}
          className={`px-3 py-1.5 rounded-md font-semibold transition-colors ${value === o.value ? 'bg-forest text-paper' : 'text-ink/60 hover:text-ink'}`}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

function Tile({ label, value, sub }) {
  return (
    <div className="rounded-xl border border-black/10 p-3">
      <div className="text-xs font-semibold text-ink/60">{label}</div>
      <div className="text-xl font-semibold tabular-nums mt-0.5">{value}</div>
      {sub && <div className="text-xs text-ink/60 mt-0.5">{sub}</div>}
    </div>
  )
}

/** Statewide next-week outlook from the state-level model, with its measured accuracy beside it. */
function StateOutlook({ crop, state }) {
  const [d, setD] = useState(null)
  useEffect(() => {
    let live = true
    setD(null)
    api.getMlStateForecast(crop, state).then(r => { if (live) setD(r) }).catch(() => { if (live) setD(null) })
    return () => { live = false }
  }, [crop, state])
  if (!d?.available) return null
  const f = d.forecast, m = d.model
  const change = (f.predicted_price - f.last_observed_price) / f.last_observed_price * 100
  const word = Math.abs(change) < 2 ? 'about the same' : change > 0 ? 'higher' : 'lower'
  const Icon = Math.abs(change) < 2 ? Minus : change > 0 ? TrendingUp : TrendingDown
  const cls = Math.abs(change) < 2 ? 'text-ink/70' : change > 0 ? 'text-gain' : 'text-loss'
  const crp = m.this_crop_test
  const better = crp ? (1 - crp.model_mae / crp.persistence_mae) * 100 : null
  return (
    <div className="rounded-xl border border-black/10 p-4 mb-3">
      <h3 className="text-sm font-semibold">Next week, {state} average (a forecast)</h3>
      <p className={`text-lg font-semibold flex items-start gap-2 mt-1 ${cls}`}>
        <Icon size={20} className="mt-0.5 shrink-0" aria-hidden="true" />
        <span>Around {money(f.predicted_price)} per kg by {fmtDate(f.target_date, { day: 'numeric', month: 'short' })}
          <span className="font-normal text-ink/70"> — {Math.abs(change) < 2 ? 'about the same as' : `${Math.abs(change).toFixed(0)}% ${word} than`} {money(f.last_observed_price)} on {fmtDate(f.as_of_date, { day: 'numeric', month: 'short' })}</span>
        </span>
      </p>
      <p className="text-sm text-ink/70 mt-1">Likely range {money(f.predicted_price_low)} to {money(f.predicted_price_high)}. Based on prices up to {fmtDate(f.as_of_date)}{d.data_age_days > 3 ? ` (${d.data_age_days} days old)` : ''}.</p>
      <p className="text-xs text-ink/60 mt-2 max-w-[80ch]">
        How reliable: on months it had never seen, its average miss was ₹{Math.round(crp ? crp.model_mae : m.test_mae_inr_per_quintal)} per quintal{crp ? ` for ${crop}` : ''}.
        {better != null && <> That was {better.toFixed(0)}% smaller than simply assuming the price stays the same.</>}
        {' '}It is about level with a 7-day average (₹{Math.round(m.ma7_baseline_test_mae)}), and the range held the real price {Math.round((m.interval_coverage_test || 0) * 100)}% of the time (aimed for 80%).
        A statistical guess from past prices, not a promise; weather and sudden supply changes are not in it.
      </p>
    </div>
  )
}

function National({ rows }) {
  const latest = rows.find(r => r.label === 'Latest')
  if (!latest) return null
  const earlier = ['1 week earlier', '1 month earlier', '1 year earlier', '2 years earlier', '3 years earlier']
    .map(l => rows.find(r => r.label === l)).filter(Boolean)
  return (
    <div className="mt-5">
      <h3 className="text-sm font-semibold">All-India price on {fmtDate(latest.date, { day: 'numeric', month: 'short' })}, and the same date in earlier years</h3>
      <p className="text-xs text-ink/60 mt-0.5">National wholesale average, not this state or market. Shown per kg.</p>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 mt-2">
        <Tile label="Latest" value={money(latest.modal)} sub={fmtDate(latest.date, { day: 'numeric', month: 'short', year: 'numeric' })} />
        {earlier.map(r => {
          const pct = (latest.modal - r.modal) / r.modal * 100
          return <Tile key={r.date} label={r.label[0].toUpperCase() + r.label.slice(1)} value={money(r.modal)}
            sub={`${fmtDate(r.date, { day: 'numeric', month: 'short', year: '2-digit' })} · now ${pct >= 0 ? '+' : '−'}${Math.abs(pct).toFixed(0)}%`} />
        })}
      </div>
    </div>
  )
}

function Trend({ s }) {
  const t = s.trend
  if (t.direction === 'unknown' || t.change_pct == null) {
    return (
      <p className="text-sm text-ink/70 flex items-start gap-1.5">
        <Minus size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
        <span>Not enough recent prices to call a trend (only {t.n_points} recorded{t.after_gap ? ' since the gap' : ''}).</span>
      </p>
    )
  }
  const Icon = t.direction === 'rising' ? TrendingUp : t.direction === 'falling' ? TrendingDown : Minus
  const cls = t.direction === 'rising' ? 'text-gain' : t.direction === 'falling' ? 'text-loss' : 'text-ink/70'
  const word = { rising: 'Going up', falling: 'Going down', steady: 'Staying about the same' }[t.direction]
  const span = `${fmtDate(t.from_date, { day: 'numeric', month: 'short', year: 'numeric' })} to ${fmtDate(t.to_date, { day: 'numeric', month: 'short', year: 'numeric' })}`
  const detail = t.direction === 'steady' ? `within ${Math.abs(t.change_pct).toFixed(1)}%` : `${t.change_pct > 0 ? 'rose' : 'fell'} ${Math.abs(t.change_pct).toFixed(0)}%`
  return (
    <p className={`text-lg font-semibold flex items-start gap-2 ${cls}`}>
      <Icon size={20} className="mt-0.5 shrink-0" aria-hidden="true" />
      <span>{word}<span className="font-normal text-ink/70"> — {detail}, {span}</span></span>
    </p>
  )
}

/** Points -> chart rows; a null row is inserted inside each gap so the line breaks instead of bridging it. */
function toRows(points, gaps) {
  const rows = []
  const gapAfter = new Map(gaps.map(g => [g.from, g]))
  points.forEach(p => {
    rows.push({ t: ts(p.date), kg: kg(p.modal), date: p.date, source: p.source })
    const g = gapAfter.get(p.date)
    if (g) rows.push({ t: Math.round((ts(g.from) + ts(g.to)) / 2), kg: null })
  })
  return rows
}

function Chart({ rows, gaps, c }) {
  const real = rows.filter(r => r.kg != null)
  const lo = Math.min(...real.map(r => r.kg)), hi = Math.max(...real.map(r => r.kg))
  const pad = Math.max((hi - lo) * 0.15, hi * 0.03, 0.5)
  const widest = gaps.reduce((a, g) => (!a || g.days > a.days ? g : a), null)
  const t0 = rows[0].t, t1 = rows[rows.length - 1].t
  const span = Math.max(t1 - t0, DAY)
  const tickFmt = v => fmtDate(new Date(v).toISOString().slice(0, 10), span > 200 * DAY ? { month: 'short', year: '2-digit' } : { day: 'numeric', month: 'short' })
  // Show a dot where a point is isolated (single record, or next to a gap) or the series is short.
  const dot = props => {
    const { cx, cy, index, payload } = props
    if (payload.kg == null || cx == null) return <g key={index} />
    const prev = rows[index - 1], next = rows[index + 1]
    const isolated = !prev || prev.kg == null || !next || next.kg == null
    if (real.length > 45 && !isolated) return <g key={index} />
    return <circle key={index} cx={cx} cy={cy} r={3.5} fill={c.line} stroke={c.surface} strokeWidth={1.5} />
  }
  return (
    <div style={{ width: '100%', height: 280 }}>
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={c.grid} vertical={false} />
          {gaps.map(g => <ReferenceArea key={g.from} x1={ts(g.from)} x2={ts(g.to)} fill={c.gap} strokeOpacity={0}
            label={g === widest ? { value: 'No records', position: 'insideTop', fill: c.axis, fontSize: 11 } : undefined} />)}
          <XAxis dataKey="t" type="number" scale="time" domain={[t0 - (real.length === 1 ? 10 * DAY : 0), t1 + (real.length === 1 ? 10 * DAY : 0)]}
            tickFormatter={tickFmt} tick={{ fill: c.axis, fontSize: 11 }} stroke={c.grid} tickCount={6} minTickGap={24} />
          <YAxis domain={[Math.max(0, Math.floor(lo - pad)), Math.ceil(hi + pad)]} tick={{ fill: c.axis, fontSize: 11 }} stroke={c.grid}
            tickFormatter={v => `₹${v}`} width={48} allowDecimals={false} />
          <Tooltip content={({ active, payload }) => {
            const p = active && payload?.[0]?.payload
            if (!p || p.kg == null) return null
            return (
              <div className="rounded-lg px-3 py-2 text-xs shadow-lifted border" style={{ background: c.surface, borderColor: c.grid, color: c.ink }}>
                <div className="font-semibold mb-0.5">{fmtDate(p.date)}</div>
                <div><strong className="tabular-nums">{money(p.kg * 100)}</strong> per kg</div>
                <div className="opacity-70">{sourceName(p.source)}</div>
              </div>
            )
          }} />
          <Line type="monotone" dataKey="kg" name="Price per kg" stroke={c.line} strokeWidth={2} dot={dot} activeDot={{ r: 5 }}
            connectNulls={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function PastPrices({ crop, market, cropLabel }) {
  const { theme } = useTheme()
  const c = PAL[theme === 'dark' ? 'dark' : 'light']
  const [days, setDays] = useState(365)
  const [scope, setScope] = useState('auto')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [asTable, setAsTable] = useState(false)

  useEffect(() => {
    if (!crop || !market) return undefined
    let live = true
    setLoading(true); setError(false)
    api.getPastPrices(crop, market, days || null, scope)
      .then(d => { if (live) setData(d) })
      .catch(() => { if (live) { setData(null); setError(true) } })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [crop, market, days, scope])

  // A new crop or market starts from the default view again.
  useEffect(() => { setScope('auto') }, [crop, market])

  const rows = useMemo(() => (data?.available ? toRows(data.points, data.gaps) : []), [data])
  const name = cropLabel || crop
  const where = data?.scope === 'state' ? `${data.state} (statewide average)` : market

  return (
    <section className="mb-10" aria-labelledby="past-prices-h">
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2 mb-3">
        <div className="max-w-[70ch]">
          <h2 id="past-prices-h" className="text-lg font-semibold">Past prices</h2>
          <p className="text-sm text-ink/60 mt-0.5">
            {data?.available && data.scope === 'state'
              ? <>What {name} sold for across {data.state}: one price per day, averaged over all its mandis by how much arrived.</>
              : <>What {name} sold for in {market}, from recorded mandi prices.</>}
          </p>
        </div>
        <Segmented value={days} onChange={setDays} options={RANGES} label="Time range" />
      </div>

      {data?.available && data.scopes_available.length > 1 && (
        <div className="mb-3">
          <Segmented value={data.scope} onChange={setScope} label="Which prices"
            options={[{ value: 'state', label: `${data.state} average` }, { value: 'market', label: `${market} only` }]} />
        </div>
      )}

      {loading && !data && <LoadingSpinner />}
      {error && <p className="text-sm text-ink/70 flex items-center gap-2"><AlertTriangle size={14} aria-hidden="true" /> Past prices could not be loaded. Try again in a moment.</p>}

      {data && !data.available && (
        <div className="rounded-xl border border-black/10 p-4 text-sm text-ink/70">
          No recorded prices for {name} in {market} yet. Try another market, or check back after the next live mandi sync.
        </div>
      )}

      {data?.available && (() => {
        const s = data.summary
        const latest = s.latest
        const stale = latest.age_days > 30
        return (
          <div className={loading ? 'opacity-60 transition-opacity' : 'transition-opacity'}>
            <div className="rounded-xl border border-black/10 p-4 mb-3">
              <p className="text-sm text-ink/70">
                {s.latest.source === 'state_average' ? `${data.state} average` : 'Last recorded price'}: <strong className="text-ink">{money(latest.modal)} per kg</strong> on {fmtDate(latest.date)} ({ageText(latest.age_days)}).
                {data.scope === 'market' && latest.min != null && latest.max != null && <> That day it ranged from {money(latest.min)} to {money(latest.max)}.</>}
              </p>
              <div className="mt-2"><Trend s={s} /></div>
              {latest.note && <p className="text-xs text-ink/60 mt-2">The latest price comes from {latest.note}.</p>}
            </div>

            {data.scope === 'state' && data.state && <StateOutlook crop={crop} state={data.state} />}

            {stale && (
              <div className="text-xs text-ink/70 mb-3 flex items-start gap-2 max-w-[80ch]">
                <AlertTriangle size={14} className="mt-0.5 shrink-0 text-marigold-dark" aria-hidden="true" />
                <span>The newest record here is {ageText(latest.age_days)}. Prices from after that are not in the data yet, so this is not today&apos;s rate. Time ranges count back from the newest record.</span>
              </div>
            )}

            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
              <Tile label="Latest" value={money(latest.modal)} sub={fmtDate(latest.date, { day: 'numeric', month: 'short' })} />
              <Tile label="Highest" value={money(s.high.modal)} sub={fmtDate(s.high.date, { day: 'numeric', month: 'short', year: '2-digit' })} />
              <Tile label="Lowest" value={money(s.low.modal)} sub={fmtDate(s.low.date, { day: 'numeric', month: 'short', year: '2-digit' })} />
              <Tile label="Average" value={money(s.average)} sub={`${s.n_points} recorded ${s.n_points === 1 ? 'day' : 'days'}`} />
            </div>

            {asTable ? (
              <div className="overflow-x-auto max-h-80 overflow-y-auto">
                <table className="w-full text-xs border-collapse">
                  <caption className="sr-only">Recorded prices for {name}: {where}</caption>
                  <thead>
                    <tr className="text-left text-ink/60">
                      {['Date', '₹ per kg', '₹ per quintal', 'Source'].map(h => <th key={h} scope="col" className="font-semibold py-1.5 pr-4 border-b border-black/10 whitespace-nowrap">{h}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {[...data.points].reverse().map(p => (
                      <tr key={p.date} className="border-b border-black/5">
                        <td className="py-1.5 pr-4 whitespace-nowrap">{fmtDate(p.date)}</td>
                        <td className="py-1.5 pr-4 tabular-nums">{money(p.modal)}</td>
                        <td className="py-1.5 pr-4 tabular-nums">₹{p.modal.toLocaleString('en-IN')}</td>
                        <td className="py-1.5 pr-4">{sourceName(p.source)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div role="img" aria-label={`Line chart of recorded ${name} prices, ${where}, ${s.n_points} days from ${fmtDate(s.first_date)} to ${fmtDate(latest.date)}`}>
                <Chart rows={rows} gaps={data.gaps} c={c} />
              </div>
            )}
            <button type="button" onClick={() => setAsTable(v => !v)} className="mt-2 text-xs font-semibold text-ink underline underline-offset-2">
              {asTable ? 'View as chart' : 'View as table'}
            </button>

            {data.national && <National rows={data.national} />}

            <p className="text-xs text-ink/60 mt-3 max-w-[80ch]">
              Prices are the day&apos;s typical (modal) mandi price, shown per kg. Source: {data.sources.map(sourceName).join(' + ').toLowerCase()} (Agmarknet).
              {data.gaps.length > 0 && ' Shaded stretches have no recorded prices; they are left blank, not estimated.'}
            </p>
          </div>
        )
      })()}
    </section>
  )
}
