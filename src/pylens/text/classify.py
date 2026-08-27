from __future__ import annotations

import re
from typing import Literal

TextKind = Literal["skip", "ja", "en", "mixed"]

_HAS_JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
_HAS_LATIN = re.compile(r"[A-Za-z]")
_URL = re.compile(r"^(?:https?://|www\.)\S+$", re.IGNORECASE)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_FORMULA = re.compile(r"^=\s*[A-Za-z][A-Za-z0-9_.]*\s*\(.*\)$")
_DATE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$")
_CURRENCY = re.compile(r"^[¥￥$€£]\s*[\d,.]+$")
_NUMBER = re.compile(r"^[+-]?[\d,.]+%?$")
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*\d[A-Za-z0-9_-]*$")
_SQL_START = re.compile(
    r"^(?:SELECT|INSERT|UPDATE|DELETE|WITH|CREATE|ALTER|DROP)\b",
    re.IGNORECASE,
)
_SQL_ONLY = re.compile(
    r"^(?:(?:SELECT|FROM|WHERE|JOIN|INNER|LEFT|RIGHT|OUTER|ON|AS|CASE|WHEN|THEN|"
    r"ELSE|END|AND|OR|NOT|NULL|TRUE|FALSE|IN|IS|EXISTS)\b|[\s*_=<>!(),.;'\"+\-/])+$",
    re.IGNORECASE,
)


def classify_span(text: str) -> TextKind:
    """Classify OCR text so non-language content can bypass translation."""

    value = text.strip()
    if not value or _should_skip(value):
        return "skip"

    has_japanese = _HAS_JAPANESE.search(value) is not None
    has_latin = _HAS_LATIN.search(value) is not None

    if has_japanese and has_latin:
        return "mixed"
    if has_japanese:
        return "ja"
    if has_latin:
        return "en"
    return "skip"


def _should_skip(text: str) -> bool:
    return _SQL_START.match(text) is not None or any(
        pattern.fullmatch(text) is not None
        for pattern in (_URL, _EMAIL, _FORMULA, _DATE, _CURRENCY, _NUMBER, _IDENTIFIER, _SQL_ONLY)
    )
