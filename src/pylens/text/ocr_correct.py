from __future__ import annotations

import re

# Longer phrases first. Avoid rules whose output still matches a later "bad" pattern.
_SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("セキユリテイ保母なし", "セキュリティ保護なし"),
    ("セキユリテイ", "セキュリティ"),
    ("セキュリティ保母", "セキュリティ保護"),
    ("保母なし", "保護なし"),
    ("ブロジエクト選択", "プロジェクト選択"),
    ("ブロジェクト選択", "プロジェクト選択"),
    ("プロジエクト選択", "プロジェクト選択"),
    ("ブロジエクト", "プロジェクト"),
    ("ブロジェクト", "プロジェクト"),
    ("プロジエクト", "プロジェクト"),
    ("プロシエクト", "プロジェクト"),
    ("プロシェクト", "プロジェクト"),
    ("ブロシェクト", "プロジェクト"),
    ("登義型式", "登録型式"),
    ("受録型式", "登録型式"),
    ("愛操型式", "登録型式"),
    ("愛祭型式", "登録型式"),
    ("豊季型式", "登録型式"),
    ("一無型式", "登録型式"),
    ("モテル名", "モデル名"),
    ("モデレ名", "モデル名"),
    ("モラル名", "モデル名"),
    ("モデレイャー", "モデルイヤー"),
    ("モデレイャミ", "モデルイヤー"),
    ("モデレイャ", "モデルイヤー"),
    ("モテレイャ", "モデルイヤー"),
    ("モゴルイヤ", "モデルイヤー"),
    ("モテルイキー", "モデルイヤー"),
    ("モデレイモ", "モデルイヤー"),
    ("千画コード", "計画コード"),
    ("千面コード", "計画コード"),
    ("千西コード", "計画コード"),
    ("計画ヨード", "計画コード"),
    ("計画コ三ド", "計画コード"),
    ("計画コヨド", "計画コード"),
    ("計西コヨド", "計画コード"),
    ("千画コヨト", "計画コード"),
    ("千画コ三ト", "計画コード"),
    ("仕問地コード", "仕向地コード"),
    ("仕向地ヨード", "仕向地コード"),
    ("仕向地コート", "仕向地コード"),
    ("仕向地コ一ト", "仕向地コード"),
    ("仕向地国ヨト", "仕向地コード"),
    ("出向地ゴ=ト", "仕向地コード"),
    ("出向地国当ト", "仕向地コード"),
    ("上向地国当ト", "仕向地コード"),
    ("山向地コート", "仕向地コード"),
    ("検素", "検索"),
    ("経由oみ", "経由のみ"),
    ("経由ｏみ", "経由のみ"),
    ("々スクを起動", "タスクを起動"),
)

_TRAILING_JUNK = re.compile(r"[!！]+$")


def correct_ocr_text(text: str) -> str:
    """Apply cheap deterministic OCR repairs before translation (single pass)."""

    value = (text or "").strip()
    if not value:
        return value
    # Longest-first, one pass — avoids chained damage like プロジェクト→ププロジェクト.
    for bad, good in sorted(_SUBSTITUTIONS, key=lambda pair: len(pair[0]), reverse=True):
        if bad in value:
            value = value.replace(bad, good)
    if value.endswith(("!", "！")) and "：" not in value and ":" not in value:
        value = _TRAILING_JUNK.sub("", value)
    return value
