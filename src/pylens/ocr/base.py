from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from PIL import Image

from pylens.models import TextBlock


class OcrEngineId(str, Enum):
    PADDLE = "paddle"
    WINDOWS = "windows"
    MACOS_VISION = "macos_vision"
    LINUX_TESSERACT = "linux_tesseract"

    @classmethod
    def from_value(cls, value: str) -> OcrEngineId:
        normalized = (value or "").strip().lower()
        for item in cls:
            if item.value == normalized:
                return item
        raise ValueError(
            f"Unknown OCR engine '{value}'. Choose one of: "
            + ", ".join(e.value for e in cls)
        )


class OcrAdapter(ABC):
    """Pluggable OCR backend. Implementations must not download assets at import time."""

    id: OcrEngineId
    display_name: str

    @abstractmethod
    def is_available(self) -> bool:
        """True when the runtime dependency for this engine is present."""

    @abstractmethod
    def is_ready(self, language: str) -> bool:
        """True when the engine can run for `language` without fetching remote assets."""

    @abstractmethod
    def readiness_message(self, language: str) -> str:
        """Human-readable status / install hint for Settings and pre-checks."""

    @abstractmethod
    def recognize(
        self,
        image: Image.Image,
        language: str = "ja",
        *,
        debug: bool = False,
        profile: str = "balanced",
    ) -> list[TextBlock]:
        """Run OCR. Must raise RuntimeError with a clear message if not ready."""