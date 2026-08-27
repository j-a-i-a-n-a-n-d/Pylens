from __future__ import annotations

from pylens.models import TextBlock
from pylens.ocr.preprocess import (
    filter_junk_blocks,
    is_junk_fragment,
    merge_line_fragments,
    postprocess_ocr_blocks,
)
from pylens.overlay.layout import chip_rect, find_overlapping_indices, preferred_font_pt


def test_junk_filter_drops_noise():
    assert is_junk_fragment("ANI")
    assert not is_junk_fragment("計画コード")


def test_gap_aware_keeps_separate_cells():
    blocks = [
        TextBlock("更新日", (10, 100, 50, 16)),
        TextBlock("更新者", (200, 100, 50, 16)),
        TextBlock("更新内容", (400, 100, 60, 16)),
    ]
    out = postprocess_ocr_blocks(blocks)
    assert len(out) == 3


def test_gap_aware_merges_close_phrase():
    blocks = [
        TextBlock("計画", (10, 50, 40, 14)),
        TextBlock("コード", (52, 50, 50, 14)),
    ]
    out = merge_line_fragments(filter_junk_blocks(blocks))
    assert len(out) == 1


def test_postprocess_does_not_vertically_merge_rows():
    blocks = [
        TextBlock("row1", (500, 100, 80, 14)),
        TextBlock("row2", (505, 130, 70, 14)),
        TextBlock("row3", (502, 160, 60, 14)),
    ]
    out = postprocess_ocr_blocks(blocks)
    assert len(out) == 3


def test_chip_rect_can_grow_height_for_wrap():
    ocr = (100.0, 200.0, 80.0, 16.0)
    _x, _y, w, h = chip_rect(ocr, 800.0, 600.0, needed_h=48.0)
    assert w <= 84.0
    assert h > 16.0


def test_always_shrink_reduces_preferred_font():
    normal = preferred_font_pt(20.0, shrink_pt=0.0)
    shrunk = preferred_font_pt(20.0, shrink_pt=4.0)
    assert shrunk <= normal - 3.5


def test_find_overlapping_indices():
    rects = [
        (10.0, 10.0, 40.0, 20.0),
        (30.0, 15.0, 40.0, 20.0),  # overlaps 0
        (200.0, 10.0, 30.0, 20.0),  # free
    ]
    hit = find_overlapping_indices(rects)
    assert hit == {0, 1}
