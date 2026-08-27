import json

from pylens.paths import default_glossary_path
from pylens.text.glossary import Glossary


def _write_glossary(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_exact_translation_lookup(tmp_path):
    default = tmp_path / "default.json"
    _write_glossary(default, {"ja-en": {"受注": "Order"}, "en-ja": {}})

    glossary = Glossary.from_paths([default])

    assert glossary.lookup("受注", "ja", "en") == "Order"
    assert glossary.lookup("受注番号", "ja", "en") is None


def test_later_file_overrides_default(tmp_path):
    default = tmp_path / "default.json"
    user = tmp_path / "user.json"
    _write_glossary(default, {"ja-en": {"受注": "Order"}})
    _write_glossary(user, {"ja-en": {"受注": "Sales Order"}})

    glossary = Glossary.from_paths([default, user])

    assert glossary.lookup("受注", "ja", "en") == "Sales Order"


def test_missing_glossary_file_is_ignored(tmp_path):
    glossary = Glossary.from_paths([tmp_path / "missing.json"])
    assert glossary.lookup("受注", "ja", "en") is None


def test_default_project_glossary_is_available():
    glossary = Glossary.from_paths([default_glossary_path()])
    assert glossary.lookup("受注", "ja", "en") == "Order"
    assert glossary.lookup("save", "en", "ja") == "保存する"
    assert glossary.lookup("Save", "en", "ja") == "保存する"
    assert glossary.lookup("and", "en", "ja") == "および"


def test_default_glossary_stays_in_lookup_budget():
    data = json.loads(default_glossary_path().read_text(encoding="utf-8"))
    total = sum(len(entries) for entries in data.values())
    assert 1_000 <= total <= 10_000
