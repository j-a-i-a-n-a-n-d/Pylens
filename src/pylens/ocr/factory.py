from __future__ import annotations

from pylens.ocr.base import OcrAdapter, OcrEngineId
from pylens.ocr.paddle_adapter import PaddleOcrAdapter
from pylens.ocr.windows_adapter import WindowsOcrAdapter


def create_ocr_adapter(engine: str | OcrEngineId, *, auto_download: bool = False) -> OcrAdapter:
    """Factory: Paddle (primary) or Windows (secondary)."""
    engine_id = engine if isinstance(engine, OcrEngineId) else OcrEngineId.from_value(str(engine))
    if engine_id is OcrEngineId.PADDLE:
        return PaddleOcrAdapter(auto_download=auto_download)
    if engine_id is OcrEngineId.WINDOWS:
        return WindowsOcrAdapter()
    raise ValueError(f"Unsupported OCR engine: {engine_id}")


def available_engines() -> list[tuple[OcrEngineId, str]]:
    # Paddle first (primary), Windows secondary.
    return [
        (OcrEngineId.PADDLE, PaddleOcrAdapter.display_name),
        (OcrEngineId.WINDOWS, WindowsOcrAdapter.display_name),
    ]
