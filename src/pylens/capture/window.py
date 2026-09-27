from __future__ import annotations

from collections.abc import Iterable

from pylens.capture import create_capture_backend
from pylens.models import CaptureResult


def capture_region(x: int, y: int, width: int, height: int) -> CaptureResult:
    """Capture a screen region using platform-specific backend."""
    backend = create_capture_backend()
    return backend.capture_region(x, y, width, height)


def capture_foreground_window(
    exclude_hwnds: Iterable[int] | None = None,
) -> CaptureResult | None:
    """Capture the foreground/active window using platform-specific backend."""
    backend = create_capture_backend()
    exclude = {int(h) for h in (exclude_hwnds or []) if h}
    return backend.capture_window(exclude_hwnds=exclude)


def virtual_screen_bounds() -> tuple[int, int, int, int]:
    """Get virtual screen bounds using platform-specific backend."""
    backend = create_capture_backend()
    bounds = backend.get_virtual_screen_bounds()
    return bounds.x, bounds.y, bounds.width, bounds.height