import React from 'react'
import { Link } from 'react-router-dom'
import { useI18n } from '../i18n/I18nContext'

/** Plain-language privacy notice. Public. Describes what the app actually
 *  stores today; it is not a substitute for a legally reviewed policy. */
const SECTIONS = ['collect', 'passwords', 'logins', 'soil', 'sharing', 'demo', 'rights']

export default function Privacy() {
  const { t } = useI18n()
  return (
    <div className="min-h-screen bg-paper dark:bg-ink text-ink dark:text-paper">
      <main id="main" className="max-w-3xl mx-auto px-6 py-10">
        <Link to="/" className="text-sm underline text-forest dark:text-forest-light">{t('disclaimer.back')}</Link>
        <h1 className="font-display text-2xl md:text-3xl font-bold mt-4 mb-2">{t('privacy.title')}</h1>
        <p className="text-sm mb-6 text-ink/70 dark:text-paper/70">{t('privacy.intro')}</p>
        {SECTIONS.map(k => (
          <section key={k} className="mb-6">
            <h2 className="font-display text-lg font-bold mb-1">{t(`privacy.${k}.title`)}</h2>
            <p className="text-sm leading-relaxed">{t(`privacy.${k}.body`)}</p>
          </section>
        ))}
        <p className="text-xs text-ink/60 dark:text-paper/60">{t('privacy.notice')}</p>
      </main>
    </div>
  )
}
