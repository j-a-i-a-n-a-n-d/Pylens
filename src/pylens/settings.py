from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def appdata_dir() -> Path:
    base = Path.home() / "AppData" / "Roaming" / "PyLens"
    base.mkdir(parents=True, exist_ok=True)
    return base


def settings_path() -> Path:
    return appdata_dir() / "settings.json"


class Settings(BaseModel):
    target_lang: str = "en"
    hotkey_region: str = "ctrl+alt+r"
    hotkey_window: str = "ctrl+alt+t"
    ocr_engine: str = "paddle"  # primary: paddle | secondary: windows
    ocr_language: str = "ja"  # Japanese-only for Paddle
    ocr_profile: str = "balanced"  # fast | balanced | accuracy
    translation_engine: str = "argos"  # argos (offline) | google (online)
    paddle_auto_download: bool = False  # retained for old settings; downloads are disabled
    privacy_acknowledged: bool = False
    first_run_done: bool = False
    debug_save_capture: bool = False
    debug_ocr: bool = True  # write OCR images + raw/post JSON under %TEMP%/pylens_ocr/
    recent_targets: list[str] = Field(default_factory=lambda: ["en", "ja"])
    # Overlay readability / overlap controls
    overlay_always_shrink_font: bool = True
    overlay_always_shrink_pt: float = 4.0
    overlay_shrink_on_collide: bool = True
    overlay_hover_show_full: bool = True

    def save(self) -> None:
        settings_path().write_text(
            self.model_dump_json(indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls) -> Settings:
        path = settings_path()
        if not path.exists():
            return cls()
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return cls.model_validate(data)
        except Exception:
            return cls()
