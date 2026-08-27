from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir
from typing import Any

from PIL import Image

from pylens.models import TextBlock

logger = logging.getLogger("pylens.ocr")


def ocr_debug_root() -> Path:
    root = Path(gettempdir()) / "pylens_ocr"
    root.mkdir(parents=True, exist_ok=True)
    return root


def image_fingerprint(image: Image.Image) -> str:
    """Stable content hash so you can compare 'same data' across runs."""
    rgb = image.convert("RGB")
    digest = hashlib.sha256(rgb.tobytes()).hexdigest()
    return f"{rgb.width}x{rgb.height}:{digest[:16]}"


class OcrDebugSession:
    """
    Writes one folder per OCR run under %TEMP%/pylens_ocr/<timestamp>/
    so you can compare identical captures that produce different text.
    """

    def __init__(self, enabled: bool, engine: str) -> None:
        self.enabled = enabled
        self.engine = engine
        self.dir: Path | None = None
        self._log_path: Path | None = None
        if not enabled:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.dir = ocr_debug_root() / f"{stamp}_{engine}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self.dir / "ocr.log"
        self.write(f"session_dir={self.dir}")
        self.write(f"engine={engine}")

    def write(self, line: str) -> None:
        msg = f"[{datetime.now():%H:%M:%S.%f}] {line}"
        logger.info(msg)
        if not self.enabled or self._log_path is None:
            return
        try:
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass

    def save_image(self, name: str, image: Image.Image) -> None:
        if not self.enabled or self.dir is None:
            return
        path = self.dir / name
        try:
            image.save(path)
            self.write(f"saved_image={path.name} size={image.size}")
        except Exception as ex:
            self.write(f"save_image_failed name={name} err={ex}")

    def save_json(self, name: str, payload: Any) -> None:
        if not self.enabled or self.dir is None:
            return
        path = self.dir / name
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.write(f"saved_json={path.name}")
        except Exception as ex:
            self.write(f"save_json_failed name={name} err={ex}")

    def log_blocks(self, stage: str, blocks: list[TextBlock]) -> None:
        rows = [
            {
                "text": b.original,
                "rect": list(b.rect),
                "translated": b.translated,
            }
            for b in blocks
        ]
        self.write(f"{stage}_count={len(blocks)}")
        self.save_json(f"{stage}_blocks.json", rows)


def configure_ocr_logging() -> None:
    """Ensure pylens.ocr logs also go to %TEMP%/pylens_ocr/ocr_global.log."""
    root = ocr_debug_root()
    global_log = root / "ocr_global.log"
    target = str(global_log.resolve())
    for h in logger.handlers:
        if isinstance(h, logging.FileHandler) and Path(h.baseFilename).resolve() == Path(target):
            return
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    fh = logging.FileHandler(global_log, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(fh)
