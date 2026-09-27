from __future__ import annotations

import ctypes
from ctypes import wintypes

# Re-export for backward compatibility
from pylens.dpi import create_dpi_backend

# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
_DPI_CONTEXT_V2 = ctypes.c_void_p(-4)

__all__ = ["RECT", "dip_to_physical", "get_system_dpi", "physical_to_dip", "set_dpi_awareness"]


def set_dpi_awareness() -> None:
    """Best-effort Per-Monitor DPI Aware v2 before any GUI/capture."""
    backend = create_dpi_backend()
    backend.set_dpi_awareness()


def get_system_dpi() -> int:
    backend = create_dpi_backend()
    return backend.get_system_dpi()


def physical_to_dip(value: float, dpi: int | None = None) -> float:
    backend = create_dpi_backend()
    if dpi is None:
        dpi = backend.get_system_dpi()
    return value * 96.0 / dpi


def dip_to_physical(value: float, dpi: int | None = None) -> float:
    backend = create_dpi_backend()
    if dpi is None:
        dpi = backend.get_system_dpi()
    return value * dpi / 96.0


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]