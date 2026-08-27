from __future__ import annotations

import hashlib
import unicodedata


def normalize_for_cache(text: str) -> str:
    """Return a stable representation for glossary and cache lookups."""

    normalized = unicodedata.normalize("NFKC", text)
    return " ".join(normalized.split())


def cache_key(source_lang: str, target_lang: str, text: str) -> str:
    """Build a deterministic key that includes the translation direction."""

    payload = "\0".join(
        (
            source_lang.lower(),
            target_lang.lower(),
            normalize_for_cache(text),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
