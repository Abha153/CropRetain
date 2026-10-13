import React from 'react'

const STYLES = {
  success: 'bg-emerald-100 dark:bg-emerald-950/50 text-emerald-800 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800',
  warning: 'bg-amber-100 dark:bg-amber-950/50 text-amber-800 dark:text-amber-300 border-amber-300 dark:border-amber-800',
  info: 'bg-sky-100 dark:bg-sky-950/50 text-sky-800 dark:text-sky-300 border-sky-300 dark:border-sky-800',
  neutral: 'bg-stone-100 dark:bg-white/10 text-stone-700 dark:text-stone-300 border-stone-300 dark:border-white/15',
  marigold: 'bg-marigold/15 dark:bg-marigold/20 text-marigold-dark dark:text-marigold-light border-marigold/40 dark:border-marigold/50',
  forest: 'bg-forest/10 dark:bg-forest-light/20 text-forest dark:text-forest-light border-forest/30 dark:border-forest-light/40',
  // District/variety-aggregated reference price -- deliberately distinct
  // from "success" (verified mandi-specific) so it can never be mistaken
  // for a real mandi modal price at a glance.
  district: 'bg-violet-100 dark:bg-violet-950/50 text-violet-800 dark:text-violet-300 border-violet-300 dark:border-violet-800',
}

export default function Badge({ children, tone = 'neutral', className = '' }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold border ${STYLES[tone] || STYLES.neutral} ${className}`}>
      {children}
    </span>
  )
}
