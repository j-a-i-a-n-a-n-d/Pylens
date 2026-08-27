from pylens.models import TextBlock
from pylens.ocr.preprocess import choose_scale, merge_line_fragments
from pylens.translate.service import TranslationService


def test_choose_scale_limits_upscale_and_downscales_large_images():
    assert choose_scale(100, 100) == 3.0
    assert choose_scale(5000, 5000) == 2560 / 5000


def test_merge_line_fragments():
    a = TextBlock(original="こんにちは", rect=(10, 10, 40, 12))
    b = TextBlock(original="世界", rect=(55, 11, 30, 12))
    merged = merge_line_fragments([a, b])
    assert len(merged) == 1
    assert "こんにちは" in merged[0].original
    assert "世界" in merged[0].original


def test_google_parse_shape():
    svc = TranslationService()
    assert svc.translate("  ", "en") == "  "
    svc.close()
