// Frontend mirror of the backend language capability matrix
// (app/i18n/languages.py). Kept as a static module so the language
// selector can render instantly without a network round-trip; the backend
// remains the source of truth for assistant NLU capability and is fetched
// separately (see api.assistantLanguages()) to confirm AI support per language.
export const FULLY_SUPPORTED = ["en", "hi", "mr", "bn", "ta", "te", "gu", "kn", "ml", "pa", "or", "as", "ur", "bho", "mai"]

export const LANGUAGES = [
  { code: "en", native: "English", english: "English", rtl: false, ui: true, stt: "device", tts: "device", family: "indian" },
  { code: "hi", native: "हिन्दी", english: "Hindi", rtl: false, ui: true, stt: "device", tts: "device", family: "indian" },
  { code: "mr", native: "मराठी", english: "Marathi", rtl: false, ui: true, stt: "device", tts: "device", family: "indian" },
  { code: "bn", native: "বাংলা", english: "Bengali", rtl: false, ui: true, stt: "device", tts: "device", family: "indian" },
  { code: "ta", native: "தமிழ்", english: "Tamil", rtl: false, ui: true, stt: "device", tts: "device", family: "indian" },
  { code: "te", native: "తెలుగు", english: "Telugu", rtl: false, ui: true, stt: "device", tts: "device", family: "indian" },
  { code: "gu", native: "ગુજરાતી", english: "Gujarati", rtl: false, ui: true, stt: "device", tts: "device", family: "indian" },
  { code: "kn", native: "ಕನ್ನಡ", english: "Kannada", rtl: false, ui: true, stt: "device", tts: "device", family: "indian" },
  { code: "ml", native: "മലയാളം", english: "Malayalam", rtl: false, ui: true, stt: "device", tts: "device", family: "indian" },
  { code: "pa", native: "ਪੰਜਾਬੀ", english: "Punjabi", rtl: false, ui: true, stt: "device", tts: "device", family: "indian" },
  { code: "or", native: "ଓଡ଼ିଆ", english: "Odia", rtl: false, ui: true, stt: "unsupported", tts: "device", family: "indian" },
  { code: "as", native: "অসমীয়া", english: "Assamese", rtl: false, ui: true, stt: "unsupported", tts: "device", family: "indian" },
  { code: "ur", native: "اردو", english: "Urdu", rtl: true, ui: true, stt: "device", tts: "device", family: "indian" },
  { code: "bho", native: "भोजपुरी", english: "Bhojpuri", rtl: false, ui: true, stt: "unsupported", tts: "device", family: "indian" },
  { code: "mai", native: "मैथिली", english: "Maithili", rtl: false, ui: true, stt: "unsupported", tts: "device", family: "indian" },

  { code: "sa", native: "संस्कृतम्", english: "Sanskrit", rtl: false, ui: false, stt: "unsupported", tts: "unsupported", family: "indian" },
  { code: "ne", native: "नेपाली", english: "Nepali", rtl: false, ui: false, stt: "device", tts: "device", family: "indian" },
  { code: "kok", native: "कोंकणी", english: "Konkani", rtl: false, ui: false, stt: "unsupported", tts: "unsupported", family: "indian" },
  { code: "ks", native: "کٲشُر", english: "Kashmiri", rtl: true, ui: false, stt: "unsupported", tts: "unsupported", family: "indian" },
  { code: "sd", native: "سنڌي", english: "Sindhi", rtl: true, ui: false, stt: "unsupported", tts: "unsupported", family: "indian" },
  { code: "mni", native: "মৈতৈলোন্", english: "Manipuri (Meitei)", rtl: false, ui: false, stt: "unsupported", tts: "unsupported", family: "indian" },
  { code: "brx", native: "बड़ो", english: "Bodo", rtl: false, ui: false, stt: "unsupported", tts: "unsupported", family: "indian" },
  { code: "doi", native: "डोगरी", english: "Dogri", rtl: false, ui: false, stt: "unsupported", tts: "unsupported", family: "indian" },
  { code: "sat", native: "ᱥᱟᱱᱛᱟᱲᱤ", english: "Santali", rtl: false, ui: false, stt: "unsupported", tts: "unsupported", family: "indian" },

  { code: "zh", native: "中文", english: "Mandarin Chinese", rtl: false, ui: false, stt: "device", tts: "device", family: "international" },
  { code: "ja", native: "日本語", english: "Japanese", rtl: false, ui: false, stt: "device", tts: "device", family: "international" },
  { code: "ko", native: "한국어", english: "Korean", rtl: false, ui: false, stt: "device", tts: "device", family: "international" },
  { code: "es", native: "Español", english: "Spanish", rtl: false, ui: false, stt: "device", tts: "device", family: "international" },
  { code: "fr", native: "Français", english: "French", rtl: false, ui: false, stt: "device", tts: "device", family: "international" },
  { code: "de", native: "Deutsch", english: "German", rtl: false, ui: false, stt: "device", tts: "device", family: "international" },
  { code: "pt", native: "Português", english: "Portuguese", rtl: false, ui: false, stt: "device", tts: "device", family: "international" },
  { code: "ar", native: "العربية", english: "Arabic", rtl: true, ui: false, stt: "device", tts: "device", family: "international" },
  { code: "ru", native: "Русский", english: "Russian", rtl: false, ui: false, stt: "device", tts: "device", family: "international" },
  { code: "id", native: "Bahasa Indonesia", english: "Indonesian", rtl: false, ui: false, stt: "device", tts: "device", family: "international" },
  { code: "vi", native: "Tiếng Việt", english: "Vietnamese", rtl: false, ui: false, stt: "device", tts: "device", family: "international" },
  { code: "th", native: "ไทย", english: "Thai", rtl: false, ui: false, stt: "device", tts: "device", family: "international" },
  { code: "tr", native: "Türkçe", english: "Turkish", rtl: false, ui: false, stt: "device", tts: "device", family: "international" },
  { code: "it", native: "Italiano", english: "Italian", rtl: false, ui: false, stt: "device", tts: "device", family: "international" },
]

export const LANGUAGE_BY_CODE = Object.fromEntries(LANGUAGES.map(l => [l.code, l]))

export function getLanguage(code) {
  return LANGUAGE_BY_CODE[code] || LANGUAGE_BY_CODE.en
}

// BCP-47 locale tags for Web Speech API, matched to app.i18n.languages.py
export const SPEECH_LOCALES = {
  en: "en-IN", hi: "hi-IN", mr: "mr-IN", bn: "bn-IN", ta: "ta-IN", te: "te-IN",
  gu: "gu-IN", kn: "kn-IN", ml: "ml-IN", pa: "pa-IN", ur: "ur-IN",
  ne: "ne-NP", zh: "zh-CN", ja: "ja-JP", ko: "ko-KR", es: "es-ES", fr: "fr-FR",
  de: "de-DE", pt: "pt-PT", ar: "ar-SA", ru: "ru-RU", id: "id-ID", vi: "vi-VN",
  th: "th-TH", tr: "tr-TR", it: "it-IT",
}
