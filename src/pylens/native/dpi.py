from __future__ import annotations

import ctypes
from ctypes import wintypes

# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
_DPI_CONTEXT_V2 = ctypes.c_void_p(-4)

__all__ = ["RECT", "dip_to_physical", "get_system_dpi", "physical_to_dip", "set_dpi_awareness"]


def set_dpi_awareness() -> None:
    """Best-effort Per-Monitor DPI Aware v2 before any GUI/capture."""
    user32 = ctypes.windll.user32
    try:
        # Windows 10 1703+
        if hasattr(user32, "SetProcessDpiAwarenessContext"):
            user32.SetProcessDpiAwarenessContext(_DPI_CONTEXT_V2)
            return
    except Exception:
        pass
    try:
        shcore = ctypes.windll.shcore
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def get_system_dpi() -> int:
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
        return int(dpi) if dpi else 96
    except Exception:
        return 96


def physical_to_dip(value: float, dpi: int | None = None) -> float:
    d = dpi or get_system_dpi()
    return value * 96.0 / d


def dip_to_physical(value: float, dpi: int | None = None) -> float:
    d = dpi or get_system_dpi()
    return value * d / 96.0


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]
