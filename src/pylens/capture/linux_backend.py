from __future__ import annotations

import mss
from PIL import Image

from pylens.capture import CaptureBackend, ScreenBounds, WindowInfo
from pylens.models import CaptureResult


class LinuxCaptureBackend(CaptureBackend):
    """Linux implementation using mss and X11/Wayland."""

    def __init__(self):
        self._xlib = None
        self._ewmh = None
        self._init_x11()

    def _init_x11(self):
        """Initialize X11 bindings if available."""
        try:
            import Xlib.display
            import Xlib.X
            self._xlib = Xlib
        except ImportError:
            pass
        try:
            import ewmh
            self._ewmh = ewmh
        except ImportError:
            pass

    def capture_region(self, x: int, y: int, width: int, height: int) -> CaptureResult:
        if width < 1 or height < 1:
            raise ValueError("Capture region too small")
        with mss.mss() as sct:
            monitor = {"left": int(x), "top": int(y), "width": int(width), "height": int(height)}
            shot = sct.grab(monitor)
            image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        return CaptureResult(image=image, origin_x=int(x), origin_y=int(y))

    def capture_window(self, window_id: int | None = None) -> CaptureResult | None:
        if window_id is None:
            window_id = self._get_active_window_id()

        if window_id is None:
            return None

        bounds = self._get_window_bounds(window_id)
        if bounds is None:
            return None

        x, y, w, h = bounds
        return self.capture_region(x, y, w, h)

    def get_virtual_screen_bounds(self) -> ScreenBounds:
        with mss.mss() as sct:
            # mss monitor 0 is the full virtual screen
            monitor = sct.monitors[0]
            return ScreenBounds(
                monitor["left"], monitor["top"],
                monitor["width"], monitor["height"]
            )

    def list_windows(self) -> list[WindowInfo]:
        if not self._ewmh:
            return []

        try:
            windows = []
            client_list = self._ewmh.getClientList()
            for win in client_list:
                geom = win.get_geometry()
                name = win.get_wm_name() or ""
                if geom.width < 50 or geom.height < 50:
                    continue
                windows.append(WindowInfo(
                    id=win.id,
                    title=name,
                    x=geom.x, y=geom.y,
                    width=geom.width, height=geom.height,
                    is_visible=True,  # EWMH doesn't easily tell us this
                    is_minimized=False,
                ))
            return windows
        except Exception:
            return []

    def _get_active_window_id(self) -> int | None:
        if not self._ewmh:
            return None
        try:
            active = self._ewmh.getActiveWindow()
            return active.id if active else None
        except Exception:
            return None

    def _get_window_bounds(self, window_id: int) -> tuple[int, int, int, int] | None:
        if not self._xlib:
            return None
        try:
            display = self._xlib.display.Display()
            win = display.create_resource_object('window', window_id)
            geom = win.get_geometry()
            return geom.x, geom.y, geom.width, geom.height
        except Exception:
            return None