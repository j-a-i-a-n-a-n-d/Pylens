from __future__ import annotations

"""Chip geometry + overlap helpers."""

MIN_FONT_PT = 6.5
MAX_FONT_PT = 14.0
PREFERRED_FONT_RATIO = 0.78
EDGE_PAD = 1.0
MAX_HEIGHT_MULT = 4.0
DEFAULT_ALWAYS_SHRINK_PT = 4.0


def preferred_font_pt(ocr_height: float, *, shrink_pt: float = 0.0) -> float:
    base = max(MIN_FONT_PT, min(MAX_FONT_PT, ocr_height * PREFERRED_FONT_RATIO))
    return max(MIN_FONT_PT, base - max(0.0, shrink_pt))


def chip_rect(
    ocr: tuple[float, float, float, float],
    bounds_w: float,
    bounds_h: float,
    *,
    edge_pad: float = EDGE_PAD,
    needed_h: float | None = None,
    max_height_mult: float = MAX_HEIGHT_MULT,
) -> tuple[float, float, float, float]:
    ox, oy, ow, oh = ocr
    x = max(0.0, ox - edge_pad)
    y = max(0.0, oy - edge_pad)
    w = min(bounds_w - x, ow + edge_pad * 2)
    max_h = min(bounds_h - y, oh * max_height_mult, bounds_h * 0.9)
    h = oh + edge_pad * 2
    if needed_h is not None:
        h = max(h, needed_h + edge_pad * 2)
    h = min(h, max_h)
    return x, y, max(1.0, w), max(1.0, h)


def rects_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    *,
    pad: float = 1.0,
) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (
        ax + aw + pad <= bx
        or bx + bw + pad <= ax
        or ay + ah + pad <= by
        or by + bh + pad <= ay
    )


def find_overlapping_indices(
    rects: list[tuple[float, float, float, float]],
) -> set[int]:
    hit: set[int] = set()
    n = len(rects)
    for i in range(n):
        for j in range(i + 1, n):
            if rects_overlap(rects[i], rects[j]):
                hit.add(i)
                hit.add(j)
    return hit


def strip_rect(
    ocr: tuple[float, float, float, float],
    bounds_w: float,
    bounds_h: float,
) -> tuple[float, float, float, float]:
    return chip_rect(ocr, bounds_w, bounds_h)
