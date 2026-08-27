from __future__ import annotations

import importlib.util
import io
import os
import shutil
import tarfile
from collections.abc import Callable
from pathlib import Path

import httpx
from PIL import Image

from pylens.models import TextBlock
from pylens.ocr.base import OcrAdapter, OcrEngineId
from pylens.ocr.preprocess import choose_scale, prepare_for_ocr, postprocess_ocr_blocks
from pylens.paths import paddle_cls_dir, paddle_det_dir, paddle_models_dir, paddle_rec_dir

# Japanese-only mobile/infer models (small). Stored under <project>/models/paddle/.
_JAPAN_MODEL_URLS = {
    "det": (
        "https://paddleocr.bj.bcebos.com/PP-OCRv3/multilingual/"
        "Multilingual_PP-OCRv3_det_infer.tar"
    ),
    "rec": (
        "https://paddleocr.bj.bcebos.com/PP-OCRv3/multilingual/"
        "japan_PP-OCRv3_rec_infer.tar"
    ),
    "cls": (
        "https://paddleocr.bj.bcebos.com/dygraph_v2.0/ch/"
        "ch_ppocr_mobile_v2.0_cls_infer.tar"
    ),
}

ProgressCb = Callable[[str], None]


def paddle_package_installed() -> bool:
    try:
        return importlib.util.find_spec("paddleocr") is not None
    except Exception:
        return False


def _dir_has_weights(path: Path) -> bool:
    if not path.exists():
        return False
    patterns = ("*.pdiparams", "inference.pdmodel", "inference.yml", "*.onnx")
    return any(any(path.rglob(pattern)) for pattern in patterns)


def _paddle_home_root() -> Path:
    """Project-local substitute for ~/.paddleocr."""
    return paddle_models_dir() / "_home" / ".paddleocr"


def _find_kind_dir(root: Path, kind: str, tokens: tuple[str, ...]) -> Path | None:
    if not root.exists():
        return None
    candidates: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_dir():
            continue
        blob = f"{path.parent.name}/{path.name}".lower()
        if kind not in blob and kind not in path.name.lower():
            continue
        if any(token.lower() in blob for token in tokens) and _dir_has_weights(path):
            candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda p: len(str(p)))


