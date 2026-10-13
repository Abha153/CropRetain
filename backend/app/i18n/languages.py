"""
Global language capability matrix for CropRetain.

This is the single source of truth for "what does CropRetain actually support
for language X" -- UI translation, text-based AI understanding, speech-to-
text, text-to-speech, and free-text translation. Nothing here is aspirational:
`ui`, `assistant_nlu` and `response_templates` are True only for languages we
have actually shipped resources for (see translations/*.json on the frontend
and templates.py / crop_terms.py on the backend). `stt` / `tts` are marked
"device" because the browser Web Speech API's actual per-language support
depends on the user's OS/browser voice packs, which the server cannot know in
advance -- the frontend re-checks real STT/TTS availability at runtime
(see frontend/src/i18n/speech.js and tts.js) and never claims support that
isn't actually there.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LanguageInfo:
    code: str                 # BCP-47-ish app-internal code
    native_name: str
    english_name: str
    speech_locale: Optional[str]   # best-effort locale tag for Web Speech API
    rtl: bool = False
    ui: bool = False               # full UI translation shipped
    assistant_nlu: bool = False    # backend can extract intent/entities in this language
    response_templates: bool = False  # backend can generate a native-language answer
    stt: str = "unsupported"       # "device" | "unsupported"  (never a blanket "yes")
    tts: str = "device"            # "device" | "unsupported"  (checked live client-side)
    family: str = "indian"         # "indian" | "international"


# 15 languages with full UI + assistant NLU + native response templates.
FULLY_SUPPORTED = ["en", "hi", "mr", "bn", "ta", "te", "gu", "kn", "ml", "pa", "or", "as", "ur", "bho", "mai"]

LANGUAGE_CATALOG: list[LanguageInfo] = [
    LanguageInfo("en", "English", "English", "en-IN", ui=True, assistant_nlu=True, response_templates=True, stt="device", family="indian"),
    LanguageInfo("hi", "हिन्दी", "Hindi", "hi-IN", ui=True, assistant_nlu=True, response_templates=True, stt="device"),
    LanguageInfo("mr", "मराठी", "Marathi", "mr-IN", ui=True, assistant_nlu=True, response_templates=True, stt="device"),
    LanguageInfo("bn", "বাংলা", "Bengali", "bn-IN", ui=True, assistant_nlu=True, response_templates=True, stt="device"),
    LanguageInfo("ta", "தமிழ்", "Tamil", "ta-IN", ui=True, assistant_nlu=True, response_templates=True, stt="device"),
    LanguageInfo("te", "తెలుగు", "Telugu", "te-IN", ui=True, assistant_nlu=True, response_templates=True, stt="device"),
    LanguageInfo("gu", "ગુજરાતી", "Gujarati", "gu-IN", ui=True, assistant_nlu=True, response_templates=True, stt="device"),
    LanguageInfo("kn", "ಕನ್ನಡ", "Kannada", "kn-IN", ui=True, assistant_nlu=True, response_templates=True, stt="device"),
    LanguageInfo("ml", "മലയാളം", "Malayalam", "ml-IN", ui=True, assistant_nlu=True, response_templates=True, stt="device"),
    LanguageInfo("pa", "ਪੰਜਾਬੀ", "Punjabi", "pa-IN", ui=True, assistant_nlu=True, response_templates=True, stt="device"),
    LanguageInfo("or", "ଓଡ଼ିଆ", "Odia", "or-IN", ui=True, assistant_nlu=True, response_templates=True, stt="unsupported"),
    LanguageInfo("as", "অসমীয়া", "Assamese", "as-IN", ui=True, assistant_nlu=True, response_templates=True, stt="unsupported"),
    LanguageInfo("ur", "اردو", "Urdu", "ur-IN", rtl=True, ui=True, assistant_nlu=True, response_templates=True, stt="device"),
    LanguageInfo("bho", "भोजपुरी", "Bhojpuri", None, ui=True, assistant_nlu=True, response_templates=True, stt="unsupported"),
    LanguageInfo("mai", "मैथिली", "Maithili", None, ui=True, assistant_nlu=True, response_templates=True, stt="unsupported"),

    # Remaining Indian languages: selectable, honestly marked as UI/AI not yet
    # translated (falls back to English text) but on the roadmap. No fake claims.
    LanguageInfo("sa", "संस्कृतम्", "Sanskrit", None, stt="unsupported", tts="unsupported"),
    LanguageInfo("ne", "नेपाली", "Nepali", "ne-NP", stt="unsupported"),
    LanguageInfo("kok", "कोंकणी", "Konkani", None, stt="unsupported", tts="unsupported"),
    LanguageInfo("ks", "کٲشُر", "Kashmiri", None, rtl=True, stt="unsupported", tts="unsupported"),
    LanguageInfo("sd", "سنڌي", "Sindhi", None, rtl=True, stt="unsupported", tts="unsupported"),
    LanguageInfo("mni", "মৈতৈলোন্", "Manipuri (Meitei)", None, stt="unsupported", tts="unsupported"),
    LanguageInfo("brx", "बड़ो", "Bodo", None, stt="unsupported", tts="unsupported"),
    LanguageInfo("doi", "डोगरी", "Dogri", None, stt="unsupported", tts="unsupported"),
    LanguageInfo("sat", "ᱥᱟᱱᱛᱟᱲᱤ", "Santali", None, stt="unsupported", tts="unsupported"),

    # International languages: capability-listed for the global-extensibility
    # requirement. UI/assistant not yet shipped -- selectable, honest fallback.
    LanguageInfo("zh", "中文", "Mandarin Chinese", "zh-CN", stt="device", family="international"),
    LanguageInfo("ja", "日本語", "Japanese", "ja-JP", stt="device", family="international"),
    LanguageInfo("ko", "한국어", "Korean", "ko-KR", stt="device", family="international"),
    LanguageInfo("es", "Español", "Spanish", "es-ES", stt="device", family="international"),
    LanguageInfo("fr", "Français", "French", "fr-FR", stt="device", family="international"),
    LanguageInfo("de", "Deutsch", "German", "de-DE", stt="device", family="international"),
    LanguageInfo("pt", "Português", "Portuguese", "pt-PT", stt="device", family="international"),
    LanguageInfo("ar", "العربية", "Arabic", "ar-SA", rtl=True, stt="device", family="international"),
    LanguageInfo("ru", "Русский", "Russian", "ru-RU", stt="device", family="international"),
    LanguageInfo("id", "Bahasa Indonesia", "Indonesian", "id-ID", stt="device", family="international"),
    LanguageInfo("vi", "Tiếng Việt", "Vietnamese", "vi-VN", stt="device", family="international"),
    LanguageInfo("th", "ไทย", "Thai", "th-TH", stt="device", family="international"),
    LanguageInfo("tr", "Türkçe", "Turkish", "tr-TR", stt="device", family="international"),
    LanguageInfo("it", "Italiano", "Italian", "it-IT", stt="device", family="international"),
]

LANGUAGE_BY_CODE = {l.code: l for l in LANGUAGE_CATALOG}
DEFAULT_LANGUAGE = "en"


def get_language(code: str) -> LanguageInfo:
    return LANGUAGE_BY_CODE.get(code, LANGUAGE_BY_CODE[DEFAULT_LANGUAGE])


def catalog_as_dicts():
    out = []
    for l in LANGUAGE_CATALOG:
        out.append({
            "code": l.code, "native_name": l.native_name, "english_name": l.english_name,
            "speech_locale": l.speech_locale, "rtl": l.rtl, "family": l.family,
            "capabilities": {
                "ui_translation": l.ui,
                "assistant_understanding": l.assistant_nlu,
                "native_response": l.response_templates,
                "speech_to_text": l.stt,   # "device" = available if browser/OS supports it, checked live
                "text_to_speech": l.tts,   # checked live against speechSynthesis.getVoices()
                "text_input": True,        # every listed language can always be typed
            },
        })
    return out
