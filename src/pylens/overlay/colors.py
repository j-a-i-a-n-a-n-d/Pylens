from __future__ import annotations

from statistics import median

from PIL import Image

from pylens.models import Color, Rect, TextBlock

# Chip fill alpha — high enough to mask Japanese glyphs; tint still from sample.
CHIP_BG_ALPHA = 236


def luminance(rgb: Color) -> float:
    r, g, b = rgb
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def contrasting_fg(bg: Color) -> Color:
    return (255, 255, 255) if luminance(bg) < 0.55 else (25, 25, 25)


def sample_colors(image: Image.Image, rect: Rect, pad: int = 2) -> tuple[Color, Color]:
    """
    Sample background colour near the OCR box so chips tint toward the document
    (headers, flowchart nodes, etc.) while remaining opaque enough to hide JP ink.
    """
    x, y, w, h = rect
    samples: list[Color] = []
    points: list[tuple[int, int]] = []
    for dx in range(x - pad, x + w + pad):
        points.append((dx, y - pad))
        points.append((dx, y + h + pad))
    for dy in range(y, y + h):
        points.append((x - pad, dy))
        points.append((x + w + pad, dy))
    inset_x = max(1, w // 8)
    inset_y = max(1, h // 8)
    for px, py in (
        (x + inset_x, y + inset_y),
        (x + w - inset_x, y + inset_y),
        (x + inset_x, y + h - inset_y),
        (x + w - inset_x, y + h - inset_y),
    ):
        points.append((px, py))

    rgb = image.convert("RGB")
    iw, ih = rgb.size
    for px, py in points:
        if 0 <= px < iw and 0 <= py < ih:
            samples.append(rgb.getpixel((px, py)))  # type: ignore[arg-type]

    if not samples:
        cx = min(max(x + w // 2, 0), iw - 1)
        cy = min(max(y + h // 2, 0), ih - 1)
        bg = rgb.getpixel((cx, cy))  # type: ignore[assignment]
        bg_t = (int(bg[0]), int(bg[1]), int(bg[2]))
        return _readable_pair(bg_t)

    bg = (
        int(median(s[0] for s in samples)),
        int(median(s[1] for s in samples)),
        int(median(s[2] for s in samples)),
    )
    return _readable_pair(bg)


def _readable_pair(bg: Color) -> tuple[Color, Color]:
    """Slightly lift very dark fills so English stays readable on tinted chips."""
    r, g, b = bg
    if luminance(bg) < 0.18:
        bg = (min(255, r + 40), min(255, g + 40), min(255, b + 40))
    return bg, contrasting_fg(bg)


def apply_colors(image: Image.Image, blocks: list[TextBlock]) -> list[TextBlock]:
    for b in blocks:
        bg, fg = sample_colors(image, b.rect)
        b.bg_color = bg
        b.fg_color = fg
    return blocks
