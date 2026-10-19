import React, { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nContext'

const TONE = {
  INSUFFICIENT_VERIFICATION_EVIDENCE: 'neutral',
  SELF_DECLARED: 'info',
  PLATFORM_VERIFIED: 'success',
  VERIFICATION_REJECTED: 'warning',
}
const EMOJI = {
  INSUFFICIENT_VERIFICATION_EVIDENCE: '\u26aa',
  SELF_DECLARED: '\ud83d\udfe1',
  PLATFORM_VERIFIED: '\ud83d\udfe2',
  VERIFICATION_REJECTED: '\ud83d\udd34',
}
const LABEL_KEY = {
  INSUFFICIENT_VERIFICATION_EVIDENCE: 'verification.badge.insufficient',
  SELF_DECLARED: 'verification.badge.selfDeclared',
  PLATFORM_VERIFIED: 'verification.badge.platformVerified',
  VERIFICATION_REJECTED: 'verification.badge.rejected',
}
const DESC_KEY = {
  INSUFFICIENT_VERIFICATION_EVIDENCE: 'verification.badge.insufficientDesc',
  SELF_DECLARED: 'verification.badge.selfDeclaredDesc',
  PLATFORM_VERIFIED: 'verification.badge.platformVerifiedDesc',
  VERIFICATION_REJECTED: 'verification.badge.rejectedDesc',
}

/**
 * CropRetain never claims government/eNAM verification. This always reflects
 * the real backend status -- see app/routers/buyer_verification.py::display_info.
 * Never invents a value; while loading it renders nothing rather than
 * guessing a tier from the old binary verification_status field.
 */
export default function VerificationBadge({ buyerId, compact = false, className = '' }) {
  const { t } = useI18n()
  const [badge, setBadge] = useState(null)

  useEffect(() => {
    let live = true
    if (!buyerId) return
    api.getBuyerVerificationBadge(buyerId).then(b => { if (live) setBadge(b) }).catch(() => {})
    return () => { live = false }
  }, [buyerId])

  if (!badge) return null
  // Seeded demonstration records must never read as a real platform review.
  const demo = badge.demo_seed === true
  const tone = demo ? 'neutral' : (TONE[badge.status] || 'neutral')
  const label = demo ? t('verification.badge.demoSeed') : (t(LABEL_KEY[badge.status]) || badge.label)
  const desc = demo ? t('verification.badge.demoSeedDesc') : (t(DESC_KEY[badge.status]) || badge.description)
  const emoji = demo ? '\ud83e\uddea' : EMOJI[badge.status]

  const toneClass = {
    neutral: 'text-ink/50 dark:text-paper/50',
    info: 'text-blue-700 dark:text-blue-400',
    success: 'text-emerald-700 dark:text-emerald-400',
    warning: 'text-red-600 dark:text-red-400',
  }[tone]

  return (
    <span
      title={desc}
      className={`inline-flex items-center gap-1 text-xs font-semibold ${toneClass} ${className}`}
    >
      <span aria-hidden="true">{emoji}</span>
      {!compact && <span>{label}</span>}
    </span>
  )
}
