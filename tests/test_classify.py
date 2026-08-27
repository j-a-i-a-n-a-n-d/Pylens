import pytest

from pylens.text.classify import classify_span


@pytest.mark.parametrize(
    "text",
    [
        "",
        "123456",
        "A00123",
        "2026/08/23",
        "2026-08-23",
        "¥120,000",
        "$5,000",
        "ABC-123",
        "https://example.com/a",
        "foo@yamaha-motor.com",
        "QSD01_01",
        "=SUM(A1:A10)",
        "SELECT * FROM T",
    ],
)
def test_non_language_content_is_skipped(text: str):
    assert classify_span(text) == "skip"


def test_japanese_text_is_identified():
    assert classify_span("受注管理") == "ja"


def test_english_text_is_identified():
    assert classify_span("Order status") == "en"


def test_mixed_japanese_and_english_is_identified():
    assert classify_span("Status 処理中") == "mixed"
