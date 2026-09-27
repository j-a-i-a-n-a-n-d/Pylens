from __future__ import annotations

import platform
import sys
from enum import Enum
from functools import lru_cache


class Platform(Enum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    UNKNOWN = "unknown"


@lru_cache(maxsize=1)
def current_platform() -> Platform:
    """Detect the current platform."""
    system = platform.system().lower()
    if system == "windows":
        return Platform.WINDOWS
    elif system == "darwin":
        return Platform.MACOS
    elif system == "linux":
        return Platform.LINUX
    return Platform.UNKNOWN


@lru_cache(maxsize=1)
def is_windows() -> bool:
    return current_platform() == Platform.WINDOWS


@lru_cache(maxsize=1)
def is_macos() -> bool:
    return current_platform() == Platform.MACOS


@lru_cache(maxsize=1)
def is_linux() -> bool:
    return current_platform() == Platform.LINUX


@lru_cache(maxsize=1)
def is_unix() -> bool:
    return current_platform() in (Platform.MACOS, Platform.LINUX)


def platform_name() -> str:
    """Human-readable platform name."""
    p = current_platform()
    if p == Platform.WINDOWS:
        return "Windows"
    elif p == Platform.MACOS:
        return "macOS"
    elif p == Platform.LINUX:
        return "Linux"
    return "Unknown"


def python_version() -> tuple[int, int]:
    """Return Python major, minor version."""
    return sys.version_info[:2]


def requires_python(min_version: tuple[int, int] = (3, 11)) -> bool:
    """Check if Python version meets minimum requirement."""
    return python_version() >= min_version