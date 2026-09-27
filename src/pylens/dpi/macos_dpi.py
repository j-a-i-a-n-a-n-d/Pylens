from __future__ import annotations

from pylens.dpi import DpiBackend, DpiInfo


class MacOSDpiBackend(DpiBackend):
    """macOS DPI handling using AppKit."""

    def __init__(self):
        self._appkit = None
        self._init_appkit()

    def _init_appkit(self):
        try:
            import AppKit
            self._appkit = AppKit
        except ImportError:
            pass

    def set_dpi_awareness(self) -> None:
        """macOS handles DPI automatically; no special action needed."""
        # On macOS, Qt handles high-DPI automatically when using
        # QApplication.setHighDpiScaleFactorRoundingPolicy
        pass

    def get_system_dpi(self) -> int:
        """macOS uses 72 DPI as base (points), but retina screens have 2x scale."""
        return 72

    def get_screen_dpi(self, screen_index: int = 0) -> DpiInfo:
        if not self._appkit:
            return DpiInfo(72, 72, 1.0)

        screens = self._appkit.NSScreen.screens()
        if screen_index >= len(screens):
            screen_index = 0

        screen = screens[screen_index]
        scale = screen.backingScaleFactor()
        # On macOS, logical DPI is 72, physical is 72 * scale
        logical_dpi = 72
        physical_dpi = int(72 * scale)
        return DpiInfo(logical_dpi, physical_dpi, scale)

    def physical_to_logical(self, value: float, screen_index: int = 0) -> float:
        dpi_info = self.get_screen_dpi(screen_index)
        return value / dpi_info.scale_factor

    def logical_to_physical(self, value: float, screen_index: int = 0) -> float:
        dpi_info = self.get_screen_dpi(screen_index)
        return value * dpi_info.scale_factor