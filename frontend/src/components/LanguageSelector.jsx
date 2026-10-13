import React, { useState, useMemo } from 'react'
import { Globe } from 'lucide-react'
import { useI18n } from '../i18n/I18nContext'

function CapabilityDots({ lang }) {
  const { t } = useI18n()
  return (
    <span className="flex items-center gap-1 text-[10px] shrink-0">
      {lang.ui ? <span title={t('language.interfaceTranslated')} className="text-emerald-600 dark:text-emerald-400">✍️</span> : <span title={t('language.interfaceUnavailable')} className="text-stone-300 dark:text-white/20">✍️</span>}
      {lang.stt === 'device' ? <span title={t('language.voiceInputAvailable')} className="text-emerald-600 dark:text-emerald-400">🎤</span> : <span title={t('language.voiceInputUnavailable')} className="text-stone-300 dark:text-white/20">🎤</span>}
      {lang.tts === 'device' ? <span title={t('language.voiceOutputAvailable')} className="text-emerald-600 dark:text-emerald-400">🔊</span> : <span title={t('language.voiceOutputUnavailable')} className="text-stone-300 dark:text-white/20">🔊</span>}
    </span>
  )
}

export default function LanguageSelector({ compact = false }) {
  const { code, setLanguage, languageInfo, languages, t } = useI18n()
  const supportedLanguages = languages.filter(language => language.ui)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = q
      ? supportedLanguages.filter(l => l.native.toLowerCase().includes(q) || l.english.toLowerCase().includes(q))
      : supportedLanguages
    return {
      indian: list.filter(l => l.family === 'indian'),
      international: list.filter(l => l.family === 'international'),
    }
  }, [supportedLanguages, query])

  function choose(langCode) {
    setLanguage(langCode)
    setOpen(false)
    setQuery('')
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className={`flex items-center gap-2 rounded-lg border transition-colors ${compact ? 'px-2.5 py-1.5 text-xs' : 'px-3 py-2 text-sm'} ${open ? 'border-marigold bg-marigold/10' : 'border-black/10 dark:border-white/15 bg-white dark:bg-white/5 hover:bg-wheat dark:bg-white/5'}`}
        aria-label={`${t('language')}: ${languageInfo.native}. ${t('language.change')}`}
        aria-expanded={open}
      >
        <span className="inline-flex h-4 w-4 items-center justify-center"><Globe size={14} /></span>
        <span className="font-medium">{languageInfo.native}</span>
        {!languageInfo.ui && <span className="text-[10px] text-stone-400">({t('language.beta')})</span>}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto bg-white dark:bg-white/5 rounded-xl shadow-lg border border-black/10 dark:border-white/15 z-40 p-3">
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder={t('searchLanguage')}
              className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm mb-3 bg-white dark:bg-white/5 dark:text-paper"
            />
            <div className="text-[11px] font-semibold text-ink/40 dark:text-paper/40 uppercase tracking-wide px-1 mb-1">{t('indianLanguages')}</div>
            <div className="space-y-0.5 mb-3">
              {filtered.indian.map(l => (
                <button
                  key={l.code}
                  onClick={() => choose(l.code)}
                  className={`w-full flex items-center justify-between px-2 py-1.5 rounded-lg text-sm hover:bg-wheat dark:bg-white/5 transition-colors ${l.code === code ? 'bg-marigold/15 font-semibold' : ''}`}
                >
                  <span className="flex items-center gap-2">
                    <span>{l.native}</span>
                    <span className="text-xs text-ink/40 dark:text-paper/40">{l.english}</span>
                  </span>
                  <CapabilityDots lang={l} />
                </button>
              ))}
            </div>
            <div className="text-[11px] font-semibold text-ink/40 dark:text-paper/40 uppercase tracking-wide px-1 mb-1">{t('internationalLanguages')}</div>
            <div className="space-y-0.5">
              {filtered.international.map(l => (
                <button
                  key={l.code}
                  onClick={() => choose(l.code)}
                  className={`w-full flex items-center justify-between px-2 py-1.5 rounded-lg text-sm hover:bg-wheat dark:bg-white/5 transition-colors ${l.code === code ? 'bg-marigold/15 font-semibold' : ''}`}
                >
                  <span className="flex items-center gap-2">
                    <span>{l.native}</span>
                    <span className="text-xs text-ink/40 dark:text-paper/40">{l.english}</span>
                  </span>
                  <CapabilityDots lang={l} />
                </button>
              ))}
            </div>
            <div className="border-t border-black/5 dark:border-white/10 mt-3 pt-2 px-1 text-[10px] text-ink/40 dark:text-paper/40 leading-relaxed">
              {t('language.legendPrefix')} {t('language.capabilities')}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
