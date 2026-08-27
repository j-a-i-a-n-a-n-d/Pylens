from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

Color = tuple[int, int, int]
Rect = tuple[int, int, int, int]  # x, y, w, h in capture-local physical pixels


@dataclass
class TextBlock:
    original: str
    rect: Rect
    translated: str = ""
    bg_color: Color = (255, 255, 255)
    fg_color: Color = (0, 0, 0)


@dataclass
class CaptureResult:
    """A screen capture and its position on the virtual desktop (physical pixels)."""

    image: Image.Image
    origin_x: int
    origin_y: int

    @property
    def width(self) -> int:
        return self.image.width

    @property
    def height(self) -> int:
        return self.image.height

    @property
    def screen_rect(self) -> Rect:
        return (self.origin_x, self.origin_y, self.width, self.height)


@dataclass
class AppState:
    busy: bool = False
    target_lang: str = "en"
    recent_targets: list[str] = field(default_factory=lambda: ["en", "ja", "zh-CN", "ko"])
