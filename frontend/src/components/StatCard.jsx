import React from 'react'

/**
 * Shared metric card -- used by Farmer, Buyer and Admin dashboards.
 * Same props/API as before (label, value, sub, icon, tone); `icon` can be
 * either a Lucide element or a plain emoji string (both existing callers
 * are still supported unchanged). Visual refinement only: an icon "chip"
 * instead of a bare glyph, tighter type hierarchy -- no new props, no
 * behavior change.
 */
export default function StatCard({ label, value, sub, icon, tone = 'default' }) {
  const isMarigold = tone === 'marigold'
  const toneClasses = isMarigold ? 'bg-forest text-paper' : 'bg-white dark:bg-white/5 text-ink dark:text-paper'
  const chipClasses = isMarigold ? 'bg-white/10 text-marigold-light' : 'bg-forest/8 dark:bg-white/10 text-forest dark:text-forest-light'
  return (
    <div className={`rounded-2xl p-5 shadow-card border border-black/5 dark:border-white/10 ${toneClasses}`}>
      <div className="flex items-start justify-between gap-2 mb-3">
        <span className={`text-xs font-semibold ${isMarigold ? 'text-marigold-light' : 'text-ink/50 dark:text-paper/50'}`}>{label}</span>
        {icon && (
          <span className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${chipClasses}`}>
            {icon}
          </span>
        )}
      </div>
      <div className="font-mono-data text-2xl font-semibold leading-none">{value}</div>
      {sub && <div className={`text-xs mt-1.5 ${isMarigold ? 'text-paper/70' : 'text-ink/50 dark:text-paper/50'}`}>{sub}</div>}
    </div>
  )
}
