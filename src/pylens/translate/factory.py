from __future__ import annotations

from pylens.paths import argos_models_dir
from pylens.translate.argos import ArgosTranslator
from pylens.translate.base import Translator
from pylens.translate.google import GoogleTranslator


def create_translator(engine: str) -> Translator:
    """Create the selected translation provider without downloading assets."""

    normalized = engine.strip().lower()
    if normalized == "argos":
        return ArgosTranslator(argos_models_dir())
    if normalized == "google":
        return GoogleTranslator()
    raise ValueError(f"Unknown translation engine: {engine}")