def _leaf_model_dir(root: Path) -> Path | None:
    """
    Resolve the directory that actually contains inference weights.

    Accepts either flat layout (weights in root) or one nested extract folder
    (e.g. det/Multilingual_PP-OCRv3_det_infer/inference.pdmodel).
    """
    if not root.exists():
        return None
    if any(root.glob("*.pdiparams")) or any(root.glob("inference.pdmodel")):
        return root
    # Prefer a single child dir that holds the weights (manual tar extract).
    children = [p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")]
    for child in children:
        if any(child.glob("*.pdiparams")) or any(child.glob("inference.pdmodel")):
            return child
    # Fallback: any nested weights under root.
    for pattern in ("*.pdiparams", "inference.pdmodel"):
        hits = list(root.rglob(pattern))
        if hits:
            return hits[0].parent
    return None


def japan_model_dirs() -> dict[str, Path] | None:
    """Return det/rec(/cls) dirs if Japanese weights exist under the project."""
    det_p = _leaf_model_dir(paddle_det_dir())
    rec_p = _leaf_model_dir(paddle_rec_dir())
    cls_p = _leaf_model_dir(paddle_cls_dir())
    if det_p and rec_p:
        found: dict[str, Path] = {"det": det_p, "rec": rec_p}
        if cls_p:
            found["cls"] = cls_p
        return found

    # Models pulled via redirected HOME land under models/paddle/_home/.paddleocr
    home = _paddle_home_root()
    det_h = _find_kind_dir(home, "det", ("det", "multilingual", "japan"))
    rec_h = _find_kind_dir(home, "rec", ("japan", "rec"))
    cls_h = _find_kind_dir(home, "cls", ("cls", "ch_ppocr"))
    if det_h and rec_h:
        found = {"det": det_h, "rec": rec_h}
        if cls_h:
            found["cls"] = cls_h
        return found
    return None

def _extract_tar_bytes(data: bytes, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
        members = [m for m in tar.getmembers() if m.name and not m.name.startswith("..")]
        tar.extractall(dest, members=members)

    children = [p for p in dest.iterdir()]
    if len(children) == 1 and children[0].is_dir() and not _dir_has_weights(dest):
        nested = children[0]
        if _dir_has_weights(nested):
            for item in nested.iterdir():
                target = dest / item.name
                if not target.exists():
                    item.rename(target)
            try:
                nested.rmdir()
            except OSError:
                pass


def _http_get(url: str) -> httpx.Response:
    """GET with SSL fallback for locked-down/corporate Windows cert stores."""
    try:
        with httpx.Client(timeout=180.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp
    except (httpx.ConnectError, httpx.HTTPStatusError):
        with httpx.Client(timeout=180.0, follow_redirects=True, verify=False) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp


def _copy_tree(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def _materialize_canonical_dirs(found: dict[str, Path]) -> dict[str, Path]:
    """Copy discovered dirs into models/paddle/{det,rec,cls} for stable paths."""
    mapping = {"det": paddle_det_dir(), "rec": paddle_rec_dir(), "cls": paddle_cls_dir()}
    out: dict[str, Path] = {}
    for kind, dest in mapping.items():
        src = found.get(kind)
        if src is None:
            continue
        if src.resolve() != dest.resolve():
            _copy_tree(src, dest)
        out[kind] = dest
    return out


def _bootstrap_via_paddle(progress: ProgressCb | None = None) -> dict[str, Path]:
    """
    Ask PaddleOCR to fetch Japanese models, but force its home into the project tree
    by temporarily redirecting USERPROFILE/HOME.
    """
    fake_home = paddle_models_dir() / "_home"
    fake_home.mkdir(parents=True, exist_ok=True)
    keys = ("USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["USERPROFILE"] = str(fake_home)
    os.environ["HOME"] = str(fake_home)
    # Avoid HOMEPATH pointing outside our fake home on Windows.
    os.environ.pop("HOMEPATH", None)
    os.environ.pop("HOMEDRIVE", None)
    try:
        if progress:
            progress(f"Bootstrapping Japanese models into {fake_home} via PaddleOCR ...")
        from paddleocr import PaddleOCR

        # Triggers download of japan det/rec/cls into fake_home/.paddleocr
        PaddleOCR(use_angle_cls=True, lang="japan", show_log=False)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    found = japan_model_dirs()
    if found is None:
        raise RuntimeError(
            f"PaddleOCR bootstrap finished but models were not found under {fake_home}"
        )
    return _materialize_canonical_dirs(found)


def download_japanese_models(
    force: bool = False,
    progress: ProgressCb | None = None,
) -> dict[str, Path]:
    """
    Download Japanese-only mobile OCR models into <project>/models/paddle/.

    Never writes to the real ~/.paddleocr. Tries direct CDN first, then Paddle bootstrap.
    """
    if not force:
        existing = japan_model_dirs()
        if existing is not None:
            # Ensure canonical layout when possible.
            if all(p.parent == paddle_models_dir() for p in existing.values()):
                if progress:
                    progress(f"Models already present under {paddle_models_dir()}")
                return existing
            return _materialize_canonical_dirs(existing)

    targets = {
        "det": paddle_det_dir(),
        "rec": paddle_rec_dir(),
        "cls": paddle_cls_dir(),
    }
    direct_ok = True
    try:
        for kind, url in _JAPAN_MODEL_URLS.items():
            dest = targets[kind]
            if not force and _dir_has_weights(dest):
                if progress:
                    progress(f"Skip {kind}: already present at {dest}")
                continue
            if progress:
                progress(f"Downloading {kind} -> {dest} ...")
            dest.mkdir(parents=True, exist_ok=True)
            resp = _http_get(url)
            _extract_tar_bytes(resp.content, dest)
            if not _dir_has_weights(dest):
                raise RuntimeError(f"No weights under {dest} after extract")
            if progress:
                progress(f"Ready: {kind}")
    except Exception as ex:
        direct_ok = False
        if progress:
            progress(f"Direct download failed ({type(ex).__name__}: {ex}); trying Paddle bootstrap")

    found = japan_model_dirs()
    if found is not None and direct_ok:
        return found if all(p.parent == paddle_models_dir() for p in found.values()) else _materialize_canonical_dirs(found)

    return _bootstrap_via_paddle(progress=progress)


class PaddleOcrAdapter(OcrAdapter):
    """Japanese-only PaddleOCR; models live under <project>/models/paddle/."""

    id = OcrEngineId.PADDLE
    display_name = "PaddleOCR (Japanese)"

    def __init__(self, auto_download: bool = False) -> None:
        self._engine = None
        self._auto_download = auto_download

    def is_available(self) -> bool:
        return paddle_package_installed()

    def is_ready(self, language: str = "ja") -> bool:
        _ = language
        if not self.is_available():
            return False
        return japan_model_dirs() is not None

    def readiness_message(self, language: str = "ja") -> str:
        _ = language
        root = paddle_models_dir()
        if not self.is_available():
            return (
                "PaddleOCR is not installed. Run: pip install paddlepaddle==2.6.2 paddleocr==2.7.3 "
                f"(models will be stored under {root})."
            )
        if self.is_ready():
            return f"Ready (Japanese models under {root})."
        return (
            f"Japanese models missing under {root}. "
            "Open Settings → Download Japanese models "
            "(or enable auto-download on first use)."
        )

    def ensure_ready(self, progress: ProgressCb | None = None) -> None:
        if not self.is_available():
            raise RuntimeError(self.readiness_message())
        if self.is_ready():
            return
        download_japanese_models(progress=progress)

    def recognize(
        self,
        image: Image.Image,
        language: str = "ja",
        *,
        debug: bool = False,
        profile: str = "balanced",
    ) -> list[TextBlock]:
        from pylens.ocr.debug import OcrDebugSession, configure_ocr_logging, image_fingerprint

        _ = language
        if debug:
            configure_ocr_logging()
        session = OcrDebugSession(enabled=debug, engine="paddle")

        if not self.is_available():
            raise RuntimeError(self.readiness_message())
        if not self.is_ready():
            if self._auto_download:
                self.ensure_ready()
            else:
                raise RuntimeError(self.readiness_message())

        model_dirs = japan_model_dirs()
        assert model_dirs is not None

        import numpy as np

        engine_was_cached = self._engine is not None
        engine = self._get_engine(model_dirs)
        rgb = image.convert("RGB")
        scale = choose_scale(rgb.width, rgb.height, profile)
        # Upscale then sharpen — better glyph edges for small UI fonts.
        prepared = prepare_for_ocr(rgb, scale)
        arr = np.asarray(prepared)

        session.write(f"fingerprint={image_fingerprint(rgb)}")
        session.write(
            f"input={rgb.size} scale={scale:.3f} prepared={prepared.size} "
            f"pipeline=upscale_then_enhance"
        )
        session.write(f"model_dirs={ {k: str(v) for k, v in model_dirs.items()} }")
        session.write(f"use_cls={'cls' in model_dirs} engine_reused={engine_was_cached}")
        session.save_image("01_capture.png", rgb)
        session.save_image("02_prepared.png", prepared)
        session.save_image("03_scaled.png", prepared)

        raw = engine.ocr(arr, cls="cls" in model_dirs)
        blocks: list[TextBlock] = []
        raw_rows: list[dict] = []
        if not raw:
            session.write("raw_ocr=empty")
            session.save_json("04_raw_ocr.json", [])
            session.log_blocks("05_post", blocks)
            return blocks

        min_conf = 0.45 if profile == "fast" else 0.35
        pages = raw if isinstance(raw, list) else [raw]
        for page in pages:
            if not page:
                continue
            for item in page:
                if not item or len(item) < 2:
                    continue
                box, meta = item[0], item[1]
                conf = None
                if isinstance(meta, (list, tuple)):
                    text = meta[0]
                    if len(meta) > 1:
                        try:
                            conf = float(meta[1])
                        except (TypeError, ValueError):
                            conf = None
                else:
                    text = str(meta)
                text = (text or "").strip()
                if not text:
                    continue
                if conf is not None and conf < min_conf:
                    session.write(f"drop low-conf text={text!r} conf={conf:.3f}")
                    continue
                xs = [float(p[0]) for p in box]
                ys = [float(p[1]) for p in box]
                x = min(xs) / scale
                y = min(ys) / scale
                w = (max(xs) - min(xs)) / scale
                h = (max(ys) - min(ys)) / scale
                rect = (int(x), int(y), max(1, int(w)), max(1, int(h)))
                raw_rows.append(
                    {
                        "text": text,
                        "confidence": conf,
                        "box_scaled": [[float(p[0]), float(p[1])] for p in box],
                        "rect_capture": list(rect),
                    }
                )
                session.write(
                    f"raw text={text!r} conf={conf if conf is not None else 'n/a'} rect={rect}"
                )
                blocks.append(TextBlock(original=text, rect=rect))

        session.save_json("04_raw_ocr.json", raw_rows)
        session.write(f"raw_block_count={len(blocks)}")
        if raw_rows:
            confs = [r["confidence"] for r in raw_rows if r["confidence"] is not None]
            if confs:
                session.write(
                    f"confidence min={min(confs):.3f} max={max(confs):.3f} "
                    f"avg={sum(confs) / len(confs):.3f}"
                )

        post = postprocess_ocr_blocks(blocks)
        session.log_blocks("05_post", post)
        for b in post:
            session.write(f"post text={b.original!r} rect={b.rect}")
        if session.dir is not None:
            session.write(f"DONE compare folder: {session.dir}")
        return post

    def _get_engine(self, model_dirs: dict[str, Path]):
        if self._engine is not None:
            return self._engine

        from paddleocr import PaddleOCR

        kwargs: dict = {
            "use_angle_cls": "cls" in model_dirs,
            "lang": "japan",
            "show_log": False,
            "det_model_dir": str(model_dirs["det"]),
            "rec_model_dir": str(model_dirs["rec"]),
            # Slightly more sensitive detection for small UI labels.
            "det_db_thresh": 0.3,
            "det_db_box_thresh": 0.5,
            "det_db_unclip_ratio": 1.8,
            "rec_batch_num": 8,
        }
        if "cls" in model_dirs:
            kwargs["cls_model_dir"] = str(model_dirs["cls"])

        self._engine = PaddleOCR(**kwargs)
        return self._engine
