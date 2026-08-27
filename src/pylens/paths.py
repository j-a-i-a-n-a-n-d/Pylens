from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Repository / install root for PyLens (parent of src/)."""
    # .../py-lens/src/pylens/paths.py → parents[2] == py-lens
    return Path(__file__).resolve().parents[2]


def paddle_models_dir() -> Path:
    """All PaddleOCR downloads live under the project (not ~/.paddleocr)."""
    path = project_root() / "models" / "paddle"
    path.mkdir(parents=True, exist_ok=True)
    return path


def paddle_det_dir() -> Path:
    return paddle_models_dir() / "det"


def paddle_rec_dir() -> Path:
    return paddle_models_dir() / "rec"


def paddle_cls_dir() -> Path:
    return paddle_models_dir() / "cls"


def argos_models_dir() -> Path:
    """Manually supplied Argos archives and installed packages."""

    path = project_root() / "models" / "argos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_glossary_path() -> Path:
    return project_root() / "data" / "glossary" / "ja_en.default.json"
