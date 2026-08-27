from __future__ import annotations

import asyncio
import io

from PIL import Image

from pylens.models import TextBlock
from pylens.ocr.base import OcrAdapter, OcrEngineId
from pylens.ocr.preprocess import choose_scale, prepare_for_ocr, postprocess_ocr_blocks


def windows_language_tag(lang: str) -> str:
    mapping = {
        "ja": "ja",
        "jp": "ja",
        "japanese": "ja",
        "en": "en-US",
        "zh": "zh-Hans",
        "zh-cn": "zh-Hans",
        "ko": "ko",
        "kr": "ko",
    }
    return mapping.get(lang.lower(), lang)


def list_windows_ocr_languages() -> list[str]:
    try:
        from winsdk.windows.media.ocr import OcrEngine

        return [str(lang.language_tag) for lang in OcrEngine.available_recognizer_languages]
    except Exception:
        return []


def has_windows_ocr_language(lang: str) -> bool:
    tag = windows_language_tag(lang).lower()
    available = [a.lower() for a in list_windows_ocr_languages()]
    return any(a == tag or a.startswith(tag + "-") or tag.startswith(a) for a in available)


async def _recognize_async(
    image: Image.Image,
    lang: str,
    profile: str = "balanced",
) -> list[TextBlock]:
    from winsdk.windows.globalization import Language
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    tag = windows_language_tag(lang)
    language = Language(tag)
    if not OcrEngine.is_language_supported(language):
        raise RuntimeError(
            f"Windows OCR language '{tag}' is not installed. "
            "Settings → Time & Language → Language → Japanese → add OCR."
        )
    engine = OcrEngine.try_create_from_language(language)
    if engine is None:
        raise RuntimeError(f"Could not create Windows OCR engine for '{tag}'.")

    scale = choose_scale(image.width, image.height, profile)
    prepared = prepare_for_ocr(image.convert("RGB"), scale)

    buf = io.BytesIO()
    prepared.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(bytearray(png_bytes))
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    software_bitmap = await decoder.get_software_bitmap_async()
    result = await engine.recognize_async(software_bitmap)

    blocks: list[TextBlock] = []
    for line in result.lines:
        text = (line.text or "").strip()
        if not text:
            continue
        words = list(line.words)
        if not words:
            continue
        xs = [w.bounding_rect.x for w in words]
        ys = [w.bounding_rect.y for w in words]
        rights = [w.bounding_rect.x + w.bounding_rect.width for w in words]
        bottoms = [w.bounding_rect.y + w.bounding_rect.height for w in words]
        x = min(xs) / scale
        y = min(ys) / scale
        w = (max(rights) - min(xs)) / scale
        h = (max(bottoms) - min(ys)) / scale
        blocks.append(
            TextBlock(
                original=text,
                rect=(int(x), int(y), max(1, int(w)), max(1, int(h))),
            )
        )
    return postprocess_ocr_blocks(blocks)


class WindowsOcrAdapter(OcrAdapter):
    id = OcrEngineId.WINDOWS
    display_name = "Windows OCR"

    def is_available(self) -> bool:
        try:
            import importlib.util

            return importlib.util.find_spec("winsdk") is not None
        except Exception:
            return False

    def is_ready(self, language: str) -> bool:
        return self.is_available() and has_windows_ocr_language(language)

    def readiness_message(self, language: str) -> str:
        if not self.is_available():
            return "winsdk is not installed."
        packs = ", ".join(list_windows_ocr_languages()) or "(none)"
        if self.is_ready(language):
            return f"Ready. Installed OCR packs: {packs}"
        tag = windows_language_tag(language)
        return (
            f"Missing Windows OCR pack for '{tag}'. "
            "Settings → Time & Language → Language → add OCR. "
            f"Installed: {packs}"
        )

    def recognize(
        self,
        image: Image.Image,
        language: str = "ja",
        *,
        debug: bool = False,
        profile: str = "balanced",
    ) -> list[TextBlock]:
        from pylens.ocr.debug import OcrDebugSession, configure_ocr_logging, image_fingerprint

        if debug:
            configure_ocr_logging()
        session = OcrDebugSession(enabled=debug, engine="windows")
        session.write(f"fingerprint={image_fingerprint(image)}")
        session.write(f"input={image.size} language={language}")
        session.save_image("01_capture.png", image.convert("RGB"))

        if not self.is_ready(language):
            raise RuntimeError(self.readiness_message(language))
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Nested loop edge case: still fall through to asyncio.run.
                pass
            blocks = asyncio.run(_recognize_async(image, language, profile))
        except RuntimeError:
            blocks = asyncio.run(_recognize_async(image, language, profile))

        session.log_blocks("05_post", blocks)
        for b in blocks:
            session.write(f"post text={b.original!r} rect={b.rect}")
        if session.dir is not None:
            session.write(f"DONE compare folder: {session.dir}")
        return blocks
