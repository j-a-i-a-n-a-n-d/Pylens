from __future__ import annotations

"""Compatibility shim — prefer pylens.ocr.windows_adapter / factory."""

from pylens.ocr.preprocess import choose_scale, merge_line_fragments, upscale
from pylens.ocr.windows_adapter import (
    WindowsOcrAdapter,
    windows_language_tag,
)
from pylens.ocr.windows_adapter import (
    has_windows_ocr_language as has_ocr_language,
)
from pylens.ocr.windows_adapter import (
    list_windows_ocr_languages as list_ocr_languages,
)

__all__ = [
    "WindowsOcrAdapter",
    "choose_scale",
    "has_ocr_language",
    "list_ocr_languages",
    "merge_line_fragments",
    "upscale",
    "windows_language_tag",
]


def recognize(image, lang: str = "ja"):
    return WindowsOcrAdapter().recognize(image, lang)
