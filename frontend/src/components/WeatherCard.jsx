import React, { useEffect, useState } from 'react'
import { Droplets, Wind, MapPin, RefreshCw } from 'lucide-react'
import { api } from '../api/client'
import { iconForWeatherCode } from '../utils/weatherCodes'
import { useI18n } from '../i18n/I18nContext'

const STATUS_BADGE_KEY = {
  LIVE: { key: 'weather.live', className: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  DEMO: { key: 'weather.demo', className: 'bg-amber-50 text-amber-700 border-amber-200' },
  UNAVAILABLE: { key: 'weather.unavailableBadge', className: 'bg-gray-100 text-gray-500 border-gray-200' },
}

// Farmer-centric advisory line, computed only from real returned numbers
// -- never invented. Mirrors backend's derive_weather_risk() thresholds
// so the wording stays consistent with what AI Advisor says elsewhere.
// Returns a translation key (+ whether the demo-forecast note applies) so
// callers can render it via t() and it re-renders correctly on language
// switch, same pattern as opportunity.reason.* in BestSellingOpportunity.
function advisoryKeyFor(weather) {
  if (!weather || !weather.forecast || weather.forecast.length < 2) return null
  const tomorrow = weather.forecast[1]
  const prob = tomorrow.rainfall_probability ?? 0
  const mm = tomorrow.rainfall_mm ?? 0
  const isDemo = weather.status === 'DEMO'
  if (prob >= 70 || mm >= 20) {
    return isDemo ? 'weather.advisory.highRainDemo' : 'weather.advisory.highRain'
  }
  if (prob >= 40 || mm >= 8) {
    return isDemo ? 'weather.advisory.moderateRainDemo' : 'weather.advisory.moderateRain'
  }
  return isDemo ? 'weather.advisory.stableDemo' : 'weather.advisory.stable'
}

/**
 * Props: `latitude`/`longitude` (optional -- pass fresh GPS coordinates
 * from requestGeolocatedMarket() when available) and `location` (name,
 * used both as a display fallback and as the seeded-demo lookup key).
 * If no coordinates are passed, falls back to GET /weather/farmer (the
 * signed-in farmer's own saved location) -- see api/client.js.
 */
export default function WeatherCard({ latitude, longitude, location }) {
  const { t } = useI18n()
  const [weather, setWeather] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  function load() {
    setLoading(true)
    setError('')
    const req = (latitude != null && longitude != null)
      ? api.getWeatherByLocation(latitude, longitude, location)
      : api.getFarmerWeather()
    req.then(setWeather).catch(e => setError(e.message)).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [latitude, longitude, location])

  if (loading) {
    return (
      <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5 animate-pulse">
        <div className="h-4 w-24 bg-wheat dark:bg-white/10 rounded mb-3" />
        <div className="h-16 bg-wheat/50 dark:bg-white/5 rounded" />
      </div>
    )
  }

  if (error || !weather) {
    return (
      <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
        <h3 className="font-display font-semibold text-base mb-1">{t('weather.title')}</h3>
        <p className="text-sm text-ink/50 dark:text-paper/50">{error || t('weather.unavailable')}</p>
      </div>
    )
  }

  const badge = STATUS_BADGE_KEY[weather.status] || STATUS_BADGE_KEY.UNAVAILABLE

  if (weather.status === 'UNAVAILABLE') {
    return (
      <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-display font-semibold text-base">{t('weather.title')}</h3>
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${badge.className}`}>{t(badge.key)}</span>
        </div>
        <p className="text-sm text-ink/50 dark:text-paper/50">{t('weather.noData')}</p>
      </div>
    )
  }

  const CurrentIcon = iconForWeatherCode(weather.current.weather_code)
  const advisoryKey = advisoryKeyFor(weather)

  return (
    <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div>
          <h3 className="font-display font-semibold text-base">{t('weather.title')}</h3>
          <div className="flex items-center gap-1 text-xs text-ink/50 dark:text-paper/50 mt-0.5">
            <MapPin size={12} /> {weather.location?.name || location || '—'}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${badge.className}`}>{t(badge.key)}</span>
          <button onClick={load} title={t('common.refresh')} aria-label={t('common.refresh')} className="text-ink/30 dark:text-paper/30 hover:text-forest dark:hover:text-forest-light transition-colors">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {weather.status === 'DEMO' && (
        <p className="text-[11px] text-amber-700/80 dark:text-amber-300/80 mb-3 leading-snug">
          {t('weather.demoDisclaimer', { source: weather.source })}
        </p>
      )}
      {weather.status === 'LIVE' && (
        <p className="text-[11px] text-ink/40 dark:text-paper/40 mb-3">{t('weather.sourceLine', { source: weather.source })}</p>
      )}

      <div className="flex items-center gap-4 mb-4">
        <CurrentIcon size={40} className="text-forest dark:text-forest-light shrink-0" />
        <div>
          <div className="font-mono-data text-3xl font-bold leading-none">{weather.current.temperature}°C</div>
          <div className="text-sm text-ink/60 dark:text-paper/60 mt-1">{weather.current.condition}</div>
        </div>
        <div className="ml-auto grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-ink/50 dark:text-paper/50">
          {weather.current.humidity != null && (
            <div className="flex items-center gap-1"><Droplets size={13} /> {weather.current.humidity}%</div>
          )}
          <div className="flex items-center gap-1"><Wind size={13} /> {weather.current.wind_speed_kmh} km/h</div>
        </div>
      </div>

      {advisoryKey && (
        <p className="text-xs text-ink/60 dark:text-paper/60 bg-sage/30 dark:bg-white/5 rounded-lg px-3 py-2 mb-4 leading-relaxed">{t(advisoryKey)}</p>
      )}

      {weather.forecast && weather.forecast.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
          {weather.forecast.map((day, i) => {
            const DayIcon = iconForWeatherCode(day.weather_code)
            const dayLabel = new Date(day.date).toLocaleDateString('en-IN', { weekday: 'short' }).toUpperCase()
            return (
              <div key={day.date} className={`flex flex-col items-center shrink-0 w-16 py-2 rounded-xl ${i === 0 ? 'bg-forest/5 border border-forest/20' : ''}`}>
                <div className="text-[10px] font-semibold text-ink/50 dark:text-paper/50">{i === 0 ? t('weather.today') : dayLabel}</div>
                <DayIcon size={20} className="my-1 text-forest dark:text-forest-light" />
                <div className="text-xs font-mono-data font-semibold">{Math.round(day.temp_max)}°</div>
                <div className="text-[10px] text-ink/40 dark:text-paper/40">{Math.round(day.temp_min)}°</div>
                <div className="text-[10px] text-rain mt-0.5">{Math.round(day.rainfall_probability)}%</div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
