from __future__ import annotations

from PIL import Image

from pylens.ocr.base import OcrAdapter, OcrEngineId
from pylens.ocr.factory import create_ocr_adapter
from pylens.ocr.paddle_adapter import PaddleOcrAdapter

_adapters: dict[str, OcrAdapter] = {}


def get_shared_ocr_adapter(
    engine: str | OcrEngineId,
    *,
    auto_download: bool = False,
) -> OcrAdapter:
    """Reuse one adapter instance so OCR engines stay warm across captures."""

    key = engine.value if isinstance(engine, OcrEngineId) else str(engine).lower()
    adapter = _adapters.get(key)
    if adapter is None:
        adapter = create_ocr_adapter(engine, auto_download=auto_download)
        _adapters[key] = adapter
    return adapter


def warm_ocr_adapter(engine: str | OcrEngineId, language: str = "ja") -> None:
    """Load model weights once so the first user capture is not cold."""

    adapter = get_shared_ocr_adapter(engine, auto_download=False)
    if not adapter.is_ready(language):
        return

    # Trigger engine construction with a tiny blank image
    blank = Image.new("RGB", (64, 64), (255, 255, 255))
    try:
        adapter.recognize(blank, language, debug=False, profile="fast")
    except Exception:
        # Warm-up is best-effort; first real capture will load if this fails.
        pass