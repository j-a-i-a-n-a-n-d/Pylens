from __future__ import annotations

from pylens.dpi import DpiBackend, DpiInfo


class LinuxDpiBackend(DpiBackend):
    """Linux DPI handling using X11/Wayland."""

    def __init__(self):
        self._scale_factor = 1.0
        self._detect_scale_factor()

    def _detect_scale_factor(self):
        """Detect scale factor from environment or X11."""
        import os
        # Check common environment variables
        for var in ["GDK_SCALE", "QT_SCALE_FACTOR", "QT_AUTO_SCREEN_SCALE_FACTOR"]:
            if var in os.environ:
                try:
                    self._scale_factor = float(os.environ[var])
                    return
                except ValueError:
                    pass

        # Try X11
        try:
            import Xlib.display
            display = Xlib.display.Display()
            screen = display.screen()
            # Xft.dpi gives the DPI
            dpi = screen.get_resource("Xft.dpi", "Xft.dpi")
            if dpi:
                self._scale_factor = float(dpi) / 96.0
        except Exception:
            pass

    def set_dpi_awareness(self) -> None:
        """Linux/Wayland handles DPI automatically."""
        pass

    def get_system_dpi(self) -> int:
        return int(96 * self._scale_factor)

    def get_screen_dpi(self, screen_index: int = 0) -> DpiInfo:
        logical_dpi = 96
        physical_dpi = int(logical_dpi * self._scale_factor)
        return DpiInfo(logical_dpi, physical_dpi, self._scale_factor)

    def physical_to_logical(self, value: float, screen_index: int = 0) -> float:
        return value / self._scale_factor

    def logical_to_physical(self, value: float, screen_index: int = 0) -> float:
        return value * self._scale_factor