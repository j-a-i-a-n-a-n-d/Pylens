from __future__ import annotations

import re

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from pylens.models import Rect, TextBlock

PROFILE_LONGEST_SIDE = {
    "fast": 1920,
    "balanced": 2880,
    "accuracy": 3600,
}
MAX_UPSCALE = 3.5

_CODE_TOKEN = re.compile(
    r"^(?:"
    r"case|when|then|else|end|and|or|not|exists|select|from|where|join|on|"
    r"inner|left|right|outer|null|true|false|in|as|is|"
    r"[=<>!()\[\]{},.;:'\"`+\-/*\\|]+"
    r")$",
    re.IGNORECASE,
)
_HAS_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
_HAS_JAPANESE = _HAS_CJK
_FULLWIDTH_ALNUM = re.compile(r"^[\uFF10-\uFF19\uFF21-\uFF3A\uFF41-\uFF5A]+$")
_TECH_ACRONYM = re.compile(r"^(?:ECS|DB|S3|BL|API|SQL|EC2|VPC|IAM)$", re.IGNORECASE)
_ATTACHABLE_EN = re.compile(
    r"^(?:PrivateLink|Fargate|CloudWatch|Step\s*Functions|"
    r"ECS|DB|S3|BL|EC2|VPC|IAM|Cloud|Watch)$",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"[。！？!?]$")
_CONTINUATION_START = re.compile(r"^[ぁ-んァ-ンー]")
_LATIN_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9.\-_]*$")


def choose_scale(width: int, height: int, profile: str = "balanced") -> float:
    """Fit the longest side to a profile target without extreme enlargement."""

    if profile not in PROFILE_LONGEST_SIDE:
        raise ValueError(f"Unknown OCR profile: {profile}")
    longest = max(width, height)
    if longest <= 0:
        return 1.0
    return min(MAX_UPSCALE, PROFILE_LONGEST_SIDE[profile] / longest)


def enhance_for_ocr(image: Image.Image) -> Image.Image:
    """Contrast / sharpen for small UI fonts (forms, dense Japanese labels)."""
    rgb = image.convert("RGB")
    rgb = ImageOps.autocontrast(rgb, cutoff=2)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.45)
    rgb = ImageEnhance.Brightness(rgb).enhance(1.05)
    rgb = ImageEnhance.Sharpness(rgb).enhance(1.7)
    rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.5, percent=170, threshold=1))
    return rgb


def prepare_for_ocr(image: Image.Image, scale: float) -> Image.Image:
    """Upscale first, then enhance — sharpening works better on larger glyphs."""
    scaled = upscale(image.convert("RGB"), scale)
    return enhance_for_ocr(scaled)


def upscale(image: Image.Image, scale: float) -> Image.Image:
    if abs(scale - 1.0) < 1e-6:
        return image
    w = max(1, int(image.width * scale))
    h = max(1, int(image.height * scale))
    return image.resize((w, h), Image.Resampling.LANCZOS)


