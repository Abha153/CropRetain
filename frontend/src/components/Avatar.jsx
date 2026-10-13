import React, { useState } from 'react'
import { getAvatarUrl } from '../utils/avatars'
import { useI18n } from '../i18n/I18nContext'

const SIZES = {
  sm: 'w-8 h-8 text-xs',
  md: 'w-11 h-11 text-sm',
  lg: 'w-14 h-14 text-2xl',
}

/**
 * Renders an individual farmer/buyer portrait when one is mapped for the
 * given identity, otherwise falls back to an initials circle. Never
 * renders the CropRetain logo -- that lives only in Layout's sidebar header
 * and the browser favicon/OG assets.
 *
 * @param {'farmer'|'buyer'} role
 * @param {string} name - farmer's name, or buyer's company_name
 * @param {'sm'|'md'|'lg'} size
 */
export default function Avatar({ role, name, size = 'md', className = '' }) {
  const { t } = useI18n()
  const [failed, setFailed] = useState(false)
  const src = getAvatarUrl(role, name)
  const sizeClasses = SIZES[size] || SIZES.md
  const label = name || t('avatar.defaultLabel')

  if (src && !failed) {
    return (
      <img
        src={src}
        alt={label}
        onError={() => setFailed(true)}
        className={`${sizeClasses} rounded-full object-cover flex-shrink-0 ${className}`}
      />
    )
  }

  const initial = (name || '?').trim()[0]?.toUpperCase() || '?'
  return (
    <div
      className={`${sizeClasses} rounded-full bg-forest text-paper flex items-center justify-center font-display font-bold flex-shrink-0 ${className}`}
      aria-label={label}
    >
      {initial}
    </div>
  )
}
