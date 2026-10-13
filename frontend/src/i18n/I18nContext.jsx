import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react'
import { LANGUAGES, getLanguage, FULLY_SUPPORTED } from './languages'

const I18nContext = createContext(null)

// See the Phase-4 comment on `t()` below for what these do and why they
// never change production rendering by default.
function isDebugI18nMode() {
  try {
    return new URLSearchParams(window.location.search).get('i18nDebug') === '1'
  } catch (e) {
    return false
  }
}

function recordMissingTranslation(lang, key, hadEnglishFallback) {
  try {
    if (!window.__cropretainI18nMissing) window.__cropretainI18nMissing = new Map()
    const store = window.__cropretainI18nMissing
    if (!store.has(lang)) store.set(lang, new Set())
    const set = store.get(lang)
    const isNew = !set.has(key)
    set.add(key)
    if (isNew && typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.warn(
        `[i18n] missing key "${key}" for language "${lang}"` +
        (hadEnglishFallback ? ' (showing English fallback)' : ' (no English value either -- showing raw key)')
      )
    }
  } catch (e) {
    // Diagnostics must never break rendering.
  }
}

// Lazy-loaded, cached per language so we never ship/parse translation JSON
// the user hasn't selected (performance requirement from the spec).
const translationCache = {}
async function loadTranslations(code) {
  if (translationCache[code]) return translationCache[code]
  if (!FULLY_SUPPORTED.includes(code)) {
    translationCache[code] = {} // no shipped resource -- will fall back to English per-key
    return translationCache[code]
  }
  try {
    const mod = await import(`./translations/${code}.json`)
    translationCache[code] = mod.default || mod
  } catch (e) {
    translationCache[code] = {}
  }
  return translationCache[code]
}

export function I18nProvider({ children }) {
  const [code, setCode] = useState(() => {
    try { return localStorage.getItem('cropretain_language') || 'en' } catch (e) { return 'en' }
  })
  const [dict, setDict] = useState({})
  const [enDict, setEnDict] = useState({})
  const [loading, setLoading] = useState(true)

  // English is always loaded as the fallback dictionary
  useEffect(() => { loadTranslations('en').then(setEnDict) }, [])

  useEffect(() => {
    setLoading(true)
    loadTranslations(code).then(d => { setDict(d); setLoading(false) })
    try { localStorage.setItem('cropretain_language', code) } catch (e) {}
  }, [code])

  const setLanguage = useCallback((newCode) => {
    setCode(newCode)
  }, [])

  // t(key, params?) -- looks up `key` in the active language, falling back to
  // English and then to the raw key. When `params` is supplied, replaces every
  // {{paramName}} placeholder in the resolved string with the given value, so
  // callers never need to hand-roll string concatenation/interpolation
  // (which would bypass per-language word order and formatting).
  //
  // MISSING-TRANSLATION DIAGNOSTICS (Phase 4): a silent fallback from the
  // selected language to English (or, worse, to the raw key) is exactly
  // the failure mode this product requirement forbids going unnoticed.
  // This does NOT change end-user-visible behavior in normal use --
  // production still shows the graceful English/key fallback, because a
  // visibly broken string in front of a real farmer is worse than an
  // English one. Instead:
  //   - every miss is recorded in `window.__cropretainI18nMissing` (a
  //     Map<lang, Set<key>>) so it can be inspected or exported at any
  //     time, in any environment, without changing what's rendered.
  //   - in dev (import.meta.env.DEV) each new miss is also console.warn'd
  //     once, so it surfaces immediately while building/testing a page.
  //   - appending ?i18nDebug=1 to the URL renders missing entries as
  //     visible "⚠ missing:key.path" markers instead of the silent
  //     fallback, for an explicit, opt-in "find every gap" pass -- this
  //     is the "obvious diagnostic result" mode, never the default.
  const t = useCallback((key, params) => {
    const hasSelected = Object.prototype.hasOwnProperty.call(dict, key)
    const hasEnglish = Object.prototype.hasOwnProperty.call(enDict, key)
    if (!hasSelected) {
      recordMissingTranslation(code, key, hasEnglish)
    }
    let raw
    if (hasSelected) raw = dict[key]
    else if (hasEnglish) raw = enDict[key]
    else raw = key

    if (!hasSelected && isDebugI18nMode()) {
      raw = `⚠ missing:${key}`
    }

    if (!params) return raw
    return Object.keys(params).reduce(
      (str, paramKey) => str.replace(new RegExp(`\\{\\{\\s*${paramKey}\\s*\\}\\}`, 'g'), params[paramKey]),
      raw
    )
  }, [dict, enDict, code])

  const languageInfo = useMemo(() => getLanguage(code), [code])
  const isFullySupported = FULLY_SUPPORTED.includes(code)

  useEffect(() => {
    document.documentElement.lang = code
    document.documentElement.dir = languageInfo.rtl ? 'rtl' : 'ltr'
  }, [code, languageInfo])

  const value = {
    code, setLanguage, t, loading,
    languageInfo, isFullySupported,
    languages: LANGUAGES,
    rtl: languageInfo.rtl,
  }

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used within I18nProvider')
  return ctx
}

// i18n Phase 6 helper -- translate a backend error that was migrated to
// the AppError/`code` architecture (see backend/app/errors.py), falling
// back to the original English `detail` message for the ~200 endpoints
// not yet migrated. Call as `translateApiError(t, err)` in a catch block
// instead of `err.message`. NOT YET WIRED into every page's catch block
// (see I18N_STATUS.md) -- this is the ready-to-use building block, not a
// claim that every page already uses it.
export function translateApiError(t, err) {
  if (err && err.code) {
    const key = `errors.${err.code}`
    const translated = t(key)
    if (translated !== key) return translated
  }
  return (err && err.message) || t('errors.generic')
}
