from __future__ import annotations

import mss
from PIL import Image

from pylens.capture import CaptureBackend, ScreenBounds, WindowInfo
from pylens.models import CaptureResult


class MacOSCaptureBackend(CaptureBackend):
    """macOS implementation using mss and Quartz/CoreGraphics."""

    def __init__(self):
        self._quartz = None
        self._cg = None
        self._init_quartz()

    def _init_quartz(self):
        """Initialize Quartz/CoreGraphics bindings."""
        try:
            import Quartz
            self._quartz = Quartz
        except ImportError:
            pass
        try:
            import CoreGraphics as CG
            self._cg = CG
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
        if not self._quartz:
            raise RuntimeError("Quartz framework not available. Install pyobjc-framework-Quartz")

        if window_id is None:
            window_id = self._get_frontmost_window_id()

        if window_id is None:
            return None

        # Get window bounds
        bounds = self._get_window_bounds(window_id)
        if bounds is None:
            return None

        x, y, w, h = bounds
        return self.capture_region(x, y, w, h)

    def get_virtual_screen_bounds(self) -> ScreenBounds:
        if not self._quartz:
            # Fallback to primary screen
            import AppKit
            screen = AppKit.NSScreen.mainScreen()
            frame = screen.frame()
            return ScreenBounds(0, 0, int(frame.size.width), int(frame.size.height))

        # Get union of all screens
        screens = self._quartz.CGGetActiveDisplayList(0, None, None)[1]
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')

        for display_id in screens:
            bounds = self._quartz.CGDisplayBounds(display_id)
            min_x = min(min_x, bounds.origin.x)
            min_y = min(min_y, bounds.origin.y)
            max_x = max(max_x, bounds.origin.x + bounds.size.width)
            max_y = max(max_y, bounds.origin.y + bounds.size.height)

        return ScreenBounds(
            int(min_x), int(min_y),
            int(max_x - min_x), int(max_y - min_y)
        )

    def list_windows(self) -> list[WindowInfo]:
        if not self._quartz:
            return []

        windows = []
        window_list = self._quartz.CGWindowListCopyWindowInfo(
            self._quartz.kCGWindowListOptionOnScreenOnly |
            self._quartz.kCGWindowListExcludeDesktopElements,
            self._quartz.kCGNullWindowID
        )

        for win in window_list:
            layer = win.get(self._quartz.kCGWindowLayer, 0)
            if layer != 0:
                continue  # Skip non-standard windows

            bounds_dict = win.get(self._quartz.kCGWindowBounds, {})
            x = int(bounds_dict.get('X', 0))
            y = int(bounds_dict.get('Y', 0))
            w = int(bounds_dict.get('Width', 0))
            h = int(bounds_dict.get('Height', 0))

            if w < 50 or h < 50:
                continue

            windows.append(WindowInfo(
                id=int(win.get(self._quartz.kCGWindowNumber, 0)),
                title=win.get(self._quartz.kCGWindowName, "") or "",
                x=x, y=y, width=w, height=h,
                is_visible=True,
                is_minimized=False,
                process_name=win.get(self._quartz.kCGWindowOwnerName, "")
            ))

        return windows

    def _get_frontmost_window_id(self) -> int | None:
        """Get the frontmost application window ID."""
        if not self._quartz:
            return None

        # Get frontmost app
        workspace = self._quartz.NSWorkspace.sharedWorkspace()
        frontmost_app = workspace.frontmostApplication()
        if not frontmost_app:
            return None

        pid = frontmost_app.processIdentifier()

        # Get windows for this PID
        window_list = self._quartz.CGWindowListCopyWindowInfo(
            self._quartz.kCGWindowListOptionOnScreenOnly,
            self._quartz.kCGNullWindowID
        )

        for win in window_list:
            owner_pid = win.get(self._quartz.kCGWindowOwnerPID, 0)
            if owner_pid == pid:
                layer = win.get(self._quartz.kCGWindowLayer, 0)
                if layer == 0:
                    return int(win.get(self._quartz.kCGWindowNumber, 0))

        return None

    def _get_window_bounds(self, window_id: int) -> tuple[int, int, int, int] | None:
        if not self._quartz:
            return None

        window_list = self._quartz.CGWindowListCopyWindowInfo(
            self._quartz.kCGWindowListOptionOnScreenOnly,
            self._quartz.kCGNullWindowID
        )

        for win in window_list:
            if int(win.get(self._quartz.kCGWindowNumber, 0)) == window_id:
                bounds_dict = win.get(self._quartz.kCGWindowBounds, {})
                x = int(bounds_dict.get('X', 0))
                y = int(bounds_dict.get('Y', 0))
                w = int(bounds_dict.get('Width', 0))
                h = int(bounds_dict.get('Height', 0))
                return x, y, w, h

        return None