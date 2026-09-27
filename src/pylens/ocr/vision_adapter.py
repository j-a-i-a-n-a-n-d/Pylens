from __future__ import annotations

import io
import importlib.util
from typing import TYPE_CHECKING

from PIL import Image

from pylens.models import TextBlock
from pylens.ocr.base import OcrAdapter, OcrEngineId
from pylens.ocr.preprocess import choose_scale, prepare_for_ocr, postprocess_ocr_blocks

if TYPE_CHECKING:
    import Vision
    import Quartz
    import Foundation


def vision_framework_available() -> bool:
    """Check if Vision framework is available via PyObjC."""
    return (
        importlib.util.find_spec("Vision") is not None
        and importlib.util.find_spec("Quartz") is not None
    )


def macos_ocr_languages() -> list[str]:
    """Return supported macOS OCR languages."""
    # Vision framework supports many languages
    return [
        "ja", "en-US", "zh-Hans", "zh-Hant", "ko",
        "fr", "de", "it", "es", "pt", "ru",
        "ar", "hi", "th", "vi",
    ]


def has_vision_language(lang: str) -> bool:
    """Check if a language is supported by Vision."""
    supported = [l.lower() for l in macos_ocr_languages()]
    lang_lower = lang.lower()
    return any(lang_lower == s or lang_lower.startswith(s.split("-")[0]) for s in supported)


class VisionOcrAdapter(OcrAdapter):
    """macOS native OCR using Apple Vision framework."""

    id = OcrEngineId("macos_vision")
    display_name = "macOS Vision (Native)"

    def __init__(self) -> None:
        self._vision = None
        self._quartz = None
        self._foundation = None
        self._init_frameworks()

    def _init_frameworks(self) -> None:
        try:
            import Vision
            import Quartz
            import Foundation
            self._vision = Vision
            self._quartz = Quartz
            self._foundation = Foundation
        except ImportError:
            pass

    def is_available(self) -> bool:
        return self._vision is not None and self._quartz is not None

    def is_ready(self, language: str = "ja") -> bool:
        return self.is_available() and has_vision_language(language)

    def readiness_message(self, language: str = "ja") -> str:
        if not self.is_available():
            return (
                "Apple Vision framework not available. "
                "Install pyobjc-framework-Vision and pyobjc-framework-Quartz."
            )
        if self.is_ready(language):
            return f"Ready (native macOS OCR for {language})."
        return f"Language '{language}' not supported by Vision framework."

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
        session = OcrDebugSession(enabled=debug, engine="vision")

        rgb = image.convert("RGB")
        scale = choose_scale(rgb.width, rgb.height, profile)
        prepared = prepare_for_ocr(rgb, scale)

        session.write(f"fingerprint={image_fingerprint(rgb)}")
        session.write(f"input={rgb.size} scale={scale:.3f} prepared={prepared.size}")
        session.save_image("01_capture.png", rgb)
        session.save_image("02_prepared.png", prepared)

        # Convert PIL image to CGImage for Vision
        cg_image = self._pil_to_cgimage(prepared)
        if cg_image is None:
            raise RuntimeError("Failed to convert image for Vision framework")

        # Create Vision request
        request = self._vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(self._vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)
        request.setRecognitionLanguages_([language])

        # Perform OCR
        handler = self._vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
        error = None
        success = handler.performRequests_error_([request], error)

        blocks: list[TextBlock] = []

        if success and request.results():
            for observation in request.results():
                text = observation.text().strip()
                if not text:
                    continue

                # Get bounding box (normalized coordinates 0-1)
                bbox = observation.boundingBox()
                x = bbox.origin.x * prepared.width
                y = (1 - bbox.origin.y - bbox.size.height) * prepared.height  # Vision uses bottom-left origin
                w = bbox.size.width * prepared.width
                h = bbox.size.height * prepared.height

                # Convert back to original image coordinates
                x_orig = int(x / scale)
                y_orig = int(y / scale)
                w_orig = max(1, int(w / scale))
                h_orig = max(1, int(h / scale))

                blocks.append(TextBlock(
                    original=text,
                    rect=(x_orig, y_orig, w_orig, h_orig)
                ))

                session.write(f"text={text!r} rect=({x_orig}, {y_orig}, {w_orig}, {h_orig})")

        session.log_blocks("05_post", blocks)
        for b in blocks:
            session.write(f"post text={b.original!r} rect={b.rect}")

        post = postprocess_ocr_blocks(blocks)
        if session.dir is not None:
            session.write(f"DONE compare folder: {session.dir}")

        return post

    def _pil_to_cgimage(self, image: Image.Image):
        """Convert PIL Image to CGImage for Vision framework."""
        if not self._quartz:
            return None

        # Save to bytes as PNG
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        png_data = buf.getvalue()

        # Create CGImage from PNG data via Foundation.NSData and Quartz.CIImage
        ns_data = self._foundation.NSData.dataWithBytes_length_(png_data, len(png_data))
        ci_image = self._quartz.CIImage.imageWithData_(ns_data)

        if ci_image is None:
            return None

        # Convert CIImage to CGImage
        context = self._quartz.CIContext.contextWithOptions_(None)
        cg_image = context.createCGImage_fromRect_(ci_image, ci_image.extent())

        return cg_image