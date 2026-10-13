import React, { useEffect, useState } from 'react'
import { Bell, TrendingDown, TrendingUp, Sparkles, Leaf } from 'lucide-react'
import { api } from '../api/client'
import Badge from '../components/Badge'
import LoadingSpinner from '../components/LoadingSpinner'
import { useI18n } from '../i18n/I18nContext'

const ICONS = {
  price_drop: { icon: TrendingDown, tone: 'text-red-500 bg-red-50' },
  high_demand: { icon: TrendingUp, tone: 'text-emerald-600 bg-emerald-50' },
  opportunity: { icon: Sparkles, tone: 'text-amber-600 bg-amber-50' },
  harvest_reminder: { icon: Leaf, tone: 'text-forest bg-forest/5' },
}

export default function Notifications() {
  const { t } = useI18n()
  const [items, setItems] = useState(null)
  const [generating, setGenerating] = useState(false)

  async function load() {
    const data = await api.myNotifications()
    setItems(data)
  }
  useEffect(() => { load() }, [])

  async function markRead(id) {
    await api.markNotificationRead(id)
    load()
  }

  async function generate() {
    setGenerating(true)
    try {
      await api.generateNotification()
      await load()
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-1 flex-wrap gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-forest/60">{t('notifications.insights')}</p>
          <h1 className="font-display text-3xl font-bold mt-2 inline-flex items-center gap-2"><Bell size={22} className="text-forest" /> {t('navAlerts')}</h1>
        </div>
        <button onClick={generate} disabled={generating} className="text-sm bg-forest text-paper font-semibold rounded-xl px-4 py-2.5 transition-colors disabled:opacity-60 shadow-soft">
          {generating ? t('notifications.generating') : t('notifications.generate')}
        </button>
      </div>
      <p className="text-ink/60 dark:text-paper/60 -mt-2">{t('notifications.subtitle')}</p>

      {items === null ? <LoadingSpinner label={t('notifications.loading')} /> : items.length === 0 ? (
        <p className="text-sm text-ink/50 dark:text-paper/50">{t('dashboard.noAlerts')}</p>
      ) : (
        <div className="space-y-3">
          {items.map(n => {
            const iconConfig = ICONS[n.type] || { icon: Bell, tone: 'text-forest bg-forest/5' }
            const Icon = iconConfig.icon
            return (
              <div key={n.id} className={`bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 shadow-card p-4 flex items-start gap-3 ${n.is_read ? 'opacity-60' : ''}`}>
                <div className={`mt-0.5 flex h-10 w-10 items-center justify-center rounded-xl ${iconConfig.tone}`}><Icon size={18} /></div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold">{n.title}</h3>
                    {!n.is_read && <Badge tone="marigold">{t('notifications.new')}</Badge>}
                  </div>
                  <p className="text-sm text-ink/60 dark:text-paper/60 mt-0.5">{n.message}</p>
                </div>
                {!n.is_read && (
                  <button onClick={() => markRead(n.id)} className="text-xs text-forest font-semibold hover:underline whitespace-nowrap">{t('notifications.markRead')}</button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
