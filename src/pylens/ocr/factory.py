from __future__ import annotations

from pylens.ocr.base import OcrAdapter, OcrEngineId
from pylens.ocr.paddle_adapter import PaddleOcrAdapter
from pylens.ocr.windows_adapter import WindowsOcrAdapter
from pylens.platform import current_platform, Platform


def create_ocr_adapter(engine: str | OcrEngineId, *, auto_download: bool = False) -> OcrAdapter:
    """Factory: Paddle (primary), Windows (Windows), Vision (macOS), Tesseract (Linux)."""
    engine_id = engine if isinstance(engine, OcrEngineId) else OcrEngineId.from_value(str(engine))
    platform = current_platform()

    if engine_id is OcrEngineId.PADDLE:
        return PaddleOcrAdapter(auto_download=auto_download)

    if engine_id is OcrEngineId.WINDOWS:
        if platform != Platform.WINDOWS:
            raise ValueError("Windows OCR is only available on Windows")
        return WindowsOcrAdapter()

    if engine_id is OcrEngineId.MACOS_VISION:
        if platform != Platform.MACOS:
            raise ValueError("macOS Vision OCR is only available on macOS")
        from pylens.ocr.vision_adapter import VisionOcrAdapter
        return VisionOcrAdapter()

    if engine_id is OcrEngineId.LINUX_TESSERACT:
        if platform != Platform.LINUX:
            raise ValueError("Tesseract OCR is only available on Linux")
        from pylens.ocr.tesseract_adapter import TesseractOcrAdapter
        return TesseractOcrAdapter()

    raise ValueError(f"Unsupported OCR engine: {engine_id}")


def available_engines() -> list[tuple[OcrEngineId, str]]:
    """Return available engines for current platform, ordered by preference."""
    platform = current_platform()
    engines = []

    # PaddleOCR is cross-platform
    from pylens.ocr.paddle_adapter import PaddleOcrAdapter
    engines.append((OcrEngineId.PADDLE, PaddleOcrAdapter.display_name))

    if platform == Platform.WINDOWS:
        from pylens.ocr.windows_adapter import WindowsOcrAdapter
        engines.append((OcrEngineId.WINDOWS, WindowsOcrAdapter.display_name))
    elif platform == Platform.MACOS:
        from pylens.ocr.vision_adapter import VisionOcrAdapter
        if VisionOcrAdapter().is_available():
            engines.append((OcrEngineId.MACOS_VISION, VisionOcrAdapter.display_name))
    elif platform == Platform.LINUX:
        from pylens.ocr.tesseract_adapter import TesseractOcrAdapter
        if TesseractOcrAdapter().is_available():
            engines.append((OcrEngineId.LINUX_TESSERACT, TesseractOcrAdapter.display_name))

    return engines