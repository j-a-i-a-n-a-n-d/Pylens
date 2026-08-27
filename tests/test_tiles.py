from PIL import Image

from pylens.models import TextBlock
from pylens.ocr.tiles import (
    merge_overlap,
    recognize_regions,
    remap_blocks,
    should_tile,
    split_quadrants,
)


def test_small_capture_is_not_tiled():
    assert should_tile(400, 300, force=False) is False


def test_large_capture_is_tiled():
    assert should_tile(1920, 1080, force=False) is True


def test_force_tiles_overrides_size_threshold():
    assert should_tile(400, 300, force=True) is True


def test_quadrants_overlap_and_cover_image_edges():
    image = Image.new("RGB", (1000, 800), "white")
    tiles = split_quadrants(image, overlap_fraction=0.10)

    assert len(tiles) == 4
    assert tiles[0][0:2] == (0, 0)
    assert tiles[-1][0] + tiles[-1][2].width == image.width
    assert tiles[-1][1] + tiles[-1][2].height == image.height
    assert tiles[0][2].width + tiles[1][2].width > image.width
    assert tiles[0][2].height + tiles[2][2].height > image.height


def test_remap_blocks_adds_tile_offset():
    blocks = [TextBlock("受注", (10, 20, 100, 30))]
    assert remap_blocks(blocks, 300, 200)[0].rect == (310, 220, 100, 30)


def test_duplicate_overlap_detection_is_merged():
    blocks = [
        TextBlock("受注", (490, 100, 100, 30)),
        TextBlock("受注", (492, 101, 100, 30)),
        TextBlock("売上", (700, 100, 100, 30)),
    ]

    merged = merge_overlap(blocks)

    assert [block.original for block in merged].count("受注") == 1
    assert len(merged) == 2


def test_region_recognizer_remaps_each_tile():
    image = Image.new("RGB", (1000, 800), "white")

    def recognize(_crop):
        return [TextBlock("cell", (0, 0, 20, 10))]

    blocks = recognize_regions(image, recognize, force_tiles=True)

    assert len(blocks) == 4
    assert blocks[0].rect[0:2] == (0, 0)
    assert blocks[-1].rect[0] > 0
    assert blocks[-1].rect[1] > 0
