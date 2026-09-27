from __future__ import annotations

from PIL import Image

from pylens.ocr.base import OcrEngineId
from pylens.ocr.factory import available_engines, create_ocr_adapter
from pylens.ocr.paddle_adapter import PaddleOcrAdapter, japan_model_dirs, paddle_package_installed
from pylens.paths import argos_models_dir, paddle_models_dir, project_root


def test_project_models_path_is_under_repo():
    root = project_root()
    models = paddle_models_dir()
    assert models == root / "models" / "paddle"
    assert root.name == "py-lens" or (root / "pyproject.toml").exists()
    assert argos_models_dir() == root / "models" / "argos"


def test_factory_paddle_primary():
    engines = available_engines()
    assert engines[0][0] is OcrEngineId.PADDLE
    # Second engine varies by platform: Windows=WINDOWS, macOS=MACOS_VISION, Linux=LINUX_TESSERACT
    assert len(engines) >= 2
    paddle = create_ocr_adapter("paddle")
    assert paddle.id is OcrEngineId.PADDLE


def test_factory_rejects_unknown():
    try:
        create_ocr_adapter("tesseract")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_paddle_japanese_only_and_project_local():
    adapter = PaddleOcrAdapter(auto_download=False)
    assert adapter.is_available() is paddle_package_installed()
    msg = adapter.readiness_message("ja")
    assert "models" in msg.lower() or "install" in msg.lower() or "Ready" in msg
    # Models must be resolved from project dir, never require ~/.paddleocr
    found = japan_model_dirs()
    if found:
        for path in found.values():
            assert "models" in path.parts and "paddle" in path.parts


def test_paddle_recognize_fails_clearly_without_models_when_no_autodownload():
    adapter = PaddleOcrAdapter(auto_download=False)
    if adapter.is_ready("ja"):
        return
    img = Image.new("RGB", (64, 32), "white")
    try:
        adapter.recognize(img, "ja")
        raised = False
        message = ""
    except RuntimeError as ex:
        raised = True
        message = str(ex)
    assert raised
    assert "models" in message.lower() or "install" in message.lower()
