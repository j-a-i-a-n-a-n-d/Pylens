from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pylens.platform import current_platform, Platform


def config_dir() -> Path:
    """Get platform-appropriate config directory."""
    platform = current_platform()

    if platform == Platform.WINDOWS:
        # Windows: %APPDATA%\PyLens
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "PyLens"
    elif platform == Platform.MACOS:
        # macOS: ~/Library/Application Support/PyLens
        base = Path.home() / "Library" / "Application Support" / "PyLens"
    elif platform == Platform.LINUX:
        # Linux: ~/.config/pylens (XDG_CONFIG_HOME)
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            base = Path(xdg_config) / "pylens"
        else:
            base = Path.home() / ".config" / "pylens"
    else:
        # Fallback
        base = Path.home() / ".pylens"

    base.mkdir(parents=True, exist_ok=True)
    return base


def settings_path() -> Path:
    return config_dir() / "settings.json"


def log_dir() -> Path:
    """Get platform-appropriate log directory."""
    platform = current_platform()

    if platform == Platform.WINDOWS:
        # Windows: %TEMP%\pylens
        base = Path(os.environ.get("TEMP", Path.home() / "AppData" / "Local" / "Temp")) / "pylens"
    elif platform == Platform.MACOS:
        # macOS: ~/Library/Logs/PyLens
        base = Path.home() / "Library" / "Logs" / "PyLens"
    elif platform == Platform.LINUX:
        # Linux: ~/.cache/pylens (XDG_CACHE_HOME)
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        if xdg_cache:
            base = Path(xdg_cache) / "pylens"
        else:
            base = Path.home() / ".cache" / "pylens"
    else:
        base = Path.home() / ".pylens" / "logs"

    base.mkdir(parents=True, exist_ok=True)
    return base


def default_hotkey_region() -> str:
    if current_platform() == Platform.MACOS:
        return "option+ctrl+r"
    return "ctrl+alt+r"


def default_hotkey_window() -> str:
    if current_platform() == Platform.MACOS:
        return "option+ctrl+t"
    return "ctrl+alt+t"


class Settings(BaseModel):
    target_lang: str = "en"
    hotkey_region: str = Field(default_factory=default_hotkey_region)
    hotkey_window: str = Field(default_factory=default_hotkey_window)
    ocr_engine: str = "paddle"  # primary: paddle | secondary: windows/macos
    ocr_language: str = "ja"  # Japanese-only for Paddle
    ocr_profile: str = "balanced"  # fast | balanced | accuracy
    translation_engine: str = "argos"  # argos (offline) | google (online)
    paddle_auto_download: bool = False  # retained for old settings; downloads are disabled
    privacy_acknowledged: bool = False
    first_run_done: bool = False
    debug_save_capture: bool = False
    debug_ocr: bool = True  # write OCR images + raw/post JSON under log_dir()/ocr/
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