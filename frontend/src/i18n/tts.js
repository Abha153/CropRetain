// TTSProvider abstraction. Ships the browser's native SpeechSynthesis API.
// Unlike STT, the browser DOES expose a real, queryable voice list, so we
// can honestly check live whether a given language has a voice installed
// on this specific device -- no static claim, no guessing.
import { SPEECH_LOCALES } from './languages'

// --- Centralized voice-list manager (module-level, single source of truth) ---
//
// BUG THIS FIXES (found in an earlier pass, and again in review): using
// `speechSynthesis.onvoiceschanged = fn` is an ASSIGNMENT, not a
// subscription -- only one handler can ever be attached at a time, so any
// second piece of code that also assigns `onvoiceschanged` silently
// overwrites the first one. A previous fix introduced a proper subscriber
// list but *also* left behind an old `ensureVoicesLoaded()` helper that
// still did `onvoiceschanged = ...`, which could stomp on the new
// subscription depending on call order. This version uses
// `addEventListener('voiceschanged', ...)` (a real subscription, supports
// multiple listeners) and removes the obsolete one-shot helper entirely --
// there is now exactly one listener, attached once, that fans out to every
// subscriber.
let listenerAttached = false
const subscribers = new Set()

function notifyAll() {
  subscribers.forEach((cb) => {
    try { cb() } catch (e) { /* one subscriber's error must not break others */ }
  })
}

function attachGlobalListener() {
  if (listenerAttached || typeof window === 'undefined' || !window.speechSynthesis) return
  listenerAttached = true
  window.speechSynthesis.addEventListener('voiceschanged', notifyAll)
}

/**
 * Subscribe to the device's voice list changing (voices frequently load
 * asynchronously, sometimes well after page load -- see BrowserTTSProvider
 * below). Returns an unsubscribe function; always call it on unmount to
 * avoid leaking listeners.
 */
export function subscribeToVoicesChanged(callback) {
  attachGlobalListener()
  subscribers.add(callback)
  return () => subscribers.delete(callback)
}

function normalizeLangTag(tag) {
  return (tag || '').toLowerCase().replace(/_/g, '-')
}

class BrowserTTSProvider {
  get supported() {
    return typeof window !== 'undefined' && !!window.speechSynthesis
  }

  getVoicesForLanguage(languageCode) {
    if (!this.supported) return []
    const locale = normalizeLangTag(SPEECH_LOCALES[languageCode] || languageCode)
    const prefix = locale.split('-')[0]
    const voices = window.speechSynthesis.getVoices() || []
    if (voices.length === 0) return []

    // 1) exact locale match (e.g. "mr-in" === "mr-in")
    const exact = voices.filter(v => normalizeLangTag(v.lang) === locale)
    if (exact.length > 0) return exact

    // 2) language-prefix match -- covers "mr_IN" vs "mr-IN" tag-style
    //    inconsistencies across browsers/OSes, and regional/engine suffixes
    //    like "mr-in-x-marx"
    const byPrefix = voices.filter(v => normalizeLangTag(v.lang).split('-')[0] === prefix)
    if (byPrefix.length > 0) return byPrefix

    // 3) last-resort fallback: a handful of Android/Chrome OEM builds
    //    mislabel `lang` but include the language's English name in the
    //    voice name -- only tried if 1-2 found nothing.
    const englishName = { mr: 'marathi', hi: 'hindi', bn: 'bengali', ta: 'tamil', te: 'telugu' }[prefix]
    if (englishName) {
      const byName = voices.filter(v => v.name.toLowerCase().includes(englishName))
      if (byName.length > 0) return byName
    }
    return []
  }

  isAvailable(languageCode) {
    return this.getVoicesForLanguage(languageCode).length > 0
  }

  speak(text, languageCode, { onEnd, onError } = {}) {
    if (!this.supported) {
      onError?.({ type: 'unsupported-browser', message: 'Text-to-speech is not available in this browser.' })
      return false
    }
    const voices = this.getVoicesForLanguage(languageCode)
    if (voices.length === 0) {
      onError?.({ type: 'voice-unavailable', message: 'No voice installed for this language on your device.' })
      return false
    }
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.voice = voices[0]
    utterance.lang = voices[0].lang
    utterance.onend = () => onEnd?.()
    utterance.onerror = () => onError?.({ type: 'speak-failed', message: 'Could not play the response.' })
    window.speechSynthesis.cancel() // stop anything currently speaking
    window.speechSynthesis.speak(utterance)
    return true
  }

  stop() {
    if (this.supported) window.speechSynthesis.cancel()
  }
}

const providers = { browser: new BrowserTTSProvider() }

export function getTTSProvider(name = 'browser') {
  return providers[name]
}
