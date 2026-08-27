import pytest

from pylens.translate.argos import ArgosTranslator
from pylens.translate.factory import create_translator
from pylens.translate.google import GoogleTranslator


def test_factory_creates_argos_with_project_model_path():
    translator = create_translator("argos")
    assert isinstance(translator, ArgosTranslator)


def test_factory_creates_google_provider():
    translator = create_translator("google")
    assert isinstance(translator, GoogleTranslator)
    translator.close()


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unknown translation engine"):
        create_translator("other")
