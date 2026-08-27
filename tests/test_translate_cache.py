from pylens.text.normalize import cache_key, normalize_for_cache
from pylens.translate.cache import TranslationCache


def test_normalization_folds_width_and_whitespace():
    assert normalize_for_cache("  ＡＢＣ   受注  ") == "ABC 受注"


def test_cache_key_includes_language_direction():
    text = "受注"
    assert cache_key("ja", "en", text) != cache_key("en", "ja", text)


def test_cache_persists_between_instances(tmp_path):
    db_path = tmp_path / "translations.sqlite"
    first = TranslationCache(db_path)
    first.set("ja", "en", "  受注  ", "Order")
    first.close()

    second = TranslationCache(db_path)
    assert second.get("ja", "en", "受注") == "Order"
    assert second.get("ja", "ja", "受注") is None
    second.close()


def test_empty_text_is_not_cached(tmp_path):
    cache = TranslationCache(tmp_path / "translations.sqlite")
    cache.set("ja", "en", "   ", "ignored")
    assert cache.get("ja", "en", "   ") is None
    cache.close()
