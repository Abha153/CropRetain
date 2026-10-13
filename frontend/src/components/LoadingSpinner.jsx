import React from 'react'
import { useI18n } from '../i18n/I18nContext'

export default function LoadingSpinner({ label }) {
  const { t } = useI18n()
  return (
    <div className="flex flex-col items-center justify-center py-16 text-forest/70">
      <div className="w-8 h-8 border-4 border-forest/20 border-t-forest rounded-full animate-spin mb-3" />
      <p className="font-mono-data text-sm">{label || t('common.loading')}</p>
    </div>
  )
}
