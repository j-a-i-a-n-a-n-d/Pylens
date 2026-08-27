from __future__ import annotations

import ctypes
from collections.abc import Iterable

import mss
from PIL import Image

from pylens.models import CaptureResult
from pylens.native.dpi import RECT

user32 = ctypes.windll.user32


def capture_region(x: int, y: int, width: int, height: int) -> CaptureResult:
    if width < 1 or height < 1:
        raise ValueError("Capture region too small")
    with mss.mss() as sct:
        monitor = {"left": int(x), "top": int(y), "width": int(width), "height": int(height)}
        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    return CaptureResult(image=image, origin_x=int(x), origin_y=int(y))


def _window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value or ""


def _is_usable_top_level(hwnd: int, exclude: set[int]) -> bool:
    if not hwnd or hwnd in exclude:
        return False
    if not user32.IsWindowVisible(hwnd):
        return False
    if user32.IsIconic(hwnd):
        return False
    # Skip tool windows / owned popups without a meaningful client area.
    style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
    if style & 0x80000000:  # WS_POPUP alone is often our HUD/tray helpers
        ex_style = user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
        if ex_style & 0x00000080:  # WS_EX_TOOLWINDOW
            return False
    title = _window_title(hwnd).strip().lower()
    if title in {"pylenshost", "pylens"}:
        return False
    return True


def get_foreground_window_rect(
    exclude_hwnds: Iterable[int] | None = None,
) -> tuple[int, int, int, int] | None:
    """Return the active (or next usable) top-level window bounds."""

    exclude = {int(h) for h in (exclude_hwnds or []) if h}
    hwnd = int(user32.GetForegroundWindow() or 0)
    if not _is_usable_top_level(hwnd, exclude):
        # Walk Z-order for the next visible top-level window (hotkey / HUD may steal focus).
        candidate = int(user32.GetWindow(hwnd, 2) or 0) if hwnd else 0  # GW_HWNDNEXT
        found = None
        hops = 0
        while candidate and hops < 40:
            if _is_usable_top_level(candidate, exclude):
                found = candidate
                break
            candidate = int(user32.GetWindow(candidate, 2) or 0)
            hops += 1
        if found is None:
            # Fallback: EnumWindows first usable
            found = _first_visible_window(exclude)
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


def _first_visible_window(exclude: set[int]) -> int | None:
    result: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _enum(hwnd, _lparam):  # type: ignore[no-untyped-def]
        handle = int(hwnd)
        if _is_usable_top_level(handle, exclude):
            result.append(handle)
            return False
        return True

    user32.EnumWindows(_enum, 0)
    return result[0] if result else None


def capture_foreground_window(
    exclude_hwnds: Iterable[int] | None = None,
) -> CaptureResult | None:
    bounds = get_foreground_window_rect(exclude_hwnds=exclude_hwnds)
    if bounds is None:
        return None
    left, top, width, height = bounds
    return capture_region(left, top, width, height)


def virtual_screen_bounds() -> tuple[int, int, int, int]:
    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79
    x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return int(x), int(y), int(w), int(h)
