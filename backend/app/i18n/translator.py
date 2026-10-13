"""
Translation provider abstraction for freeform user text (listing notes,
offer messages -- as opposed to crop/market names, which are canonical
entities handled by crop_terms.py / location_terms.py, not "translated").

IMPORTANT / HONESTY NOTE:
This hackathon build ships only a `NoOpTranslationProvider`: no external
translation API key is configured, so freeform text is NOT machine
translated. The architecture is intentionally provider-agnostic so a real
provider (Google Cloud Translate, Azure Translator, AWS Translate, etc.)
can be dropped in later by implementing `TranslationProvider` and wiring it
in `get_translation_provider()` -- no caller code changes required.

What CropRetain stores and shows instead, honestly:
  - the original text and its source language, always preserved
  - the viewer's language
  - a `translation_available` flag the frontend uses to show either a
    real translation (if a provider is configured) or the original text
    with a clear "shown in original language" note.
"""
from abc import ABC, abstractmethod
from typing import Optional


class TranslationProvider(ABC):
    @abstractmethod
    def translate(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        """Return translated text, or None if translation isn't possible."""
        raise NotImplementedError

    @property
    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError


class NoOpTranslationProvider(TranslationProvider):
    """No external provider configured -- always honest about it."""

    @property
    def available(self) -> bool:
        return False

    def translate(self, text: str, source_lang: str, target_lang: str) -> Optional[str]:
        return None


def get_translation_provider() -> TranslationProvider:
    # Swap this for a real provider once API credentials are configured
    # server-side (never in frontend code -- see app/config.py).
    return NoOpTranslationProvider()


def build_message_payload(original_text: str, source_language: str, viewer_language: str) -> dict:
    """
    Shared helper used by marketplace endpoints (listings, offers) to attach
    translation metadata to any user-authored free text, without ever
    overwriting the original.
    """
    provider = get_translation_provider()
    translated = None
    if provider.available and source_language != viewer_language:
        translated = provider.translate(original_text, source_language, viewer_language)
    return {
        "original_text": original_text,
        "source_language": source_language,
        "viewer_language": viewer_language,
        "translated_text": translated,
        "translation_available": translated is not None,
    }
