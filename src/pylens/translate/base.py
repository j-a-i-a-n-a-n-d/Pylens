from __future__ import annotations

from typing import Protocol


class Translator(Protocol):
    """Minimal interface implemented by local and cloud translation engines."""

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        ...

    def prepare(self, source_lang: str, target_lang: str) -> None:
        """Prepare an already-local model. Must not download anything."""
        ...

    def close(self) -> None:
        ...
