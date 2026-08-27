from __future__ import annotations

"""OCR package public API — adapters + factory."""

from pylens.ocr.base import OcrAdapter, OcrEngineId
from pylens.ocr.factory import available_engines, create_ocr_adapter
from pylens.ocr.preprocess import (
    choose_scale,
    merge_line_fragments,
    postprocess_ocr_blocks,
    upscale,
)
from pylens.ocr.windows_adapter import (
    has_windows_ocr_language,
    list_windows_ocr_languages,
)

has_ocr_language = has_windows_ocr_language
list_ocr_languages = list_windows_ocr_languages


def recognize(image, lang: str = "ja", engine: str = "paddle"):
    return create_ocr_adapter(engine).recognize(image, lang)


__all__ = [
    "OcrAdapter",
    "OcrEngineId",
    "available_engines",
    "choose_scale",
    "create_ocr_adapter",
    "has_ocr_language",
    "list_ocr_languages",
    "merge_line_fragments",
    "postprocess_ocr_blocks",
    "recognize",
    "upscale",
]
