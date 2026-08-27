from pylens.settings import Settings


def test_models_never_auto_download_by_default():
    assert Settings().paddle_auto_download is False


def test_balanced_ocr_profile_is_default():
    assert Settings().ocr_profile == "balanced"


def test_offline_translation_is_default():
    assert Settings().translation_engine == "argos"
