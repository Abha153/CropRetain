"""
Location alias resolution for the 10 CropRetain demo markets, across
supported languages. Same principle as crop_terms.py: canonical market
name is what the business logic uses; this module only helps *recognize*
a market mentioned in free text, in Devanagari/other-script spellings.
"""

MARKET_ALIASES = {
    "Bilaspur": ["bilaspur", "बिलासपुर", "বিলাসপুর"],
    "Raipur": ["raipur", "रायपुर", "রায়পুর"],
    "Durg": ["durg", "दुर्ग"],
    "Raigarh": ["raigarh", "रायगढ़"],
    "Korba": ["korba", "कोरबा"],
    "Bilha": ["bilha", "बिल्हा"],
    "Ambikapur": ["ambikapur", "अंबिकापुर"],
    "Rajnandgaon": ["rajnandgaon", "राजनांदगांव"],
    "Mahasamund": ["mahasamund", "महासमुंद"],
    "Jagdalpur": ["jagdalpur", "जगदलपुर"],
}

_ALIAS_INDEX = {}
for canonical, aliases in MARKET_ALIASES.items():
    for a in aliases:
        _ALIAS_INDEX[a.lower()] = canonical


def find_market_in_text(text: str) -> str | None:
    lowered = text.lower()
    for alias in sorted(_ALIAS_INDEX.keys(), key=len, reverse=True):
        if alias in lowered:
            return _ALIAS_INDEX[alias]
    return None


def find_all_markets_in_text(text: str) -> list[str]:
    """Return every distinct canonical market named in the text, in the
    order they first appear -- used by MARKET_COMPARISON, which needs two
    named markets rather than the single "where am I selling from" market
    that find_market_in_text() resolves for every other intent."""
    lowered = text.lower()
    found = []
    for alias in sorted(_ALIAS_INDEX.keys(), key=len, reverse=True):
        if alias in lowered:
            canonical = _ALIAS_INDEX[alias]
            if canonical not in found:
                found.append(canonical)
    return found
