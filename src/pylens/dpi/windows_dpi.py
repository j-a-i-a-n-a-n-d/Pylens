from __future__ import annotations

import ctypes
from ctypes import wintypes

from pylens.dpi import DpiBackend, DpiInfo


class WindowsDpiBackend(DpiBackend):
    """Windows DPI handling using Win32 APIs."""

    # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
    _DPI_CONTEXT_V2 = ctypes.c_void_p(-4)

    def set_dpi_awareness(self) -> None:
        """Best-effort Per-Monitor DPI Aware v2 before any GUI/capture."""
        user32 = ctypes.windll.user32
        try:
            # Windows 10 1703+
            if hasattr(user32, "SetProcessDpiAwarenessContext"):
                user32.SetProcessDpiAwarenessContext(self._DPI_CONTEXT_V2)
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

    def get_system_dpi(self) -> int:
        try:
            dpi = ctypes.windll.user32.GetDpiForSystem()
            return int(dpi) if dpi else 96
        except Exception:
            return 96

    def get_screen_dpi(self, screen_index: int = 0) -> DpiInfo:
        try:
            user32 = ctypes.windll.user32
            # Get monitor handle for screen index
            monitor = user32.MonitorFromWindow(0, 2)  # MONITOR_DEFAULTTOPRIMARY
            if monitor:
                dpi_x = ctypes.c_uint()
                dpi_y = ctypes.c_uint()
                shcore = ctypes.windll.shcore
                shcore.GetDpiForMonitor(monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
                physical_dpi = int(dpi_x.value)
            else:
                physical_dpi = self.get_system_dpi()
        except Exception:
            physical_dpi = self.get_system_dpi()

        logical_dpi = 96
        scale_factor = physical_dpi / logical_dpi
        return DpiInfo(logical_dpi, physical_dpi, scale_factor)

    def physical_to_logical(self, value: float, screen_index: int = 0) -> float:
        dpi_info = self.get_screen_dpi(screen_index)
        return value * 96.0 / dpi_info.physical_dpi

    def logical_to_physical(self, value: float, screen_index: int = 0) -> float:
        dpi_info = self.get_screen_dpi(screen_index)
        return value * dpi_info.physical_dpi / 96.0