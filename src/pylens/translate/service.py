from __future__ import annotations

import re
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

from pylens.models import TextBlock
from pylens.paths import default_glossary_path
from pylens.settings import config_dir as appdata_dir
from pylens.text.classify import classify_span
from pylens.text.fragments import is_untranslatable_fragment
from pylens.text.glossary import Glossary
from pylens.translate.base import Translator
from pylens.translate.cache import TranslationCache
from pylens.translate.google import GoogleTranslator

_SCRIPT_SEGMENTS = re.compile(
    r"([\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]+|"
    r"[^\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]+)"
)


class TranslationService:
    """Route text through skip rules, glossary, cache, and one provider."""

    def __init__(
        self,
        engine: Translator | None = None,
        cache: TranslationCache | None = None,
        glossary: Glossary | None = None,
        max_workers: int = 6,
    ) -> None:
        self._engine = engine or GoogleTranslator()
        self._cache = cache or TranslationCache(appdata_dir() / "translation_cache.sqlite")
        self._glossary = glossary or Glossary.from_paths(
            [default_glossary_path(), appdata_dir() / "glossary.json"]
        )
        self._max_workers = max_workers

    def close(self) -> None:
        self._engine.close()
        self._cache.close()

    def prepare(self, source_lang: str, target_lang: str) -> None:
        self._engine.prepare(source_lang, target_lang)

    def __enter__(self) -> TranslationService:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def translate(self, text: str, target_lang: str, source_hint: str | None = None) -> str:
        target = target_lang.split("-")[0].lower()
        kind = classify_span(text)
        if kind == "skip":
            return text
        if kind == target:
            return text
        if is_untranslatable_fragment(text):
            return ""
        if kind == "mixed":
            return self._translate_mixed(text, target)

        source = source_hint or kind
        return self._translate_one(text, source, target)

    def translate_blocks(
        self,
        blocks: Iterable[TextBlock],
        target_lang: str,
    ) -> list[TextBlock]:
        block_list = list(blocks)
        if not block_list:
            return []

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            translations = list(pool.map(lambda b: self.translate(b.original, target_lang), block_list))

        for index, block in enumerate(block_list):
            translated = translations[index]
            if not translated.strip():
                translated = self._translate_with_neighbors(block_list, index, target_lang)
            block.translated = translated
        return block_list

    def _translate_with_neighbors(
        self,
        blocks: list[TextBlock],
        index: int,
        target_lang: str,
    ) -> str:
        current = blocks[index].original
        candidates: list[str] = []
        if index > 0:
            candidates.append(f"{blocks[index - 1].original} {current}")
        if index + 1 < len(blocks):
            candidates.append(f"{current} {blocks[index + 1].original}")
        if index > 0 and index + 1 < len(blocks):
            candidates.append(
                f"{blocks[index - 1].original} {current} {blocks[index + 1].original}"
            )

        for merged in candidates:
            result = self._translate_merged(merged, target_lang)
            if result.strip():
                return result
        return ""

    def _translate_merged(self, text: str, target_lang: str) -> str:
        target = target_lang.split("-")[0].lower()
        kind = classify_span(text)
        if kind in ("skip", target):
            return text
        if kind == "mixed":
            return self._translate_mixed(text, target)
        source = kind if kind in ("ja", "en") else "ja"
        return self._translate_one(text, source, target)

    def _translate_mixed(self, text: str, target_lang: str) -> str:
        translated: list[str] = []
        for segment in _SCRIPT_SEGMENTS.findall(text):
            kind = classify_span(segment)
            if kind in ("skip", target_lang):
                translated.append(segment)
            elif kind in ("ja", "en"):
                if is_untranslatable_fragment(segment):
                    translated.append("")
                else:
                    translated.append(self._translate_one(segment, kind, target_lang))
            else:
                translated.append(segment)
        return "".join(translated)

    def _translate_one(self, text: str, source_lang: str, target_lang: str) -> str:
        glossary_value = self._glossary.lookup(text, source_lang, target_lang)
        if glossary_value is not None:
            return glossary_value

        cached = self._cache.get(source_lang, target_lang, text)
        if cached is not None:
            return cached

        translated = self._engine.translate(text, source_lang, target_lang)
        self._cache.set(source_lang, target_lang, text, translated)
        return translated
