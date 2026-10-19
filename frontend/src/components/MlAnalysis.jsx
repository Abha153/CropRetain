import React, { useEffect, useMemo, useState } from 'react'
import { TrendingUp, TrendingDown, Minus, AlertTriangle, Info } from 'lucide-react'
import {
  BarChart, Bar, LineChart, Line, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, ZAxis,
} from 'recharts'
import { api } from '../api/client'
import { useTheme } from '../context/ThemeContext'
import LoadingSpinner from './LoadingSpinner'

/*
 * "Model analysis" for the ML price forecast.
 *
 * Everything here is read from /forecast/ml/analysis, which the training script precomputed on the
 * held-out TEST split (dates the model never saw). Nothing is estimated in the browser.
 *
 * Copy is kept local (English) on purpose, same as the ML panel in PriceForecast.jsx, so it does not
 * disturb the locale key-parity check (npm run i18n:validate). Move it into en.json + the other
 * locales once the wording is final.
 *
 * Chart colours were run through the data-viz palette validator (lightness band, CVD separation,
 * normal-vision floor) separately for the light and dark surfaces:
 *   light  #3A4BB0 / #E09A00 on #FFFFFF      dark  #7686F0 / #B57F10 on #151B3A
 * Colour follows the entity everywhere: amber = this model, indigo = "price stays the same".
 * Grey is the de-emphasised second baseline (7-day average). Gain/loss colours are only ever used
 * with an icon and a word, never alone.
 */

const PAL = {
  light: { baseline: '#3A4BB0', model: '#E09A00', ma7: '#8A90A8', axis: 'rgba(27,33,64,0.65)', grid: 'rgba(27,33,90,0.08)', surface: '#FFFFFF', ink: '#1B2140', track: 'rgba(27,33,90,0.07)' },
  dark: { baseline: '#7686F0', model: '#B57F10', ma7: '#8E94B0', axis: 'rgba(238,240,251,0.7)', grid: 'rgba(238,240,251,0.1)', surface: '#151B3A', ink: '#EEF0FB', track: 'rgba(238,240,251,0.08)' },
}

const COPY = {
  heading: 'Model analysis',
  sub: 'How the forecast performed on prices it had never seen',
  baselineName: 'Price stays the same',
  ma7Name: '7-day average',
  modelName: 'This model',
  unavailable: 'Model analysis is not available yet',
  reasons: {
    artifacts_missing: 'The model has not been trained on this server yet.',
    artifacts_invalid: 'The saved model does not match this version of the app. Retrain it.',
    analysis_missing: 'The model is trained but its analysis file is missing. Retrain to generate it.',
    analysis_invalid: 'The analysis file could not be read. Retrain to regenerate it.',
    ml_dependencies_missing: 'The ML packages are not installed on the server.',
  },
  limits: 'Measured on past data only. The model cannot see weather, policy changes, transport strikes or sudden supply shocks, and it only covers the crops listed above.',
}

const CALENDAR_FEATURES = ['target_doy', 'target_month']

// ───────────────────────── formatting ─────────────────────────
const inr = (n) => (typeof n === 'number' && isFinite(n) ? `₹${Math.round(n).toLocaleString('en-IN')}` : '–')
const pct = (n, d = 0) => (typeof n === 'number' && isFinite(n) ? `${(n * 100).toFixed(d)}%` : '–')
const num = (n) => (typeof n === 'number' ? n.toLocaleString('en-IN') : '–')
const shortDate = (s) => {
  const d = new Date(`${String(s).slice(0, 10)}T00:00:00`)
  return isNaN(d) ? String(s) : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}
const longDate = (s) => {
  const d = new Date(`${String(s).slice(0, 10)}T00:00:00`)
  return isNaN(d) ? String(s) : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}
const addDay = (s) => {
  const d = new Date(`${String(s).slice(0, 10)}T00:00:00`)
  d.setDate(d.getDate() + 1)
  return d.toISOString().slice(0, 10)
}

/** skill = 1 - model error / baseline error. Positive means the model is better. */
const skillOf = (m, b) => (b > 0 ? 1 - m / b : null)
function skillParts(s) {
  if (s === null || s === undefined) return { Icon: Minus, tone: 'text-ink/60', word: 'not enough data', big: '–' }
  if (s >= 0.005) return { Icon: TrendingUp, tone: 'text-gain', word: 'better', big: `${(s * 100).toFixed(1)}%` }
  if (s <= -0.005) return { Icon: TrendingDown, tone: 'text-loss', word: 'worse', big: `${(-s * 100).toFixed(1)}%` }
  return { Icon: Minus, tone: 'text-ink/60', word: 'about equal', big: '0%' }
}