def is_junk_fragment(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if _FULLWIDTH_ALNUM.match(t) or _TECH_ACRONYM.match(t):
        return False
    if len(t) <= 2 and not _HAS_CJK.search(t) and not _CODE_TOKEN.match(t):
        return True
    if len(t) <= 3 and t.isalpha() and t.isupper() and not _CODE_TOKEN.match(t):
        return False
    return False


def filter_junk_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    return [b for b in blocks if not is_junk_fragment(b.original)]


def _union_rect(a: Rect, b: Rect) -> Rect:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left = min(ax, bx)
    top = min(ay, by)
    right = max(ax + aw, bx + bw)
    bottom = max(ay + ah, by + bh)
    return (left, top, right - left, bottom - top)


def _merge_two_blocks(left: TextBlock, right: TextBlock, sep: str) -> TextBlock:
    return TextBlock(
        original=f"{left.original}{sep}{right.original}",
        rect=_union_rect(left.rect, right.rect),
        translated=left.translated or right.translated,
        bg_color=left.bg_color,
        fg_color=left.fg_color,
    )


def _x_overlap_ratio(a: Rect, b: Rect) -> float:
    ax, _, aw, _ = a
    bx, _, bw, _ = b
    overlap = min(ax + aw, bx + bw) - max(ax, bx)
    if overlap <= 0:
        return 0.0
    return overlap / max(1, min(aw, bw))


def _cluster_into_lines(blocks: list[TextBlock], y_tol: float = 0.45) -> list[list[TextBlock]]:
    if not blocks:
        return []
    ordered = sorted(blocks, key=lambda b: (b.rect[1], b.rect[0]))
    lines: list[list[TextBlock]] = [[ordered[0]]]
    for block in ordered[1:]:
        line = lines[-1]
        ref = line[-1]
        _, cy, _, ch = ref.rect
        _, ny, _, nh = block.rect
        avg_h = max(1.0, (ch + nh) / 2.0)
        same_line = abs((cy + ch / 2) - (ny + nh / 2)) <= avg_h * y_tol
        if same_line:
            line.append(block)
        else:
            lines.append([block])
    return lines


def merge_line_fragments(
    blocks: list[TextBlock],
    y_tol: float = 0.5,
    x_gap: float = 1.35,
) -> list[TextBlock]:
    """Merge same-baseline boxes; cluster by line first to avoid sort-order gaps."""
    if len(blocks) < 2:
        return blocks
    merged_lines: list[TextBlock] = []
    for line in _cluster_into_lines(blocks, y_tol):
        line_sorted = sorted(line, key=lambda b: b.rect[0])
        current = line_sorted[0]
        for nxt in line_sorted[1:]:
            cx, _, cw, ch = current.rect
            nx, _, _, nh = nxt.rect
            avg_h = max(1.0, (ch + nh) / 2.0)
            gap = nx - (cx + cw)
            close = gap <= avg_h * x_gap and gap >= -avg_h * 0.35
            if close:
                sep = "" if gap < avg_h * 0.15 else " "
                current = _merge_two_blocks(current, nxt, sep)
            else:
                merged_lines.append(current)
                current = nxt
        merged_lines.append(current)
    return merged_lines


def _is_japanese_block(block: TextBlock) -> bool:
    return _HAS_JAPANESE.search(block.original) is not None


def _is_attachable_english(text: str) -> bool:
    t = text.strip()
    if not t or _HAS_JAPANESE.search(t):
        return False
    if _ATTACHABLE_EN.match(t):
        return True
    return len(t) <= 16 and bool(_LATIN_TOKEN.match(t))


def merge_brand_tokens(blocks: list[TextBlock]) -> list[TextBlock]:
    """Merge Cloud+Watch and attach isolated product tokens to Japanese neighbors."""
    if len(blocks) < 2:
        return blocks

    line_blocks: list[TextBlock] = []
    for line in _cluster_into_lines(blocks):
        line_sorted = sorted(line, key=lambda b: b.rect[0])
        idx = 0
        while idx < len(line_sorted):
            current = line_sorted[idx]
            if (
                idx + 1 < len(line_sorted)
                and current.original.strip() == "Cloud"
                and line_sorted[idx + 1].original.strip() == "Watch"
            ):
                line_blocks.append(_merge_two_blocks(current, line_sorted[idx + 1], ""))
                idx += 2
                continue
            line_blocks.append(current)
            idx += 1

    merged_lines: list[TextBlock] = []
    for line in _cluster_into_lines(line_blocks):
        line_sorted = sorted(line, key=lambda b: b.rect[0])
        current = line_sorted[0]
        for nxt in line_sorted[1:]:
            cur_en = _is_attachable_english(current.original)
            nxt_en = _is_attachable_english(nxt.original)
            cur_ja = _is_japanese_block(current)
            nxt_ja = _is_japanese_block(nxt)
            attach = (cur_en and nxt_ja) or (cur_ja and nxt_en)
            if attach:
                current = _merge_two_blocks(current, nxt, " ")
            else:
                merged_lines.append(current)
                current = nxt
        merged_lines.append(current)

    return sorted(merged_lines, key=lambda b: (b.rect[1], b.rect[0]))


def _should_merge_vertically(
    upper: TextBlock,
    lower: TextBlock,
    *,
    y_gap: float,
    x_overlap: float,
) -> bool:
    if _SENTENCE_END.search(upper.original.strip()):
        return False
    _, uy, _, uh = upper.rect
    _, ly, _, lh = lower.rect
    line_h = max(1.0, min(lh, uh, 80.0))
    gap = ly - (uy + uh)
    if gap > line_h * y_gap or gap < -line_h * 0.3:
        return False
    if _x_overlap_ratio(upper.rect, lower.rect) < x_overlap:
        return False
    combined_height = (ly + lh) - uy
    return combined_height <= line_h * 4.0


def merge_vertical_blocks(
    blocks: list[TextBlock],
    y_gap: float = 1.5,
    x_overlap: float = 0.3,
) -> list[TextBlock]:
    """Merge vertically adjacent blocks in the same column when the upper line is incomplete."""
    if len(blocks) < 2:
        return blocks
    ordered = sorted(blocks, key=lambda b: (b.rect[1], b.rect[0]))
    merged: list[TextBlock] = []
    current = ordered[0]
    for nxt in ordered[1:]:
        upper, lower = (current, nxt) if current.rect[1] <= nxt.rect[1] else (nxt, current)
        if _should_merge_vertically(upper, lower, y_gap=y_gap, x_overlap=x_overlap):
            current = _merge_two_blocks(upper, lower, "")
        else:
            merged.append(current)
            current = nxt
    merged.append(current)
    return merged


def merge_sentence_groups(blocks: list[TextBlock]) -> list[TextBlock]:
    """Join blocks when the lower line clearly continues the upper (split words/lines)."""
    if len(blocks) < 2:
        return blocks
    ordered = sorted(blocks, key=lambda b: (b.rect[1], b.rect[0]))
    merged: list[TextBlock] = []
    current = ordered[0]
    for nxt in ordered[1:]:
        upper_text = current.original.strip()
        lower_text = nxt.original.strip()
        ends_sentence = _SENTENCE_END.search(upper_text) is not None
        same_column = _x_overlap_ratio(current.rect, nxt.rect) >= 0.25
        _, cy, _, ch = current.rect
        _, ny, _, nh = nxt.rect
        gap = ny - (cy + ch)
        close_below = 0 <= gap <= nh * 1.8
        continues = upper_text.endswith("、") or bool(_CONTINUATION_START.match(lower_text))
        if not ends_sentence and same_column and close_below and continues:
            current = _merge_two_blocks(current, nxt, "")
        else:
            merged.append(current)
            current = nxt
    merged.append(current)
    return merged


def postprocess_ocr_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    """Junk filter → OCR repair → line merge → brand attach → vertical → sentence."""
    from pylens.text.ocr_correct import correct_ocr_text

    pipeline: list[TextBlock] = []
    for block in filter_junk_blocks(blocks):
        fixed = correct_ocr_text(block.original)
        if fixed != block.original:
            block = TextBlock(
                original=fixed,
                rect=block.rect,
                translated=block.translated,
                bg_color=block.bg_color,
                fg_color=block.fg_color,
            )
        pipeline.append(block)
    pipeline = merge_line_fragments(pipeline)
    pipeline = merge_brand_tokens(pipeline)
    pipeline = merge_vertical_blocks(pipeline)
    pipeline = merge_sentence_groups(pipeline)
    # Re-correct after merges (joined fragments may match longer rules).
    out: list[TextBlock] = []
    for block in pipeline:
        fixed = correct_ocr_text(block.original)
        if fixed != block.original:
            block = TextBlock(
                original=fixed,
                rect=block.rect,
                translated=block.translated,
                bg_color=block.bg_color,
                fg_color=block.fg_color,
            )
        out.append(block)
    return out
