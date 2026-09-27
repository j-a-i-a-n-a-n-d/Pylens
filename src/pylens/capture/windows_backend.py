from __future__ import annotations

import ctypes
from collections.abc import Iterable

import mss
from PIL import Image

from pylens.capture import CaptureBackend, ScreenBounds, WindowInfo
from pylens.models import CaptureResult
from pylens.native.dpi import RECT

user32 = ctypes.windll.user32


class WindowsCaptureBackend(CaptureBackend):
    """Windows implementation using mss and Win32 APIs."""

    def capture_region(self, x: int, y: int, width: int, height: int) -> CaptureResult:
        if width < 1 or height < 1:
            raise ValueError("Capture region too small")
        with mss.mss() as sct:
            monitor = {"left": int(x), "top": int(y), "width": int(width), "height": int(height)}
            shot = sct.grab(monitor)
            image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        return CaptureResult(image=image, origin_x=int(x), origin_y=int(y))

    def capture_window(self, window_id: int | None = None) -> CaptureResult | None:
        exclude = set()
        if window_id:
            exclude.add(window_id)

        bounds = self._get_foreground_window_rect(exclude_hwnds=exclude)
        if bounds is None:
            return None
        left, top, width, height = bounds
        return self.capture_region(left, top, width, height)

    def get_virtual_screen_bounds(self) -> ScreenBounds:
        SM_XVIRTUALSCREEN = 76
        SM_YVIRTUALSCREEN = 77
        SM_CXVIRTUALSCREEN = 78
        SM_CYVIRTUALSCREEN = 79
        x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        return ScreenBounds(int(x), int(y), int(w), int(h))

    def list_windows(self) -> list[WindowInfo]:
        result: list[WindowInfo] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _enum(hwnd, _lparam):  # type: ignore[no-untyped-def]
            handle = int(hwnd)
            if self._is_usable_top_level(handle, set()):
                title = self._window_title(handle)
                rect = RECT()
                user32.GetWindowRect(handle, ctypes.byref(rect))
                result.append(WindowInfo(
                    id=handle,
                    title=title,
                    x=rect.left,
                    y=rect.top,
                    width=rect.right - rect.left,
                    height=rect.bottom - rect.top,
                    is_visible=user32.IsWindowVisible(handle),
                    is_minimized=user32.IsIconic(handle),
                ))
            return True

        user32.EnumWindows(_enum, 0)
        return result

    def _window_title(self, hwnd: int) -> str:
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value or ""

    def _is_usable_top_level(self, hwnd: int, exclude: set[int]) -> bool:
        if not hwnd or hwnd in exclude:
            return False
        if not user32.IsWindowVisible(hwnd):
            return False
        if user32.IsIconic(hwnd):
            return False
        style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
        if style & 0x80000000:  # WS_POPUP
            ex_style = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            if ex_style & 0x00000080:  # WS_EX_TOOLWINDOW
                return False
        title = self._window_title(hwnd).strip().lower()
        if title in {"pylenshost", "pylens"}:
            return False
        return True

    def _get_foreground_window_rect(
        self,
        exclude_hwnds: Iterable[int] | None = None,
    ) -> tuple[int, int, int, int] | None:
        exclude = {int(h) for h in (exclude_hwnds or []) if h}
        hwnd = int(user32.GetForegroundWindow() or 0)
        if not self._is_usable_top_level(hwnd, exclude):
            candidate = int(user32.GetWindow(hwnd, 2) or 0) if hwnd else 0  # GW_HWNDNEXT
            found = None
            hops = 0
            while candidate and hops < 40:
                if self._is_usable_top_level(candidate, exclude):
                    found = candidate
                    break
                candidate = int(user32.GetWindow(candidate, 2) or 0)
                hops += 1
            if found is None:
                found = self._first_visible_window(exclude)
            hwnd = found or 0
        if not hwnd:
            return None

        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        width = right - left
        height = bottom - top
        if width < 50 or height < 50:
            return None
        return left, top, width, height

    def _first_visible_window(self, exclude: set[int]) -> int | None:
        result: list[int] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _enum(hwnd, _lparam):  # type: ignore[no-untyped-def]
            handle = int(hwnd)
            if self._is_usable_top_level(handle, exclude):
                result.append(handle)
                return False
            return True

        user32.EnumWindows(_enum, 0)
        return result[0] if result else None