import React from 'react'
import { Link } from 'react-router-dom'
import { Sprout, ArrowRight } from 'lucide-react'
import Badge from './Badge'
import { useI18n } from '../i18n/I18nContext'

// Same crop-name -> translation-key mapping the other pages use, so crops in
// the farmer's profile are shown in the selected language.
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

// Compact "Farm Health & Soil" summary for the top of the farmer dashboard.
//
// Phase 1 is deliberately honest about what the platform actually holds:
//  - location and crops come from the farmer's own profile, so they are
//    labelled "user-entered";
//  - soil-test history is not stored anywhere yet, and no field sensors are
//    integrated, so those rows say so instead of showing placeholder numbers.
// The card therefore never displays a soil value it does not have.
function Fact({ label, children }) {
  return (
    <div className="rounded-2xl bg-paper dark:bg-white/5 border border-black/5 dark:border-white/10 px-4 py-3 min-w-0">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-ink/50 dark:text-paper/50 mb-1">{label}</div>
      {children}
    </div>
  )
}

export default function FarmHealthCard({ user }) {
  const { t } = useI18n()
  const location = typeof user?.location === 'string' ? user.location.trim() : ''
  const crops = Array.isArray(user?.crops) ? user.crops.filter(Boolean) : []

  return (
    <section
      aria-labelledby="farm-health-heading"
      className="bg-white dark:bg-white/5 rounded-3xl p-5 md:p-6 shadow-card border border-black/5 dark:border-white/10"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-forest/10 dark:bg-forest-light/15 text-forest dark:text-forest-light flex items-center justify-center">
            <Sprout size={18} />
          </div>
          <h2 id="farm-health-heading" className="font-display text-lg font-bold">{t('dashboard.soilCard.title')}</h2>
        </div>
        <Link
          to="/soil-advisor"
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-forest dark:text-forest-light hover:underline"
        >
          {t('dashboard.soilCard.cta')} <ArrowRight size={14} />
        </Link>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Fact label={t('dashboard.soilCard.location')}>
          {location ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold break-words">{location}</span>
              <Badge tone="neutral">{t('dashboard.soilCard.userEntered')}</Badge>
            </div>
          ) : (
            <span className="text-sm text-ink/60 dark:text-paper/60">{t('dashboard.soilCard.notSet')}</span>
          )}
        </Fact>

        <Fact label={t('dashboard.soilCard.crops')}>
          {crops.length ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold break-words">{crops.map(c => (CROP_KEY_MAP[c] ? t(CROP_KEY_MAP[c]) : c)).join(', ')}</span>
              <Badge tone="neutral">{t('dashboard.soilCard.userEntered')}</Badge>
            </div>
          ) : (
            <span className="text-sm text-ink/60 dark:text-paper/60">{t('dashboard.soilCard.notSet')}</span>
          )}
        </Fact>

        <Fact label={t('dashboard.soilCard.soilTest')}>
          <span className="text-sm text-ink/60 dark:text-paper/60">{t('dashboard.soilCard.noSoilTest')}</span>
        </Fact>

        <Fact label={t('dashboard.soilCard.sensors')}>
          <span className="text-sm text-ink/60 dark:text-paper/60">{t('dashboard.soilCard.noSensors')}</span>
        </Fact>
      </div>

      <p className="mt-4 text-sm text-ink/60 dark:text-paper/60 leading-relaxed">{t('dashboard.soilCard.emptyBody')}</p>
    </section>
  )
}
