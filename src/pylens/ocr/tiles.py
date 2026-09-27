from __future__ import annotations

from collections.abc import Callable

from PIL import Image

from pylens.models import TextBlock

# Prefer single-pass OCR for typical UI / window captures.
# Quadrant tiling often chops Japanese labels at seams and hurts recognition.
_TILE_MIN_WIDTH = 2200
_TILE_MIN_HEIGHT = 1600


def should_tile(width: int, height: int, force: bool = False) -> bool:
    """Tile only very large captures; never for normal UI regions."""

    if force:
        return True
    return width >= _TILE_MIN_WIDTH and height >= _TILE_MIN_HEIGHT


def split_quadrants(
    image: Image.Image,
    overlap_fraction: float = 0.15,
) -> list[tuple[int, int, Image.Image]]:
    """Split an image into four overlapping crops with their source offsets."""

    if not 0 <= overlap_fraction < 0.5:
        raise ValueError("overlap_fraction must be between 0 and 0.5")

    middle_x = image.width // 2
    middle_y = image.height // 2
    overlap_x = round(image.width * overlap_fraction / 2)
    overlap_y = round(image.height * overlap_fraction / 2)

    x_ranges = ((0, middle_x + overlap_x), (middle_x - overlap_x, image.width))
    y_ranges = ((0, middle_y + overlap_y), (middle_y - overlap_y, image.height))

    tiles: list[tuple[int, int, Image.Image]] = []
    for top, bottom in y_ranges:
        for left, right in x_ranges:
            tiles.append((left, top, image.crop((left, top, right, bottom))))
    return tiles


def remap_blocks(
    blocks: list[TextBlock],
    offset_x: int,
    offset_y: int,
) -> list[TextBlock]:
    """Move tile-local OCR boxes back into capture coordinates."""

    remapped: list[TextBlock] = []
    for block in blocks:
        x, y, width, height = block.rect
        remapped.append(
            TextBlock(
                original=block.original,
                rect=(x + offset_x, y + offset_y, width, height),
                translated=block.translated,
                bg_color=block.bg_color,
                fg_color=block.fg_color,
            )
        )
    return remapped


def merge_overlap(
    blocks: list[TextBlock],
    iou_threshold: float = 0.5,
) -> list[TextBlock]:
    """Remove same-text boxes duplicated by overlapping tile boundaries."""

    merged: list[TextBlock] = []
    for candidate in blocks:
        duplicate = any(
            existing.original == candidate.original
            and _intersection_over_union(existing.rect, candidate.rect) >= iou_threshold
            for existing in merged
        )
        if not duplicate:
            merged.append(candidate)
    return merged


def recognize_regions(
    image: Image.Image,
    recognizer: Callable[[Image.Image], list[TextBlock]],
    *,
    force_tiles: bool = False,
    overlap_fraction: float = 0.15,
) -> list[TextBlock]:
    """Run one recognizer on either the full image or overlapping quadrants."""

    if not should_tile(image.width, image.height, force_tiles):
        return recognizer(image)

    blocks: list[TextBlock] = []
    for offset_x, offset_y, crop in split_quadrants(image, overlap_fraction):
        blocks.extend(remap_blocks(recognizer(crop), offset_x, offset_y))
    return merge_overlap(blocks)


def _intersection_over_union(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> float:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + aw, bx + bw)
    bottom = min(ay + ah, by + bh)

    intersection = max(0, right - left) * max(0, bottom - top)
    if intersection == 0:
        return 0.0
    union = aw * ah + bw * bh - intersection
    return intersection / union if union else 0.0
