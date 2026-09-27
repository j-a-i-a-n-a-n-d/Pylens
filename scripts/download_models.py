#!/usr/bin/env python3
"""
Cross-platform model downloader for PyLens.
Downloads PaddleOCR models (Japanese) and Argos Translate models.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Callable

import httpx

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pylens.paths import (
    argos_models_dir,
    paddle_cls_dir,
    paddle_det_dir,
    paddle_models_dir,
    paddle_rec_dir,
    project_root,
)


# Model URLs
JAPAN_MODEL_URLS = {
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

ARGOS_MODEL_URLS = {
    "ja_en": "https://argos-net.com/v1/translate-ja_en-1_1.argosmodel",
    "en_ja": "https://argos-net.com/v1/translate-en_ja-1_1.argosmodel",
}

ARGOS_MODEL_NAMES = {
    "ja_en": "translate-ja_en-1_1.argosmodel",
    "en_ja": "translate-en_ja-1_1.argosmodel",
}


ProgressCb = Callable[[str], None]


def _http_get(url: str, progress: ProgressCb | None = None) -> httpx.Response:
    """Download with progress reporting."""
    try:
        with httpx.Client(timeout=300.0, follow_redirects=True) as client:
            if progress:
                progress(f"Downloading {url}...")
            resp = client.get(url)
            resp.raise_for_status()
            return resp
    except (httpx.ConnectError, httpx.HTTPStatusError) as e:
        # Try without SSL verification for corporate environments
        try:
            with httpx.Client(timeout=300.0, follow_redirects=True, verify=False) as client:
                if progress:
                    progress(f"Retrying without SSL verification: {url}")
                resp = client.get(url)
                resp.raise_for_status()
                return resp
        except Exception as e2:
            raise RuntimeError(f"Failed to download {url}: {e2}")


def _extract_tar_bytes(data: bytes, dest: Path, progress: ProgressCb | None = None) -> None:
    """Extract tar archive."""
    dest.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(f"Extracting to {dest}...")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
        members = [m for m in tar.getmembers() if m.name and not m.name.startswith("..")]
        tar.extractall(dest, members=members)

    # Flatten single nested directory if weights are there
    children = [p for p in dest.iterdir()]
    if len(children) == 1 and children[0].is_dir():
        nested = children[0]
        if any(nested.glob("*.pdiparams")) or any(nested.glob("inference.pdmodel")):
            if progress:
                progress(f"Flattening nested directory {nested.name}")
            for item in nested.iterdir():
                target = dest / item.name
                if not target.exists():
                    item.rename(target)
            try:
                nested.rmdir()
            except OSError:
                pass


def _dir_has_weights(path: Path) -> bool:
    """Check if directory contains model weights."""
    if not path.exists():
        return False
    patterns = ("*.pdiparams", "inference.pdmodel", "inference.yml", "*.onnx")
    return any(any(path.rglob(pattern)) for pattern in patterns)


def download_paddle_models(
    force: bool = False,
    progress: ProgressCb | None = None,
) -> dict[str, Path]:
    """Download Japanese PaddleOCR models."""
    print("=== Downloading PaddleOCR Japanese Models ===")

    targets = {
        "det": paddle_det_dir(),
        "rec": paddle_rec_dir(),
        "cls": paddle_cls_dir(),
    }

    # Check existing
    if not force:
        existing = {}
        for kind, path in targets.items():
            if _dir_has_weights(path):
                existing[kind] = path
        if len(existing) == 3:
            if progress:
                progress(f"All models already present under {paddle_models_dir()}")
            return existing

    # Download each model
    for kind, url in JAPAN_MODEL_URLS.items():
        dest = targets[kind]
        if not force and _dir_has_weights(dest):
            if progress:
                progress(f"Skip {kind}: already present at {dest}")
            continue

        if progress:
            progress(f"Downloading {kind} model...")

        dest.mkdir(parents=True, exist_ok=True)
        resp = _http_get(url, progress)
        _extract_tar_bytes(resp.content, dest, progress)

        if not _dir_has_weights(dest):
            raise RuntimeError(f"No weights found under {dest} after extraction")

        if progress:
            progress(f"Ready: {kind} at {dest}")

    # Verify all models downloaded
    result = {}
    for kind, path in targets.items():
        if _dir_has_weights(path):
            result[kind] = path
        else:
            raise RuntimeError(f"Model {kind} not found at {path}")

    print(f"✓ PaddleOCR models downloaded to {paddle_models_dir()}")
    return result


def bootstrap_paddle_via_library(
    progress: ProgressCb | None = None,
) -> dict[str, Path]:
    """Fallback: use PaddleOCR library to download models into project directory."""
    print("=== Bootstrapping via PaddleOCR library ===")

    fake_home = paddle_models_dir() / "_home"
    fake_home.mkdir(parents=True, exist_ok=True)

    # Save original env vars
    keys = ("USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH")
    saved = {k: os.environ.get(k) for k in keys}

    # Redirect to project-local home
    os.environ["USERPROFILE"] = str(fake_home)
    os.environ["HOME"] = str(fake_home)
    os.environ.pop("HOMEPATH", None)
    os.environ.pop("HOMEDRIVE", None)

    try:
        if progress:
            progress(f"Bootstrapping models into {fake_home} via PaddleOCR...")

        from paddleocr import PaddleOCR

        # This triggers download of Japanese models
        PaddleOCR(use_angle_cls=True, lang="japan", show_log=False)

    finally:
        # Restore env
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # Find and copy models to canonical locations
    found = find_paddle_models()
    if found is None:
        raise RuntimeError("PaddleOCR bootstrap completed but models not found")

    return copy_to_canonical_dirs(found, progress)


def find_paddle_models() -> dict[str, Path] | None:
    """Find PaddleOCR model directories."""
    det_p = find_model_dir(paddle_det_dir(), ("det", "multilingual", "japan"))
    rec_p = find_model_dir(paddle_rec_dir(), ("japan", "rec"))
    cls_p = find_model_dir(paddle_cls_dir(), ("cls", "ch_ppocr"))

    if det_p and rec_p:
        found: dict[str, Path] = {"det": det_p, "rec": rec_p}
        if cls_p:
            found["cls"] = cls_p
        return found

    # Check redirected home
    home = paddle_models_dir() / "_home" / ".paddleocr"
    det_h = find_model_dir(home, ("det", "multilingual", "japan"))
    rec_h = find_model_dir(home, ("japan", "rec"))
    cls_h = find_model_dir(home, ("cls", "ch_ppocr"))

    if det_h and rec_h:
        found = {"det": det_h, "rec": rec_h}
        if cls_h:
            found["cls"] = cls_h
        return found

    return None


def find_model_dir(root: Path, tokens: tuple[str, ...]) -> Path | None:
    """Find model directory containing weights."""
    if not root.exists():
        return None

    candidates = []
    for path in root.rglob("*"):
        if not path.is_dir():
            continue
        blob = f"{path.parent.name}/{path.name}".lower()
        if any(token.lower() in blob for token in tokens) and _dir_has_weights(path):
            candidates.append(path)

    if not candidates:
        return None

    return max(candidates, key=lambda p: len(str(p)))


def copy_to_canonical_dirs(
    found: dict[str, Path],
    progress: ProgressCb | None = None,
) -> dict[str, Path]:
    """Copy discovered model dirs to canonical locations."""
    mapping = {
        "det": paddle_det_dir(),
        "rec": paddle_rec_dir(),
        "cls": paddle_cls_dir(),
    }
    out = {}
    for kind, dest in mapping.items():
        src = found.get(kind)
        if src is None:
            continue
        if src.resolve() != dest.resolve():
            if progress:
                progress(f"Copying {kind} to {dest}")
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        out[kind] = dest
    return out


def download_argos_models(
    force: bool = False,
    progress: ProgressCb | None = None,
) -> dict[str, Path]:
    """Download Argos Translate model archives."""
    print("=== Downloading Argos Translate Models ===")

    models_dir = argos_models_dir()
    models_dir.mkdir(parents=True, exist_ok=True)

    result = {}
    for pair, url in ARGOS_MODEL_URLS.items():
        filename = ARGOS_MODEL_NAMES[pair]
        dest = models_dir / filename

        if not force and dest.exists():
            if progress:
                progress(f"Skip {pair}: already exists at {dest}")
            result[pair] = dest
            continue

        if progress:
            progress(f"Downloading {pair} model...")

        resp = _http_get(url, progress)
        dest.write_bytes(resp.content)

        if progress:
            progress(f"Ready: {pair} at {dest}")

        result[pair] = dest

    print(f"✓ Argos models downloaded to {models_dir}")
    return result


def install_argos_packages(
    progress: ProgressCb | None = None,
) -> None:
    """Install downloaded Argos model archives."""
    print("=== Installing Argos Models ===")

    try:
        from argostranslate import package, translate
    except ImportError:
        raise RuntimeError("argostranslate not installed. Run: pip install argostranslate")

    models_dir = argos_models_dir()
    installed_dir = models_dir / "installed"
    installed_dir.mkdir(parents=True, exist_ok=True)

    # Configure Argos environment
    os.environ["ARGOS_PACKAGES_DIR"] = str(installed_dir)
    os.environ["ARGOS_DEVICE_TYPE"] = "cpu"

    for pair, filename in ARGOS_MODEL_NAMES.items():
        archive = models_dir / filename
        if not archive.exists():
            print(f"Skipping {pair}: archive not found at {archive}")
            continue

        source_lang, target_lang = pair.split("_")
        print(f"Installing {source_lang}->{target_lang} from {archive}...")

        try:
            package.install_from_path(archive)
            print(f"✓ Installed {pair}")
        except Exception as e:
            print(f"✗ Failed to install {pair}: {e}")

    # Verify installation
    languages = translate.get_installed_languages()
    for pair in ARGOS_MODEL_NAMES:
        source_lang, target_lang = pair.split("_")
        source = next((l for l in languages if l.code == source_lang), None)
        target = next((l for l in languages if l.code == target_lang), None)
        if source and target:
            trans = source.get_translation(target)
            if trans and type(trans).__name__ != "IdentityTranslation":
                print(f"✓ Verified: {pair}")
            else:
                print(f"✗ Not working: {pair}")


def check_dependencies() -> dict[str, bool]:
    """Check which optional dependencies are available."""
    deps = {
        "paddlepaddle": importlib.util.find_spec("paddlepaddle") is not None,
        "paddleocr": importlib.util.find_spec("paddleocr") is not None,
        "argostranslate": importlib.util.find_spec("argostranslate") is not None,
    }
    return deps


def main():
    parser = argparse.ArgumentParser(description="Download PyLens models")
    parser.add_argument(
        "--paddle",
        action="store_true",
        help="Download PaddleOCR Japanese models",
    )
    parser.add_argument(
        "--argos",
        action="store_true",
        help="Download Argos Translate models",
    )
    parser.add_argument(
        "--install-argos",
        action="store_true",
        help="Install Argos model archives (requires argostranslate)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Download all models",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if models exist",
    )
    parser.add_argument(
        "--bootstrap-paddle",
        action="store_true",
        help="Use PaddleOCR library to bootstrap models (fallback)",
    )

    args = parser.parse_args()

    if not any([args.paddle, args.argos, args.install_argos, args.all, args.bootstrap_paddle]):
        parser.print_help()
        return

    def progress(msg: str):
        print(f"  {msg}")

    deps = check_dependencies()
    print(f"Dependencies: {deps}")

    if args.all or args.paddle:
        if not deps["paddleocr"] and not args.bootstrap_paddle:
            print("Note: paddleocr not installed. Using direct download.")
        try:
            download_paddle_models(force=args.force, progress=progress)
        except Exception as e:
            print(f"Direct download failed: {e}")
            if args.bootstrap_paddle or not deps["paddleocr"]:
                print("Trying bootstrap via PaddleOCR library...")
                try:
                    bootstrap_paddle_via_library(progress=progress)
                except Exception as e2:
                    print(f"Bootstrap also failed: {e2}")
                    sys.exit(1)
            else:
                sys.exit(1)

    if args.all or args.argos:
        download_argos_models(force=args.force, progress=progress)

    if args.all or args.install_argos:
        if deps["argostranslate"]:
            install_argos_packages(progress=progress)
        else:
            print("argostranslate not installed, skipping installation.")
            print("Install with: pip install argostranslate")

    print("\n=== Done ===")
    print(f"Paddle models: {paddle_models_dir()}")
    print(f"Argos models:  {argos_models_dir()}")


if __name__ == "__main__":
    main()