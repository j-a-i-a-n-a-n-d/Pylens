from pylens.translate.argos import ArgosTranslator, split_offline_sentences


def test_required_package_paths_are_project_local(tmp_path):
    translator = ArgosTranslator(tmp_path)

    assert translator.package_path("ja", "en") == tmp_path / "translate-ja_en-1_1.argosmodel"
    assert translator.package_path("en", "ja") == tmp_path / "translate-en_ja-1_1.argosmodel"


def test_missing_argos_library_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr("pylens.translate.argos.importlib.util.find_spec", lambda _name: None)
    translator = ArgosTranslator(tmp_path)

    assert translator.is_library_available() is False
    assert translator.is_ready("ja", "en") is False
    assert "not installed" in translator.readiness_message("ja", "en").lower()


def test_offline_sentence_split_keeps_ui_labels_intact():
    assert split_offline_sentences("受注管理システム") == ["受注管理システム"]


def test_offline_sentence_split_breaks_on_japanese_period():
    assert split_offline_sentences("はい。いいえ。") == ["はい。", "いいえ。"]


def test_configure_environment_uses_offline_sentence_split(tmp_path):
    translator = ArgosTranslator(tmp_path)
    translator._configure_environment()
    from argostranslate.sbd import StanzaSentencizer

    sentencizer = StanzaSentencizer.__new__(StanzaSentencizer)
    assert StanzaSentencizer.split_sentences(sentencizer, "受注管理システム") == ["受注管理システム"]


class _Lang:
    def __init__(self, code, targets=()):
        self.code = code
        self._targets = set(targets)

    def get_translation(self, other):
        return object() if other.code in self._targets else None


def test_pair_is_installed_requires_a_real_translation_link():
    from pylens.translate.argos import pair_is_installed

    ja = _Lang("ja", targets=("en",))
    en = _Lang("en")
    langs = [ja, en]
    assert pair_is_installed(langs, "ja", "en") is True
    assert pair_is_installed(langs, "en", "ja") is False
    assert pair_is_installed(langs, "ja", "fr") is False
