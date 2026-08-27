from __future__ import annotations

import re

_HAS_JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
_PARTICLE_FRAGMENT = re.compile(
    r"^(?:"
    r"が|を|に|で|は|も|の|と|から|まで|より|へ|や|か|"
    r"されるが|だが|けど|ので|のに|"
    r"[\u3040-\u30ff]{1,2}[、。]?$"
    r")$"
)
_GRAMMAR_TAIL = re.compile(r"(?:が|を|に|で|は|も|の|と|から|まで|より|され|られ)[、。]?$")


def is_untranslatable_fragment(text: str) -> bool:
    """Return True when text is too fragmentary for standalone NMT."""

    value = text.strip()
    if not value or not _HAS_JAPANESE.search(value):
        return False
    if _PARTICLE_FRAGMENT.match(value):
        return True
    if len(value) <= 6 and _GRAMMAR_TAIL.search(value):
        return True
    return False
