import React from 'react'
import { Link } from 'react-router-dom'
import Badge from '../components/Badge'
import { useI18n } from '../i18n/I18nContext'

/**
 * Market Information & Data Transparency. Public (no login needed) so it can
 * be read before signing up. All wording comes from i18n keys; the label
 * legend describes how the app actually uses each label today.
 */
const LABELS = [
  { key: 'LIVE', tone: 'success' },
  { key: 'DEMO', tone: 'warning' },
  { key: 'ESTIMATED', tone: 'info' },
  { key: 'UNAVAILABLE', tone: 'neutral' },
]

export default function Disclaimer() {
  const { t } = useI18n()
  return (
    <div className="min-h-screen bg-paper dark:bg-ink text-ink dark:text-paper">
      <main id="main" className="max-w-3xl mx-auto px-6 py-10">
        <Link to="/" className="text-sm underline text-forest dark:text-forest-light">{t('disclaimer.back')}</Link>
        <h1 className="font-display text-2xl md:text-3xl font-bold mt-4 mb-4">{t('disclaimer.title')}</h1>
        <p className="text-sm leading-relaxed mb-8">{t('disclaimer.body')}</p>

        <h2 className="font-display text-lg font-bold mb-2">{t('disclaimer.labelsTitle')}</h2>
        <dl className="space-y-2 mb-8">
          {LABELS.map(l => (
            <div key={l.key} className="flex flex-wrap items-start gap-3">
              <dt className="w-32 shrink-0"><Badge tone={l.tone}>{t(`disclaimer.label.${l.key}`)}</Badge></dt>
              <dd className="text-sm flex-1 min-w-[12rem]">{t(`disclaimer.label.${l.key}.desc`)}</dd>
            </div>
          ))}
        </dl>

        <h2 className="font-display text-lg font-bold mb-2">{t('disclaimer.demoTitle')}</h2>
        <p className="text-sm leading-relaxed mb-8">{t('disclaimer.demoBody')}</p>

        <p className="text-xs text-ink/60 dark:text-paper/60">{t('disclaimer.sourceNote')}</p>
      </main>
    </div>
  )
}
