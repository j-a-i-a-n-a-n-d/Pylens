from __future__ import annotations

import importlib.util
import shutil
from typing import TYPE_CHECKING

from PIL import Image

from pylens.models import TextBlock
from pylens.ocr.base import OcrAdapter, OcrEngineId
from pylens.ocr.preprocess import choose_scale, prepare_for_ocr, postprocess_ocr_blocks

if TYPE_CHECKING:
    import pytesseract


def tesseract_available() -> bool:
    """Check if Tesseract is available."""
    return (
        importlib.util.find_spec("pytesseract") is not None and
        shutil.which("tesseract") is not None
    )


def tesseract_languages() -> list[str]:
    """Return supported Tesseract languages."""
    if not tesseract_available():
        return []
    try:
        import pytesseract
        return pytesseract.get_languages()
    except Exception:
        return []


def has_tesseract_language(lang: str) -> bool:
    """Check if a language is supported by Tesseract."""
    supported = [l.lower() for l in tesseract_languages()]
    lang_lower = lang.lower()
    # Handle language codes like 'jpn' for Japanese, 'eng' for English
    lang_map = {
        "ja": "jpn",
        "en": "eng",
        "zh": "chi_sim",
        "zh-cn": "chi_sim",
        "zh-tw": "chi_tra",
        "ko": "kor",
    }
    tesseract_lang = lang_map.get(lang_lower, lang_lower)
    return tesseract_lang in supported


class TesseractOcrAdapter(OcrAdapter):
    """Linux OCR using Tesseract."""

    id = OcrEngineId.LINUX_TESSERACT
    display_name = "Tesseract (Linux)"

    def __init__(self) -> None:
        self._tesseract = None
        self._init_tesseract()

    def _init_tesseract(self) -> None:
        try:
            import pytesseract
            self._tesseract = pytesseract
        except ImportError:
            pass

    def is_available(self) -> bool:
        return self._tesseract is not None and shutil.which("tesseract") is not None

    def is_ready(self, language: str = "ja") -> bool:
        return self.is_available() and has_tesseract_language(language)

    def readiness_message(self, language: str = "ja") -> str:
        if not self.is_available():
            return (
                "Tesseract not available. "
                "Install tesseract-ocr and pytesseract (pip install pytesseract)."
            )
        if self.is_ready(language):
            return f"Ready (Tesseract OCR for {language})."
        return f"Language '{language}' not installed for Tesseract. Install tesseract-ocr-{language}."

    def recognize(
        self,
        image: Image.Image,
        language: str = "ja",
        *,
        debug: bool = False,
        profile: str = "balanced",
    ) -> list[TextBlock]:
        if not self.is_available():
            raise RuntimeError(self.readiness_message())
        if not self.is_ready(language):
            raise RuntimeError(self.readiness_message(language))

        from pylens.ocr.debug import OcrDebugSession, configure_ocr_logging, image_fingerprint

        if debug:
            configure_ocr_logging()
        session = OcrDebugSession(enabled=debug, engine="tesseract")

        rgb = image.convert("RGB")
        scale = choose_scale(rgb.width, rgb.height, profile)
        prepared = prepare_for_ocr(rgb, scale)

        session.write(f"fingerprint={image_fingerprint(rgb)}")
        session.write(f"input={rgb.size} scale={scale:.3f} prepared={prepared.size}")
        session.save_image("01_capture.png", rgb)
        session.save_image("02_prepared.png", prepared)

        # Map language codes
        lang_map = {
            "ja": "jpn",
            "en": "eng",
            "zh": "chi_sim",
            "zh-cn": "chi_sim",
            "zh-tw": "chi_tra",
            "ko": "kor",
        }
        tess_lang = lang_map.get(language.lower(), language.lower())

        # Run Tesseract
        try:
            data = self._tesseract.image_to_data(
                prepared,
                lang=tess_lang,
                output_type=self._tesseract.Output.DICT
            )
        except Exception as e:
            raise RuntimeError(f"Tesseract OCR failed: {e}")

        blocks: list[TextBlock] = []
        n_boxes = len(data.get("text", []))

        for i in range(n_boxes):
            text = data["text"][i].strip()
            if not text:
                continue

            conf = float(data["conf"][i]) if data["conf"][i] != "-1" else 0
            if conf < 30:  # Skip low confidence
                session.write(f"drop low-conf text={text!r} conf={conf}")
                continue

            x = data["left"][i]
            y = data["top"][i]
            w = data["width"][i]
            h = data["height"][i]

            # Convert back to original image coordinates
            x_orig = int(x / scale)
            y_orig = int(y / scale)
            w_orig = max(1, int(w / scale))
            h_orig = max(1, int(h / scale))

            blocks.append(TextBlock(
                original=text,
                rect=(x_orig, y_orig, w_orig, h_orig)
            ))

            session.write(f"text={text!r} conf={conf:.1f} rect=({x_orig}, {y_orig}, {w_orig}, {h_orig})")

        session.log_blocks("05_post", blocks)
        for b in blocks:
            session.write(f"post text={b.original!r} rect={b.rect}")

        post = postprocess_ocr_blocks(blocks)
        if session.dir is not None:
            session.write(f"DONE compare folder: {session.dir}")

        return post