function verdictFor(a) {
  const t = a.overall.test
  const mae = skillOf(t.model.mae, t.baseline_persistence.mae)
  const rmse = skillOf(t.model.rmse, t.baseline_persistence.rmse)
  const tone = mae >= 0.02 ? 'good' : mae <= -0.02 ? 'bad' : 'even'
  const start = longDate(addDay(a.data.split.val_through_target_date))
  const end = longDate(a.data.date_range[1])
  const lines = []
  lines.push(`Checked on ${num(t.rows)} forecasts made between ${start} and ${end} — prices the model never saw while learning.`)
  lines.push(`Its typical miss was ${inr(t.model.mae)} per quintal, against ${inr(t.baseline_persistence.mae)} if you had simply assumed today's price would hold.`)
  if (rmse !== null && mae !== null && rmse >= 0.02 && mae < 0.02) {
    lines.push(`It handled big price swings better than that rule (${inr(t.model.rmse)} vs ${inr(t.baseline_persistence.rmse)} on large misses) but not everyday moves.`)
  }
  if (tone === 'bad') lines.push('So use it as a range to plan around, not as a sharper guess than today’s price.')
  if (tone === 'good') lines.push('That is a real, measured improvement — still shown as a range, because individual forecasts can miss.')
  return { tone, mae, rmse, lines }
}

