from __future__ import annotations

import json
from pathlib import Path

from pylens.text.normalize import normalize_for_cache


class Glossary:
    """Exact-match terminology store for controlled business translations."""

    def __init__(self, terms: dict[str, dict[str, str]] | None = None) -> None:
        self._terms = terms or {}

    @classmethod
    def from_paths(cls, paths: list[Path]) -> Glossary:
        merged: dict[str, dict[str, str]] = {}
        for path in paths:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise TypeError(f"Glossary root must be an object: {path}")
            for direction, entries in data.items():
                if not isinstance(entries, dict):
                    raise TypeError(f"Glossary direction must be an object: {direction}")
                direction_terms = merged.setdefault(str(direction).lower(), {})
                for source, translated in entries.items():
                    key = normalize_for_cache(str(source))
                    if str(direction).lower().startswith("en-"):
                        key = key.casefold()
                    direction_terms[key] = str(translated)
        return cls(merged)

    def lookup(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> str | None:
        direction = f"{source_lang.lower()}-{target_lang.lower()}"
        key = normalize_for_cache(text)
        if source_lang.lower() == "en":
            key = key.casefold()
        return self._terms.get(direction, {}).get(key)
