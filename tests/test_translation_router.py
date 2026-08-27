from pathlib import Path

from pylens.text.glossary import Glossary
from pylens.translate.cache import TranslationCache
from pylens.translate.service import TranslationService


class RecordingTranslator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        self.calls.append((text, source_lang, target_lang))
        return f"{target_lang}:{text}"

    def close(self) -> None:
        pass


def _service(tmp_path: Path, engine: RecordingTranslator, glossary=None):
    return TranslationService(
        engine=engine,
        cache=TranslationCache(tmp_path / "cache.sqlite"),
        glossary=glossary or Glossary(),
    )


def test_skip_content_never_reaches_translation_engine(tmp_path):
    engine = RecordingTranslator()
    service = _service(tmp_path, engine)

    assert service.translate("2026-08-24", "en") == "2026-08-24"
    assert engine.calls == []
    service.close()


def test_text_already_in_target_language_is_preserved(tmp_path):
    engine = RecordingTranslator()
    service = _service(tmp_path, engine)

    assert service.translate("Order status", "en") == "Order status"
    assert service.translate("処理中", "ja") == "処理中"
    assert engine.calls == []
    service.close()


def test_glossary_precedes_translation_engine(tmp_path):
    engine = RecordingTranslator()
    glossary = Glossary({"ja-en": {"受注": "Order"}})
    service = _service(tmp_path, engine, glossary)

    assert service.translate("受注", "en") == "Order"
    assert engine.calls == []
    service.close()


def test_translation_result_is_cached(tmp_path):
    engine = RecordingTranslator()
    service = _service(tmp_path, engine)

    assert service.translate("処理中", "en") == "en:処理中"
    assert service.translate("処理中", "en") == "en:処理中"
    assert engine.calls == [("処理中", "ja", "en")]
    service.close()


def test_mixed_text_translates_only_the_non_target_script(tmp_path):
    engine = RecordingTranslator()
    service = _service(tmp_path, engine)

    assert service.translate("Status 処理中", "en") == "Status en:処理中"
    assert engine.calls == [("処理中", "ja", "en")]
    service.close()
