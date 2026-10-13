import React, { useState } from 'react'
import { api } from '../api/client'
import Badge from '../components/Badge'
import LoadingSpinner from '../components/LoadingSpinner'
import { useI18n } from '../i18n/I18nContext'

const DEFAULT_SCENARIO = (label, labelKey = null, labelParams = {}) => ({
  label, labelKey, labelParams, crop: 'Tomato', quantity_kg: 2000, selling_price_per_kg: 22,
  transport_cost: 100, labour_cost: 300, packaging_cost: 200, storage_cost: 0, other_cost: 0,
})

function ScenarioCard({ scenario, onChange, onRemove, removable, t }) {
  function set(field, value) {
    onChange({ ...scenario, [field]: value })
  }
  return (
    <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
      <div className="flex items-center justify-between mb-3">
        <input value={scenario.label} onChange={e => set('label', e.target.value)} className="font-display font-semibold text-lg border-b border-dashed border-black/20 focus:outline-none bg-transparent" />
        {removable && <button onClick={onRemove} className="text-xs text-red-500 dark:text-red-400 hover:underline">{t('profit.remove')}</button>}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label={t('common.quantityKg')} value={scenario.quantity_kg} onChange={v => set('quantity_kg', v)} />
        <Field label={t('profit.sellingPrice')} value={scenario.selling_price_per_kg} onChange={v => set('selling_price_per_kg', v)} />
        <Field label={t('profit.transportCost')} value={scenario.transport_cost} onChange={v => set('transport_cost', v)} />
        <Field label={t('profit.labourCost')} value={scenario.labour_cost} onChange={v => set('labour_cost', v)} />
        <Field label={t('profit.packagingCost')} value={scenario.packaging_cost} onChange={v => set('packaging_cost', v)} />
        <Field label={t('profit.storageCost')} value={scenario.storage_cost} onChange={v => set('storage_cost', v)} />
      </div>
    </div>
  )
}

function Field({ label, value, onChange }) {
  return (
    <div>
      <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{label}</label>
      <input type="number" value={value} onChange={e => onChange(Number(e.target.value))} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper" />
    </div>
  )
}

export default function ProfitCalculator() {
  const { t } = useI18n()
  const [scenarios, setScenarios] = useState([
    DEFAULT_SCENARIO(t('profit.localMandi'), 'profit.localMandi'),
    { ...DEFAULT_SCENARIO(t('profit.directBuyer'), 'profit.directBuyer'), selling_price_per_kg: 27, transport_cost: 800, packaging_cost: 250 },
  ])
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  function updateScenario(idx, updated) {
    setScenarios(prev => prev.map((s, i) => i === idx ? updated : s))
  }
  function addScenario() {
    const nextIndex = scenarios.length + 1
    setScenarios(prev => [...prev, DEFAULT_SCENARIO(t('profit.optionNumber', { number: nextIndex }), 'profit.optionNumber', { number: nextIndex })])
  }
  function removeScenario(idx) {
    setScenarios(prev => prev.filter((_, i) => i !== idx))
  }

  React.useEffect(() => {
    setScenarios(prev => prev.map((scenario, index) => {
      if (!scenario.labelKey) return scenario
      if (index === 0 && scenario.labelKey === 'profit.localMandi') {
        return { ...scenario, label: t('profit.localMandi') }
      }
      if (index === 1 && scenario.labelKey === 'profit.directBuyer') {
        return { ...scenario, label: t('profit.directBuyer') }
      }
      if (scenario.labelKey === 'profit.optionNumber') {
        return { ...scenario, label: t('profit.optionNumber', scenario.labelParams) }
      }
      return scenario
    }))
  }, [t])

  async function compare() {
    setLoading(true)
    setError('')
    try {
      const data = await api.profitCompare({ scenarios })
      setResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h1 className="font-display text-3xl font-bold mb-1">🧮 {t('profit.title')}</h1>
      <p className="text-ink/60 dark:text-paper/60 mb-6">{t('profit.subtitle')}</p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        {scenarios.map((s, i) => (
          <ScenarioCard key={i} scenario={s} onChange={(u) => updateScenario(i, u)} onRemove={() => removeScenario(i)} removable={scenarios.length > 1} t={t} />
        ))}
      </div>

      <div className="flex items-center gap-3 mb-6">
        <button onClick={addScenario} className="text-sm bg-white dark:bg-white/5 border border-black/10 dark:border-white/15 rounded-lg px-4 py-2 font-medium hover:bg-wheat dark:bg-white/5 transition-colors">+ {t('profit.addOption')}</button>
        <button onClick={compare} disabled={loading} className="text-sm bg-marigold hover:bg-marigold-dark text-ink dark:text-paper font-semibold rounded-lg px-5 py-2 transition-colors disabled:opacity-60">
          {loading ? t('profit.calculating') : t('profit.compareOptions')}
        </button>
      </div>

      {error && <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 text-sm rounded-lg px-3 py-2 mb-4">{error}</div>}
      {loading && <LoadingSpinner label={t('profit.loading')} />}

      {result && !loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {result.scenarios.map(s => (
            <div key={s.label} className={`rounded-2xl p-5 shadow-card border ${s.is_best ? 'bg-forest text-paper border-forest' : 'bg-white dark:bg-white/5 border-black/5 dark:border-white/10'}`}>
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-display font-semibold text-lg">{s.label}</h3>
                {s.is_best && <Badge tone="marigold">🏆 {t('profit.bestOption')}</Badge>}
              </div>
              <div className={`text-3xl font-mono-data font-bold mb-3 ${s.is_best ? '' : 'text-forest'}`}>₹{s.net_profit.toLocaleString()}</div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className={s.is_best ? 'text-paper/70' : 'text-ink/50 dark:text-paper/50'}>{t('profit.revenue')}</div>
                <div className="text-right font-mono-data">₹{s.revenue.toLocaleString()}</div>
                <div className={s.is_best ? 'text-paper/70' : 'text-ink/50 dark:text-paper/50'}>{t('profit.totalCost')}</div>
                <div className="text-right font-mono-data">₹{s.total_cost.toLocaleString()}</div>
                <div className={s.is_best ? 'text-paper/70' : 'text-ink/50 dark:text-paper/50'}>{t('profit.perKg')}</div>
                <div className="text-right font-mono-data">₹{s.net_profit_per_kg}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
