// SpeechProvider abstraction (STT). Currently ships one real provider --
// the browser's native Web Speech API -- behind an interface so a cloud
// provider can be added later without changing calling code.
import { SPEECH_LOCALES } from './languages'

// PRODUCT DECISION (not just a technical limitation): CropRetain's speech
// RECOGNITION (voice input) is intentionally limited to English and Hindi.
// The underlying Web Speech API technically accepts other locale strings
// (Marathi, Bengali, etc.), but recognition quality/reliability for most
// Indian regional languages is inconsistent across browsers/OSes in
// practice. Rather than exposing a microphone button that silently
// produces poor or empty transcriptions, CropRetain only offers voice INPUT
// for the two languages it can reliably support, and is explicit about
// this everywhere in the UI (see AskAssistant.jsx). Text input and UI
// translation remain available in all supported languages regardless --
// this restriction is voice-input-specific only.
export const VOICE_INPUT_SUPPORTED_LANGUAGES = ['en', 'hi']

export function isVoiceInputSupportedForLanguage(languageCode) {
  return VOICE_INPUT_SUPPORTED_LANGUAGES.includes(languageCode)
}

class BrowserSpeechProvider {
  get supported() {
    return typeof window !== 'undefined' && !!(window.SpeechRecognition || window.webkitSpeechRecognition)
  }

  // The browser API does not expose a queryable list of supported
  // recognition languages, so we can't claim certainty beyond "the API
  // exists". Actual per-language accuracy depends on the OS/browser voice
  // engine and is confirmed only by trying -- errors are surfaced via
  // onUnsupported below rather than silently failing.
  listen({ languageCode, onResult, onError, onStart, onEnd }) {
    if (!this.supported) {
      onError?.({ type: 'unsupported-browser', message: 'Speech recognition is not available in this browser.' })
      return null
    }
    if (!isVoiceInputSupportedForLanguage(languageCode)) {
      onError?.({
        type: 'language-not-offered',
        message: 'Voice input is currently available in Hindi and English only. Please switch voice language or type your request.',
      })
      return null
    }
    const locale = SPEECH_LOCALES[languageCode] || 'en-IN'
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    const recognition = new SpeechRecognition()
    recognition.lang = locale
    recognition.interimResults = false
    recognition.maxAlternatives = 1

    // Safety net: some browser/OS combinations occasionally never fire any
    // event at all after recognition.start() (a known Web Speech API flake).
    // Without this, the UI could show "Listening..." forever. Force-stop
    // and surface a timeout error if nothing has happened within 10s.
    let settled = false
    const hardTimeout = setTimeout(() => {
      if (settled) return
      settled = true
      try { recognition.abort() } catch (e) { /* already stopped */ }
      onError?.({ type: 'timeout', message: 'Recognition timed out with no response. Please try again.' })
      onEnd?.()
    }, 10000)

    function markSettled() {
      settled = true
      clearTimeout(hardTimeout)
    }

    recognition.onstart = () => onStart?.()
    recognition.onend = () => { markSettled(); onEnd?.() }
    recognition.onresult = (event) => {
      markSettled()
      const transcript = event.results[0][0].transcript
      if (!transcript || !transcript.trim()) {
        onError?.({ type: 'empty-result', message: 'No speech was recognized. Please try again or type your request.' })
        return
      }
      onResult?.(transcript)
    }
    recognition.onerror = (event) => {
      markSettled()
      const map = {
        'not-allowed': { type: 'permission-denied', message: 'Microphone permission was denied. Please allow microphone access, or type your request instead.' },
        'no-speech': { type: 'no-speech', message: 'No speech was detected. Please try again.' },
        'network': { type: 'network', message: 'A network error interrupted speech recognition. Please try again or type your request.' },
        'language-not-supported': { type: 'language-not-supported', message: `Speech recognition may not support ${locale} on this device.` },
        'aborted': { type: 'cancelled', message: 'Voice input was cancelled.' },
        'audio-capture': { type: 'no-microphone', message: 'No microphone was found on this device.' },
      }
      onError?.(map[event.error] || { type: event.error || 'unknown', message: 'Speech recognition failed. Please type instead.' })
    }

    try {
      recognition.start()
    } catch (e) {
      markSettled()
      onError?.({ type: 'start-failed', message: 'Could not start the microphone.' })
      return null
    }
    return recognition // caller can call .stop() / .abort()
  }
}

const providers = {
  browser: new BrowserSpeechProvider(),
}

export function getSpeechProvider(name = 'browser') {
  return providers[name]
}

export function isSpeechSupportedAtAll() {
  return getSpeechProvider('browser').supported
}
