from __future__ import annotations

from pathlib import Path

from pylens.settings import config_dir


def project_root() -> Path:
    """Repository / install root for PyLens (parent of src/)."""
    return Path(__file__).resolve().parents[2]


def _models_base_dir() -> Path:
    """Base directory for models - prefers project dir, falls back to config dir."""
    project_models = project_root() / "models"
    if project_models.exists():
        return project_models
    # Fallback to config dir
    return config_dir() / "models"


def paddle_models_dir() -> Path:
    """All PaddleOCR downloads live under the project or config dir."""
    path = _models_base_dir() / "paddle"
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
    path = _models_base_dir() / "argos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_glossary_path() -> Path:
    # Check project first, then config dir
    project_glossary = project_root() / "data" / "glossary" / "ja_en.default.json"
    if project_glossary.exists():
        return project_glossary
    return config_dir() / "glossary" / "ja_en.default.json"