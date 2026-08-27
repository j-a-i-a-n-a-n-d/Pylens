import json

from pylens.translate.service import TranslationService


def test_google_json_assembly():
    """Mirror WinLens sentence-array join logic."""
    body = json.loads('[[["Hello","こんにちは",null,null,10]],null,"ja"]')
    sentences = body[0]
    parts = []
    for s in sentences:
        if isinstance(s, list) and s and isinstance(s[0], str):
            parts.append(s[0])
    assert "".join(parts) == "Hello"


def test_preserves_sql_keywords_without_cjk():
    svc = TranslationService()
    assert svc.translate("case when then AND", "en") == "case when then AND"
    svc.close()
