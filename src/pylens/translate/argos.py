from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

# Argos 1.11 defaults to Stanza SBD, which fetches resources.json from GitHub.
# Overlay text is short; split locally and never contact the network.
_OFFLINE_SENTENCE_RE = re.compile(r"(?<=[。！？.!?])\s*")
_OFFLINE_SBD_PATCHED = False


def split_offline_sentences(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    parts = [part.strip() for part in _OFFLINE_SENTENCE_RE.split(stripped) if part.strip()]
    return parts or [stripped]


def pair_is_installed(languages, source_lang: str, target_lang: str) -> bool:
    source = next((lang for lang in languages if lang.code == source_lang), None)
    target = next((lang for lang in languages if lang.code == target_lang), None)
    if source is None or target is None:
        return False
    translation = source.get_translation(target)
    return translation is not None and type(translation).__name__ != "IdentityTranslation"


_PACKAGE_NAMES = {
    ("ja", "en"): "translate-ja_en-1_1.argosmodel",
    ("en", "ja"): "translate-en_ja-1_1.argosmodel",
}

_SUPPORTED_PAIRS = frozenset(_PACKAGE_NAMES)


def supports_pair(source_lang: str, target_lang: str) -> bool:
    return (source_lang.lower(), target_lang.lower()) in _SUPPORTED_PAIRS


class ArgosTranslator:
    """Offline JA↔EN provider using only manually supplied model archives."""

    def __init__(self, models_dir: Path) -> None:
        self._models_dir = models_dir
        self._installed_dir = models_dir / "installed"

    def package_path(self, source_lang: str, target_lang: str) -> Path:
        pair = (source_lang.lower(), target_lang.lower())
        try:
            filename = _PACKAGE_NAMES[pair]
        except KeyError as ex:
            raise ValueError(f"Unsupported Argos language pair: {pair[0]}->{pair[1]}") from ex
        return self._models_dir / filename

    def is_library_available(self) -> bool:
        return importlib.util.find_spec("argostranslate") is not None

    def is_ready(self, source_lang: str, target_lang: str) -> bool:
        if not supports_pair(source_lang, target_lang):
            return False
        if not self.is_library_available():
            return False
        self._configure_environment()
        from argostranslate import translate

        return pair_is_installed(translate.get_installed_languages(), source_lang, target_lang)

    def readiness_message(self, source_lang: str, target_lang: str) -> str:
        if not supports_pair(source_lang, target_lang):
            return (
                f"Argos offline supports only JA↔EN (got {source_lang}->{target_lang}). "
                "Set target to en (or ja), or switch Translation to Google / MyMemory."
            )
        if not self.is_library_available():
            return "Argos Translate is not installed (offline Python wheels required)."
        if self.is_ready(source_lang, target_lang):
            return f"Ready: offline {source_lang.upper()} → {target_lang.upper()} translation."
        try:
            archive = self.package_path(source_lang, target_lang)
        except ValueError as ex:
            return str(ex)
        if archive.is_file():
            return f"Local model archive found; it will be installed from {archive}."
        return f"Model archive missing: {archive}"

    def prepare(self, source_lang: str, target_lang: str) -> None:
        """Install a manually supplied archive when the pair is not ready."""

        if not supports_pair(source_lang, target_lang):
            raise ValueError(
                f"Unsupported Argos language pair: {source_lang}->{target_lang}. "
                "Use en or ja, or switch to Google / MyMemory."
            )
        if self.is_ready(source_lang, target_lang):
            return
        self.install_local_package(source_lang, target_lang)
        if not self.is_ready(source_lang, target_lang):
            raise RuntimeError(f"Argos model could not be prepared for {source_lang}->{target_lang}.")

    def install_local_package(self, source_lang: str, target_lang: str) -> None:
        """Install a local archive without contacting a package index."""

        archive = self.package_path(source_lang, target_lang)
        if not archive.is_file():
            raise FileNotFoundError(f"Argos model archive not found: {archive}")
        self._configure_environment()
        from argostranslate import package

        package.install_from_path(archive)

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not self.is_library_available():
            raise RuntimeError(
                "Argos Translate is not installed. Install it from an approved offline wheel."
            )

        self._configure_environment()
        from argostranslate import translate

        source = next(
            (lang for lang in translate.get_installed_languages() if lang.code == source_lang),
            None,
        )
        target = next(
            (lang for lang in translate.get_installed_languages() if lang.code == target_lang),
            None,
        )
        if source is None or target is None:
            raise RuntimeError(
                f"Argos model is not installed for {source_lang}->{target_lang}. "
                f"Place {self.package_path(source_lang, target_lang).name} in {self._models_dir}."
            )
        translation = source.get_translation(target)
        if translation is None or type(translation).__name__ == "IdentityTranslation":
            raise RuntimeError(
                f"Argos model is not installed for {source_lang}->{target_lang}. "
                f"Place {self.package_path(source_lang, target_lang).name} in {self._models_dir}."
            )
        return translation.translate(text)

    def close(self) -> None:
        pass

    def _configure_environment(self) -> None:
        self._installed_dir.mkdir(parents=True, exist_ok=True)
        # Argos reads these settings when its modules are first imported.
        os.environ["ARGOS_PACKAGES_DIR"] = str(self._installed_dir)
        os.environ["ARGOS_DEVICE_TYPE"] = "cpu"
        os.environ.setdefault("ARGOS_CHUNK_TYPE", "ARGOSTRANSLATE")
        if "argostranslate.settings" in sys.modules:
            from argostranslate import settings

            settings.package_data_dir = self._installed_dir
            settings.package_dirs = [self._installed_dir]
        _patch_offline_sentence_boundary_detection()


def _patch_offline_sentence_boundary_detection() -> None:
    global _OFFLINE_SBD_PATCHED
    if _OFFLINE_SBD_PATCHED:
        return
    from argostranslate.sbd import MiniSBDSentencizer, StanzaSentencizer

    StanzaSentencizer.split_sentences = lambda self, text: split_offline_sentences(text)
    MiniSBDSentencizer.split_sentences = lambda self, text: split_offline_sentences(text)
    _OFFLINE_SBD_PATCHED = True
