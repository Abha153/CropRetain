"""
Language-neutral intent + entity extraction.

This is the heart of the "language should not duplicate business logic"
requirement: no matter which of the supported languages the text comes in,
`parse()` always returns the SAME shape:

    {
      "intent": "MARKET_RECOMMENDATION",
      "crop": "Soybean" | None,
      "quantity_kg": 2000.0 | None,
      "location": "Bilaspur" | None,
      "language": "mr",
      "missing": ["location"],   # entities we could NOT extract -- caller
                                  # must ask the user, never guess
    }

Everything downstream (the recommendation engine, market comparison, etc.)
only ever sees canonical English crop/market names and plain numbers --
it has no idea what language the user typed in.
"""
import re

from app.i18n.crop_terms import find_crop_in_text
from app.i18n.location_terms import find_market_in_text
from app.i18n.intents import detect_intent

# Union of "quintal" and "kg" words across every supported language. Checking
# the union (rather than only the declared language's words) is deliberate:
# code-mixing is extremely common in real farmer speech ("20 quintal sona"),
# and it costs nothing to also recognize another language's unit word.
QUINTAL_WORDS = [
    "quintal", "quintals", "क्विंटल", "কুইন্টাল", "குவிண்டல்", "క్వింటాల్",
    "ક્વિન્ટલ", "ಕ್ವಿಂಟಲ್", "ക്വിന്റൽ", "ਕੁਇੰਟਲ", "କ୍ୱିଣ୍ଟାଲ", "کوئنٹل",
]
# 1 metric ton/tonne = 1000 kg. Checked before KG_WORDS below so "1 ton"
# never accidentally matches a bare "t" fragment of another unit.
TON_WORDS = [
    "tonne", "tonnes", "ton", "tons", "टन", "টন", "டன்", "టన్ను",
    "ટન", "ಟನ್", "ടൺ", "ਟਨ", "ଟନ", "ٹن",
]
KG_WORDS = [
    "kg", "kgs", "kilo", "kilos", "किलो", "किग्रा", "কেজি", "கிலோ", "కిలో",
    "કિલો", "ಕೆಜಿ", "കിലോ", "ਕਿਲੋ", "କିଲୋ", "কিলো", "کلو",
]

_NUM_RE = r"(\d+(?:\.\d+)?)"


def _extract_quantity_kg(text: str):
    lowered = text.lower()
    for word in sorted(QUINTAL_WORDS, key=len, reverse=True):
        m = re.search(_NUM_RE + r"\s*" + re.escape(word.lower()), lowered)
        if m:
            return float(m.group(1)) * 100  # 1 quintal = 100 kg
    for word in sorted(TON_WORDS, key=len, reverse=True):
        m = re.search(_NUM_RE + r"\s*" + re.escape(word.lower()), lowered)
        if m:
            return float(m.group(1)) * 1000  # 1 tonne = 1000 kg
    for word in sorted(KG_WORDS, key=len, reverse=True):
        m = re.search(_NUM_RE + r"\s*" + re.escape(word.lower()), lowered)
        if m:
            return float(m.group(1))
    return None


def parse(text: str, language: str = "en", known_crop: str = None,
          known_quantity_kg: float = None, known_location: str = None) -> dict:
    """
    Parse free text into a canonical intent + entities.

    `known_*` lets a caller carry forward entities already established
    earlier in the conversation (see routers/assistant.py) so that, e.g.,
    switching language mid-conversation doesn't forget the crop the user
    already mentioned.
    """
    text = text or ""
    intent = detect_intent(text, language)

    crop = find_crop_in_text(text) or known_crop
    quantity_kg = _extract_quantity_kg(text) or known_quantity_kg
    location = find_market_in_text(text) or known_location

    missing = []
    if crop is None:
        missing.append("crop")
    if location is None:
        missing.append("location")

    return {
        "intent": intent,
        "crop": crop,
        "quantity_kg": quantity_kg,
        "location": location,
        "language": language,
        "missing": missing,
    }
