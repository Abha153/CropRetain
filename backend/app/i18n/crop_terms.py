"""
Multilingual crop terminology layer.

CropRetain stores crops as a single canonical English entity name (see
app/mock_data/crops.py) everywhere in the database and business logic --
that canonical name is what market prices, listings, and the recommendation
engine key off. This module is the *display/understanding* layer on top of
that: it maps canonical crop -> localized alias words so that (a) the NLU
layer can recognize a crop mentioned in any supported language, and (b)
responses can show the crop's name in the user's language.

We do NOT machine-translate crop names on the fly -- these are curated,
standardized agricultural terms, which is safer and more accurate than a
generic translator for domain vocabulary.
"""

# canonical crop name -> {language_code: display name}
CROP_TRANSLATIONS = {
    "Tomato": {
        "en": "Tomato", "hi": "टमाटर", "mr": "टोमॅटो", "bn": "টমেটো", "ta": "தக்காளி",
        "te": "టమాటా", "gu": "ટામેટા", "kn": "ಟೊಮೇಟೊ", "ml": "തക്കാളി", "pa": "ਟਮਾਟਰ",
        "or": "ଟମାଟୋ", "as": "টমেটো", "ur": "ٹماٹر", "bho": "टमाटर", "mai": "टमाटर",
    },
    "Paddy (Rice)": {
        "en": "Paddy (Rice)", "hi": "धान", "mr": "भात", "bn": "ধান", "ta": "நெல்",
        "te": "వరి", "gu": "ડાંગર", "kn": "ಭತ್ತ", "ml": "നെല്ല്", "pa": "ਝੋਨਾ",
        "or": "ଧାନ", "as": "ধান", "ur": "دھان", "bho": "धान", "mai": "धान",
    },
    "Wheat": {
        "en": "Wheat", "hi": "गेहूं", "mr": "गहू", "bn": "গম", "ta": "கோதுமை",
        "te": "గోధుమ", "gu": "ઘઉં", "kn": "ಗೋಧಿ", "ml": "ഗോതമ്പ്", "pa": "ਕਣਕ",
        "or": "ଗହମ", "as": "গম", "ur": "گندم", "bho": "गेहूं", "mai": "गहूम",
    },
    "Potato": {
        "en": "Potato", "hi": "आलू", "mr": "बटाटा", "bn": "আলু", "ta": "உருளைக்கிழங்கு",
        "te": "బంగాళదుంప", "gu": "બટાકા", "kn": "ಆಲೂಗಡ್ಡೆ", "ml": "ഉരുളക്കിഴങ്ങ്", "pa": "ਆਲੂ",
        "or": "ଆଳୁ", "as": "আলু", "ur": "آلو", "bho": "आलू", "mai": "आलू",
    },
    "Onion": {
        "en": "Onion", "hi": "प्याज़", "mr": "कांदा", "bn": "পেঁয়াজ", "ta": "வெங்காயம்",
        "te": "ఉల్లిపాయ", "gu": "ડુંગળી", "kn": "ಈರುಳ್ಳಿ", "ml": "ഉള്ളി", "pa": "ਪਿਆਜ਼",
        "or": "ପିଆଜ", "as": "পিয়াঁজ", "ur": "پیاز", "bho": "प्याज", "mai": "पिआज",
    },
    "Soybean": {
        "en": "Soybean", "hi": "सोयाबीन", "mr": "सोयाबीन", "bn": "সয়াবিন", "ta": "சோயாபீன்",
        "te": "సోయాబీన్", "gu": "સોયાબીન", "kn": "ಸೋಯಾಬೀನ್", "ml": "സോയാബീൻ", "pa": "ਸੋਇਆਬੀਨ",
        "or": "ସୋୟାବିନ", "as": "সয়াবিন", "ur": "سویابین", "bho": "सोयाबीन", "mai": "सोयाबीन",
    },
    "Maize": {
        "en": "Maize", "hi": "मक्का", "mr": "मका", "bn": "ভুট্টা", "ta": "சோளம்",
        "te": "మొక్కజొన్న", "gu": "મકાઈ", "kn": "ಜೋಳ", "ml": "ചോളം", "pa": "ਮੱਕੀ",
        "or": "ମକା", "as": "ভুট্টা", "ur": "مکئی", "bho": "मकई", "mai": "मकई",
    },
    "Chana (Gram)": {
        "en": "Chana (Gram)", "hi": "चना", "mr": "हरभरा", "bn": "ছোলা", "ta": "கடலை",
        "te": "శనగ", "gu": "ચણા", "kn": "ಕಡಲೆ", "ml": "കടല", "pa": "ਛੋਲੇ",
        "or": "ଛୋଲା", "as": "ছোলা", "ur": "چنا", "bho": "चना", "mai": "चना",
    },
    "Groundnut": {
        "en": "Groundnut", "hi": "मूंगफली", "mr": "भुईमूग", "bn": "চীনাবাদাম", "ta": "நிலக்கடலை",
        "te": "వేరుశనగ", "gu": "મગફળી", "kn": "ಕಡಲೆಕಾಯಿ", "ml": "നിലക്കടല", "pa": "ਮੂੰਗਫਲੀ",
        "or": "ବାଦାମ", "as": "বাদাম", "ur": "مونگ پھلی", "bho": "मूंगफली", "mai": "मूंगफली",
    },
    "Sugarcane": {
        "en": "Sugarcane", "hi": "गन्ना", "mr": "ऊस", "bn": "আখ", "ta": "கரும்பு",
        "te": "చెరకు", "gu": "શેરડી", "kn": "ಕಬ್ಬು", "ml": "കരിമ്പ്", "pa": "ਗੰਨਾ",
        "or": "ଆଖୁ", "as": "কুঁহিয়ার", "ur": "گنا", "bho": "गन्ना", "mai": "ईख",
    },
}

# Reverse lookup index: alias text (lowercased) -> canonical crop name.
# Built once at import time so NLU crop matching is O(1) per token.
_ALIAS_INDEX: dict[str, str] = {}
for canonical, by_lang in CROP_TRANSLATIONS.items():
    for lang, alias in by_lang.items():
        _ALIAS_INDEX[alias.strip().lower()] = canonical
    # also index the bare canonical english word without the parenthetical, e.g. "Paddy", "Rice", "Chana", "Gram"
    for part in canonical.replace("(", "").replace(")", "").split():
        _ALIAS_INDEX.setdefault(part.strip().lower(), canonical)


def localized_crop_name(canonical: str, language: str) -> str:
    return CROP_TRANSLATIONS.get(canonical, {}).get(language, canonical)


def find_crop_in_text(text: str) -> str | None:
    """Scan free text for any known crop alias, in any supported language."""
    lowered = text.lower()
    # try longest aliases first to avoid partial-word false positives
    for alias in sorted(_ALIAS_INDEX.keys(), key=len, reverse=True):
        if alias and alias in lowered:
            return _ALIAS_INDEX[alias]
    return None