// ───────────────────────── small building blocks ─────────────────────────
function Section({ title, hint, children, right }) {
  return (
    <section className="mb-10">
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2 mb-3">
        <div className="max-w-[70ch]">
          <h3 className="text-base font-semibold">{title}</h3>
          {hint && <p className="text-sm text-ink/60 mt-0.5">{hint}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  )
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

/** Every chart has a table twin: tooltips enhance, they never gate the numbers. */
function ChartFrame({ children, table, label, legend }) {
  const [asTable, setAsTable] = useState(false)
  return (
    <div>
      {legend && <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink/70 mb-2" aria-hidden={asTable}>{legend}</div>}
      {asTable ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <caption className="sr-only">{label}</caption>
            <thead>
              <tr className="text-left text-ink/60">
                {table.cols.map(c => <th key={c} scope="col" className="font-semibold py-1.5 pr-4 border-b border-black/10 whitespace-nowrap">{c}</th>)}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((r, i) => (
                <tr key={i} className="border-b border-black/5">
                  {r.map((v, j) => <td key={j} className="py-1.5 pr-4 tabular-nums whitespace-nowrap">{v}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div role="img" aria-label={label}>{children}</div>
      )}
      <button type="button" onClick={() => setAsTable(v => !v)} className="mt-2 text-xs font-semibold text-ink underline underline-offset-2">
        {asTable ? 'View as chart' : 'View as table'}
      </button>
    </div>
  )
}

function Key({ color, label, line, dim }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <i className={`inline-block ${line ? 'w-4 h-0.5' : 'w-3 h-3 rounded-sm'}`} style={{ background: color, opacity: dim ? 0.9 : 1 }} aria-hidden="true" />
      {label}
    </span>
  )
}

function Tip({ active, payload, label, c, fmt, title }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg px-3 py-2 text-xs shadow-lifted border"
      style={{ background: c.surface, borderColor: c.grid, color: c.ink }}>
      <div className="font-semibold mb-1">{title ? title(label, payload) : label}</div>
      {payload.filter(p => p.value !== undefined && p.value !== null).map(p => (
        <div key={p.dataKey} className="flex items-center gap-1.5">
          <i className="inline-block w-2.5 h-2.5 rounded-sm" style={{ background: p.color || p.stroke || p.fill }} aria-hidden="true" />
          <span>{p.name}:</span> <strong className="tabular-nums">{fmt(p.value, p)}</strong>
        </div>
      ))}
    </div>
  )
}

// ───────────────────────── sections ─────────────────────────
function Verdict({ a }) {
  const v = verdictFor(a)
  const sp = skillParts(v.mae)
  const t = a.overall.test
  const cover = t.interval_coverage_80
  const tiles = [
    { label: 'Typical miss', value: inr(t.model.mae), sub: `vs ${inr(t.baseline_persistence.mae)} if price stays the same`, note: 'per quintal, average of the gaps' },
    { label: 'Big misses', value: inr(t.model.rmse), sub: `vs ${inr(t.baseline_persistence.rmse)} if price stays the same`, note: 'per quintal, counts large gaps more' },
    { label: 'Within 10% of the real price', value: pct(a.error_buckets_test.find(b => b.label === 'within 10%')?.model), sub: `vs ${pct(a.error_buckets_test.find(b => b.label === 'within 10%')?.persistence)} if price stays the same`, note: 'share of forecasts' },
    { label: 'Real price inside the range', value: pct(cover, 1), sub: 'the range is built to catch about 80%', note: 'measured on unseen dates' },
  ]
  const border = v.tone === 'bad' ? 'border-amber-300 dark:border-amber-800' : v.tone === 'good' ? 'border-gain/40' : 'border-black/10'
  return (
    <div className={`rounded-2xl border ${border} bg-white/60 dark:bg-white/[0.03] p-5 md:p-6 mb-8`}>
      <div className="grid lg:grid-cols-[minmax(0,260px)_1fr] gap-x-10 gap-y-5 items-start">
        <div>
          <div className="text-xs font-semibold text-ink/60 mb-1">Compared with “price stays the same”</div>
          <div className={`flex items-center gap-2 ${sp.tone}`}>
            <sp.Icon size={30} aria-hidden="true" />
            <span className="text-5xl font-bold tracking-tight">{sp.big}</span>
          </div>
          <div className={`text-sm font-semibold mt-1 ${sp.tone}`}>{sp.word} on typical miss</div>
        </div>
        <div className="text-sm leading-relaxed space-y-2 max-w-[75ch]">
          {v.lines.map((l, i) => <p key={i} className={i === 0 ? 'text-ink/60' : ''}>{l}</p>)}
        </div>
      </div>
      <dl className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-6 pt-5 border-t border-black/5">
        {tiles.map(x => (
          <div key={x.label}>
            <dt className="text-xs text-ink/60">{x.label}</dt>
            <dd className="text-2xl font-bold mt-0.5">{x.value}</dd>
            <dd className="text-xs text-ink/60 mt-0.5">{x.sub}</dd>
            <dd className="text-[11px] text-ink/40">{x.note}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function VsRules({ a, c }) {
  const rows = [
    ['Unseen test data', a.overall.test, 'Not used to choose or tune the model'],
    ['Validation data', a.overall.validation, 'Used to choose the model and size the range'],
  ]
  const max = Math.max(...rows.flatMap(([, m]) => [m.model.mae, m.baseline_persistence.mae, m.baseline_ma7.mae]))
  const series = [
    ['model', COPY.modelName, c.model], ['baseline_persistence', COPY.baselineName, c.baseline], ['baseline_ma7', COPY.ma7Name, c.ma7],
  ]
  const table = {
    cols: ['Data', 'Measure', COPY.modelName, COPY.baselineName, COPY.ma7Name],
    rows: rows.flatMap(([name, m]) => [['mae', 'Typical miss'], ['rmse', 'Big misses'], ['mape', 'Average % off']].map(([k, lab]) =>
      [name, lab, ...series.map(([key]) => (k === 'mape' ? pct(m[key][k], 1) : inr(m[key][k])))])),
  }
  return (
    <ChartFrame label="Typical miss in rupees per quintal for the model and two simple rules, on test and validation data" table={table}
      legend={series.map(([k, l, col]) => <Key key={k} color={col} label={l} />)}>
      <div className="space-y-6">
        {rows.map(([name, m, note]) => (
          <div key={name}>
            <div className="flex flex-wrap items-baseline gap-x-3 mb-2">
              <span className="text-sm font-semibold">{name}</span>
              <span className="text-xs text-ink/50">{note} · {num(m.rows)} forecasts</span>
            </div>
            <div className="space-y-[2px]">
              {series.map(([k, l, col]) => {
                const v = m[k].mae
                return (
                  <div key={k} className="flex items-center gap-3" title={`${l}: ${inr(v)} per quintal`}>
                    <div className="w-36 shrink-0 text-xs text-ink/70 truncate">{l}</div>
                    <div className="flex-1 h-5 rounded-r-[4px]" style={{ background: c.track }}>
                      <div className="h-full" style={{ width: `${Math.max((v / max) * 100, 2)}%`, background: col, borderRadius: '0 4px 4px 0' }} />
                    </div>
                    <div className="w-20 shrink-0 text-xs font-semibold tabular-nums text-right">{inr(v)}</div>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
        <p className="text-xs text-ink/50">Typical miss = average gap between forecast and real price, in ₹ per quintal. Shorter bar is better.</p>
      </div>
    </ChartFrame>
  )
}

function Buckets({ a, c }) {
  const data = a.error_buckets_test.map(b => ({ label: b.label, model: +(b.model * 100).toFixed(1), baseline: +(b.persistence * 100).toFixed(1) }))
  const table = { cols: ['Forecast was…', COPY.modelName, COPY.baselineName], rows: data.map(d => [d.label, `${d.model}%`, `${d.baseline}%`]) }
  return (
    <ChartFrame label="Share of forecasts within 5, 10 and 20 percent of the real price, and share off by more than 20 percent, for the model and for price stays the same" table={table}
      legend={[<Key key="m" color={c.model} label={COPY.modelName} />, <Key key="b" color={c.baseline} label={COPY.baselineName} />]}>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} barGap={2} barCategoryGap="28%" margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={c.grid} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: c.axis }} tickLine={false} axisLine={{ stroke: c.grid }} />
          <YAxis tick={{ fontSize: 11, fill: c.axis }} tickLine={false} axisLine={false} width={40} domain={[0, 100]} tickFormatter={v => `${v}%`} />
          <Tooltip cursor={{ fill: c.track }} content={<Tip c={c} fmt={(v) => `${v}% of forecasts`} />} />
          <Bar dataKey="baseline" name={COPY.baselineName} fill={c.baseline} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          <Bar dataKey="model" name={COPY.modelName} fill={c.model} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}

function Weekly({ a, c, crop }) {
  const keys = Object.keys(a.weekly_test)
  const [sel, setSel] = useState(keys.includes(crop) ? crop : 'All crops')
  const [metric, setMetric] = useState('change')
  useEffect(() => { if (keys.includes(crop)) setSel(crop) }, [crop]) // eslint-disable-line
  const rows = a.weekly_test[sel] || []
  const data = rows.map(r => ({
    week: r.week, actual: +r.actual_change_pct.toFixed(2), predicted: +r.predicted_change_pct.toFixed(2),
    model: +r.model_mae.toFixed(1), baseline: +r.persistence_mae.toFixed(1), rows: r.rows,
  }))
  const isChange = metric === 'change'
  const table = isChange
    ? { cols: ['Week of', 'Forecasts', 'Real average change', 'Model predicted change'], rows: data.map(d => [shortDate(d.week), d.rows, `${d.actual}%`, `${d.predicted}%`]) }
    : { cols: ['Week of', 'Forecasts', 'Model typical miss', 'Price-stays-the-same miss'], rows: data.map(d => [shortDate(d.week), d.rows, inr(d.model), inr(d.baseline)]) }
  const k1 = isChange ? ['actual', 'Real change in price', c.baseline] : ['baseline', COPY.baselineName, c.baseline]
  const k2 = isChange ? ['predicted', 'Change the model predicted', c.model] : ['model', COPY.modelName, c.model]
  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <Segmented label="Crop" value={sel} onChange={setSel} options={keys.map(k => ({ value: k, label: k }))} />
        <Segmented label="What to plot" value={metric} onChange={setMetric}
          options={[{ value: 'change', label: 'Price change' }, { value: 'error', label: 'Typical miss' }]} />
      </div>
      <ChartFrame label={isChange ? `Each week, the average real price change over the following 7 days against the change the model predicted, for ${sel}` : `Each week, the model's typical miss against price stays the same, for ${sel}`}
        table={table} legend={[<Key key="a" line color={k1[2]} label={k1[1]} />, <Key key="b" line color={k2[2]} label={k2[1]} />]}>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={c.grid} />
            <XAxis dataKey="week" tick={{ fontSize: 11, fill: c.axis }} tickLine={false} axisLine={{ stroke: c.grid }}
              tickFormatter={shortDate} interval={Math.max(Math.floor(data.length / 6), 0)} />
            <YAxis tick={{ fontSize: 11, fill: c.axis }} tickLine={false} axisLine={false} width={isChange ? 44 : 52}
              tickFormatter={v => (isChange ? `${v}%` : inr(v))} />
            {isChange && <ReferenceLine y={0} stroke={c.axis} strokeWidth={1} />}
            <Tooltip cursor={{ stroke: c.grid, strokeWidth: 1 }}
              content={<Tip c={c} title={(l) => `Week of ${shortDate(l)}`} fmt={(v) => (isChange ? `${v > 0 ? '+' : ''}${v}%` : `${inr(v)} / quintal`)} />} />
            <Line type="monotone" dataKey={k1[0]} name={k1[1]} stroke={k1[2]} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" dot={false}
              activeDot={{ r: 4, stroke: c.surface, strokeWidth: 2 }} isAnimationActive={false} />
            <Line type="monotone" dataKey={k2[0]} name={k2[1]} stroke={k2[2]} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" dot={false}
              activeDot={{ r: 4, stroke: c.surface, strokeWidth: 2 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </ChartFrame>
      <p className="text-xs text-ink/50 mt-1 max-w-[75ch]">
        {isChange
          ? 'Weeks are grouped by the day being forecast. When the two lines move apart, the model expected prices to go one way and they went the other.'
          : 'Each point is that week’s average miss in ₹ per quintal. The model line below the other means the model won that week.'}
      </p>
    </div>
  )
}

/** Why a crop was left out, in plain words (a full sentence, no prefix). */
function coverageReason(m) {
  return !m.val_rows && !m.test_rows
    ? 'The data has none of its prices in the validation or test periods, so its accuracy cannot be measured.'
    : `It has only ${num(m.val_rows)} validation and ${num(m.test_rows)} test forecasts, too few to measure its accuracy.`
}

function SkillCell({ s }) {
  const p = skillParts(s)
  return (
    <span className={`inline-flex items-center gap-1 font-semibold ${p.tone}`}>
      <p.Icon size={14} aria-hidden="true" />{p.big === '–' ? '–' : p.word === 'about equal' ? 'about equal' : `${p.big} ${p.word}`}
    </span>
  )
}

function Breakdown({ a, crop }) {
  const [showAll, setShowAll] = useState(false)
  const crops = Object.entries(a.per_crop_test)
  const excluded = Object.entries(a.data.excluded_crops || {})
  const states = Object.entries(a.per_state_test).sort((x, y) => y[1].rows - x[1].rows)
  const shown = showAll ? states : states.slice(0, 8)
  const head = (cols) => (
    <tr className="text-left text-ink/60">
      {cols.map(h => <th key={h} scope="col" className="font-semibold py-2 pr-4 border-b border-black/10 whitespace-nowrap">{h}</th>)}
    </tr>
  )
  const cols = ['Forecasts', 'Typical miss', COPY.baselineName, 'Versus that rule', 'Real price in range']
  return (
    <div className="space-y-8">
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <caption className="sr-only">Model accuracy by crop on unseen test data</caption>
          <thead>{head(['Crop', ...cols, 'Direction right'])}</thead>
          <tbody>
            {crops.map(([name, m]) => (
              <tr key={name} className={`border-b border-black/5 ${name === crop ? 'bg-forest/[0.06]' : ''}`}>
                <th scope="row" className="py-2 pr-4 text-left font-semibold whitespace-nowrap">{name}{name === crop && <span className="ml-2 text-[11px] font-medium text-ink/50">selected</span>}</th>
                <td className="py-2 pr-4 tabular-nums">{num(m.rows)}</td>
                <td className="py-2 pr-4 tabular-nums">{inr(m.model_mae)}</td>
                <td className="py-2 pr-4 tabular-nums">{inr(m.persistence_mae)}</td>
                <td className="py-2 pr-4 whitespace-nowrap"><SkillCell s={m.skill_vs_persistence} /></td>
                <td className="py-2 pr-4 tabular-nums">{pct(m.interval_coverage_80)}</td>
                <td className="py-2 pr-4 tabular-nums">{m.directional_accuracy === null ? '–' : pct(m.directional_accuracy)}</td>
              </tr>
            ))}
            {excluded.map(([name, m]) => (
              <tr key={name} className={`border-b border-black/5 text-ink/60 ${name === crop ? 'bg-forest/[0.06]' : ''}`}>
                <th scope="row" className="py-2 pr-4 text-left font-semibold whitespace-nowrap">{name}</th>
                <td colSpan={6} className="py-2 pr-4 text-xs">Not covered — {coverageReason(m).replace(/^./, ch => ch.toLowerCase())}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-xs text-ink/50 mt-2">“Direction right” counts only forecasts where the real price moved at least 2%: did the model call up or down correctly? 50% is a coin flip.</p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <caption className="sr-only">Model accuracy by state on unseen test data</caption>
          <thead>{head(['State', ...cols])}</thead>
          <tbody>
            {shown.map(([name, m]) => (
              <tr key={name} className="border-b border-black/5">
                <th scope="row" className="py-2 pr-4 text-left font-semibold whitespace-nowrap">
                  {name}{m.low_sample && <span className="ml-2 text-[11px] font-medium text-amber-700 dark:text-amber-300">few forecasts</span>}
                </th>
                <td className="py-2 pr-4 tabular-nums">{num(m.rows)}</td>
                <td className="py-2 pr-4 tabular-nums">{inr(m.model_mae)}</td>
                <td className="py-2 pr-4 tabular-nums">{inr(m.persistence_mae)}</td>
                <td className="py-2 pr-4 whitespace-nowrap"><SkillCell s={m.skill_vs_persistence} /></td>
                <td className="py-2 pr-4 tabular-nums">{pct(m.interval_coverage_80)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {states.length > 8 && (
          <button type="button" onClick={() => setShowAll(v => !v)} className="mt-2 text-xs font-semibold text-ink underline underline-offset-2">
            {showAll ? 'Show fewer states' : `Show all ${states.length} states`}
          </button>
        )}
      </div>
    </div>
  )
}

function Drivers({ a, c }) {
  const rank = a.feature_importance.ranking
  const max = Math.max(...rank.map(r => r.share), 0.0001)
  const top = rank[0]
  const calendarShare = rank.filter(r => CALENDAR_FEATURES.includes(r.feature)).reduce((s, r) => s + r.share, 0)
  const table = { cols: ['What the model looks at', 'Share of influence', 'Typical miss rises by (₹/quintal) if scrambled'], rows: rank.map(r => [r.label, pct(r.share), inr(r.mae_increase)]) }
  return (
    <div>
      <ChartFrame label="How much each input matters to the forecast, as a share of the total" table={table}>
        <div className="space-y-[2px]">
          {rank.map(r => (
            <div key={r.feature} className="flex items-center gap-3" title={`${r.label}: ${pct(r.share)}`}>
              <div className="w-52 shrink-0 text-xs text-ink/70 truncate">{r.label}</div>
              <div className="flex-1 h-4 rounded-r-[4px]" style={{ background: c.track }}>
                <div className="h-full" style={{ width: `${Math.max((r.share / max) * 100, r.share > 0 ? 2 : 0)}%`, background: c.baseline, borderRadius: '0 4px 4px 0' }} />
              </div>
              <div className="w-12 shrink-0 text-xs font-semibold tabular-nums text-right">{pct(r.share)}</div>
            </div>
          ))}
        </div>
      </ChartFrame>
      <p className="text-xs text-ink/50 mt-2 max-w-[75ch]">
        Measured by scrambling one input at a time on unseen data and seeing how much the typical miss grows (more growth = the model leaned on it more).
        {top && ` The most-used input is “${top.label}”.`}
      </p>
      {calendarShare >= 0.3 && (
        <div className="mt-3 flex items-start gap-2 text-xs text-amber-800 dark:text-amber-300 max-w-[75ch]">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>About {pct(calendarShare)} of the model’s weight is on the time of year. The training data spans only about two years, so each season has been seen once or twice — a seasonal habit it picked up can be wrong in a different year. More history is the fix.</span>
        </div>
      )}
    </div>
  )
}

function ScatterPlot({ a, c }) {
  const pts = a.scatter_test
  const { lim, beyond } = useMemo(() => {
    const abs = pts.flatMap(p => [Math.abs(p.actual), Math.abs(p.predicted)]).sort((x, y) => x - y)
    const p95 = abs.length ? abs[Math.min(abs.length - 1, Math.floor(abs.length * 0.95))] : 10
    const L = Math.min(Math.max(Math.ceil(p95 / 5) * 5, 10), 60)
    return { lim: L, beyond: pts.filter(p => Math.abs(p.actual) > L || Math.abs(p.predicted) > L).length }
  }, [pts])
  const ticks = [-lim, -lim / 2, 0, lim / 2, lim]
  const data = pts.map(p => ({ ...p, a: Math.max(-lim, Math.min(lim, p.actual)), p: Math.max(-lim, Math.min(lim, p.predicted)) }))
  const table = { cols: ['Crop', 'Real change', 'Predicted change'], rows: pts.slice(0, 60).map(p => [p.crop, `${p.actual}%`, `${p.predicted}%`]) }
  const dot = (props) => {
    const { cx, cy } = props
    if (typeof cx !== 'number') return null
    return (
      <g>
        <circle cx={cx} cy={cy} r={12} fill="transparent" />
        <circle cx={cx} cy={cy} r={4} fill={c.model} fillOpacity={0.55} stroke={c.surface} strokeWidth={2} />
      </g>
    )
  }
  return (
    <ChartFrame label="A random sample of forecasts: real 7-day price change on the horizontal axis against the change the model predicted on the vertical axis"
      table={{ ...table, rows: [...table.rows, ['', `(first 60 of ${pts.length} sampled forecasts)`, '']] }}>
      <ResponsiveContainer width="100%" height={340}>
        <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 18 }}>
          <CartesianGrid stroke={c.grid} />
          <XAxis type="number" dataKey="a" domain={[-lim, lim]} ticks={ticks} tick={{ fontSize: 11, fill: c.axis }} tickLine={false} axisLine={{ stroke: c.grid }}
            tickFormatter={v => `${+v.toFixed(1)}%`} label={{ value: 'What the price really did over 7 days', position: 'insideBottom', offset: -10, fontSize: 11, fill: c.axis }} />
          <YAxis type="number" dataKey="p" domain={[-lim, lim]} ticks={ticks} tick={{ fontSize: 11, fill: c.axis }} tickLine={false} axisLine={false} width={52}
            tickFormatter={v => `${+v.toFixed(1)}%`} label={{ value: 'What the model predicted', angle: -90, position: 'insideLeft', offset: 8, fontSize: 11, fill: c.axis, style: { textAnchor: 'middle' } }} />
          <ZAxis range={[40, 40]} />
          <ReferenceLine segment={[{ x: -lim, y: -lim }, { x: lim, y: lim }]} stroke={c.baseline} strokeWidth={1.5} ifOverflow="hidden" />
          <ReferenceLine y={0} stroke={c.axis} strokeWidth={1} />
          <ReferenceLine x={0} stroke={c.axis} strokeWidth={1} />
          <Tooltip cursor={false} content={({ active, payload }) => {
            if (!active || !payload?.length) return null
            const d = payload[0].payload
            return (
              <div className="rounded-lg px-3 py-2 text-xs shadow-lifted border" style={{ background: c.surface, borderColor: c.grid, color: c.ink }}>
                <div className="font-semibold mb-1">{d.crop}</div>
                <div>Real change: <strong className="tabular-nums">{d.actual > 0 ? '+' : ''}{d.actual}%</strong></div>
                <div>Model predicted: <strong className="tabular-nums">{d.predicted > 0 ? '+' : ''}{d.predicted}%</strong></div>
              </div>
            )
          }} />
          <Scatter data={data} shape={dot} isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
      <div className="text-xs text-ink/70 mt-1 flex flex-wrap gap-x-5 gap-y-1">
        <Key color={c.model} label="One forecast (random sample)" />
        <Key line color={c.baseline} label="A perfect forecast would sit on this line" />
      </div>
      {beyond > 0 && <p className="text-xs text-ink/50 mt-1">{beyond} of {pts.length} sampled forecasts moved more than {lim}% and are drawn at the edge of the chart.</p>}
    </ChartFrame>
  )
}

function About({ a }) {
  const d = a.data
  const prep = d.prep
  const cand = Object.entries(a.candidates)
  const labelOf = { hgb: 'HistGradientBoosting', catboost: 'CatBoost' }
  return (
    <details className="rounded-xl border border-black/10 px-4 py-3 text-sm">
      <summary className="cursor-pointer font-semibold">About the data and how the model was chosen</summary>
      <div className="mt-4 space-y-6 text-ink/70">
        <div>
          <h4 className="font-semibold text-ink mb-1">What it learned from</h4>
          <ul className="list-disc pl-5 space-y-1">
            <li>Prices from {longDate(d.date_range[0])} to {longDate(d.date_range[1])}{d.dataset ? ` (${d.dataset})` : ''}.</li>
            {prep && <li>{num(prep.rows_in)} raw rows were repaired and filtered down to {num(prep.rows_out)} usable rows ({pct(prep.rows_out_share_of_input)}) across {num(prep.states)} states and {num(prep.markets)} markets.</li>}
            <li>Crops covered: {d.crops.join(', ')}.{Object.keys(d.excluded_crops || {}).length > 0 && ` Left out because they cannot be tested: ${Object.keys(d.excluded_crops).join(', ')}.`}</li>
            <li>It learned from {num(d.split.rows.train)} forecasts up to {longDate(d.split.train_through_target_date)}, was tuned on {num(d.split.rows.val)} more up to {longDate(d.split.val_through_target_date)}, and was graded on the last {num(d.split.rows.test)}. A {d.split.purge_days}-day gap separates each stage so no answer leaks across.</li>
          </ul>
        </div>

        {prep?.identifier_recovery_simulation && (
          <div>
            <h4 className="font-semibold text-ink mb-1">How gaps in the raw data were handled</h4>
            <ul className="list-disc pl-5 space-y-1">
              <li>No price was ever invented. A row without a price was dropped.</li>
              <li>A missing date was filled only when the rows just before and after shared the same date; hiding known dates and re-deriving them got {pct(prep.date_recovery_simulation?.accuracy_when_recovered, 2)} right.</li>
              <li>A missing state was filled only from a market or district that belongs to exactly one state ({pct(prep.identifier_recovery_simulation.state_from_market_or_district.accuracy_when_recovered, 2)} right in the same test); a missing commodity only from a variety that belongs to exactly one commodity ({pct(prep.identifier_recovery_simulation.commodity_from_variety.accuracy_when_recovered, 2)} right).</li>
            </ul>
          </div>
        )}

        <div>
          <h4 className="font-semibold text-ink mb-1">How the model was chosen</h4>
          <p className="mb-2">{a.selection.rule}. Only the validation column below decides; the test column is shown for honesty.</p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="text-left text-ink/60">
                  {['Model', 'Validation miss (decides)', 'Test miss (not used)', ''].map(h => <th key={h} scope="col" className="font-semibold py-1.5 pr-4 border-b border-black/10 whitespace-nowrap">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {cand.map(([fam, r]) => (
                  <tr key={fam} className="border-b border-black/5">
                    <th scope="row" className="py-1.5 pr-4 text-left font-semibold">{labelOf[fam] || fam}</th>
                    <td className="py-1.5 pr-4 tabular-nums">{inr(r.validation.model.mae)}</td>
                    <td className="py-1.5 pr-4 tabular-nums">{inr(r.test.model.mae)}</td>
                    <td className="py-1.5 pr-4 font-semibold">{fam === a.model.family ? 'Chosen' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <h4 className="font-semibold text-ink mb-1">The range</h4>
          <p>{d.interval?.method ? `Two extra models predict a low and a high price. ${d.interval.method.charAt(0).toUpperCase()}${d.interval.method.slice(1)}.` : 'Two extra models predict a low and a high price.'}</p>
        </div>
        <p className="text-xs text-ink/50">{COPY.limits}</p>
      </div>
    </details>
  )
}

// ───────────────────────── root ─────────────────────────
export default function MlAnalysis({ crop }) {
  const { theme } = useTheme()
  const c = PAL[theme === 'dark' ? 'dark' : 'light']
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let live = true
    api.getMlAnalysis().then(d => { if (live) setData(d) }).catch(() => { if (live) setFailed(true) }).finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [])

  if (loading) return <LoadingSpinner label="Loading model analysis" />
  // The ML routes are additive: if they are missing or the call failed, the page simply omits this section.
  if (failed || !data) return null

  if (!data.available) {
    return (
      <section className="border-t border-black/5 pt-8 mb-10" aria-labelledby="mla-heading">
        <h2 id="mla-heading" className="font-display text-xl font-bold mb-3">{COPY.heading}</h2>
        <div className="bg-wheat/50 border border-black/5 rounded-xl px-4 py-4 text-sm flex items-start gap-2 max-w-[80ch]">
          <Info size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          <div>
            <div className="font-semibold">{COPY.unavailable}</div>
            <div className="text-ink/60 mt-1">{COPY.reasons[data.reason] || data.message}</div>
          </div>
        </div>
      </section>
    )
  }

  const excluded = data.data.excluded_crops?.[crop]
  return (
    <section className="border-t border-black/5 pt-8 mb-10" aria-labelledby="mla-heading">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-5">
        <h2 id="mla-heading" className="font-display text-xl font-bold">{COPY.heading}</h2>
        <span className="text-sm text-ink/50">{COPY.sub}</span>
        <span className="text-xs font-semibold rounded-full px-2.5 py-0.5 border border-black/10 text-ink/70">{data.model.label}</span>
        <span className="text-xs text-ink/40">trained {longDate(data.model.trained_utc)}</span>
      </div>

      {excluded && (
        <div className="mb-6 flex items-start gap-2 text-sm bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 text-amber-800 dark:text-amber-300 rounded-lg px-4 py-3 max-w-[80ch]">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span><strong>{crop}</strong> is not covered by the ML forecast. {coverageReason(excluded)} The figures below are for the crops that are covered.</span>
        </div>
      )}

      <Verdict a={data} />

      <Section title="Against two simple rules" hint="Any forecast has to beat “the price will stay the same” and “the price will go back to its 7-day average” to be worth using.">
        <VsRules a={data} c={c} />
      </Section>

      <Section title="How far off was each forecast?" hint="Share of unseen forecasts that landed within 5%, 10% or 20% of the real price.">
        <Buckets a={data} c={c} />
      </Section>

      <Section title="Week by week" hint="Whether the model’s direction and size of move matched what prices really did, across the unseen period.">
        <Weekly a={data} c={c} crop={crop} />
      </Section>

      <Section title="Predicted against real" hint="Each dot is one forecast. The closer to the line, the better.">
        <ScatterPlot a={data} c={c} />
      </Section>

      <Section title="What the model pays attention to">
        <Drivers a={data} c={c} />
      </Section>

      <Section title="By crop and by state" hint="Where it does well and where it doesn’t. States with few forecasts are marked.">
        <Breakdown a={data} crop={crop} />
      </Section>

      <About a={data} />
    </section>
  )
}
