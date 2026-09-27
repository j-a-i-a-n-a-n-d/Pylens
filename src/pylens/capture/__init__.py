from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from pylens.models import CaptureResult
from pylens.platform import current_platform, Platform


@dataclass(frozen=True)
class ScreenBounds:
    """Virtual screen bounds in physical pixels."""
    x: int
    y: int
    width: int
    height: int


class RegionSelector(Protocol):
    """Protocol for platform-specific region selection UI."""

    def show(self) -> None:
        """Show the region selector."""
        ...

    def close(self) -> None:
        """Close the region selector."""
        ...


class CaptureBackend(ABC):
    """Abstract base for platform-specific screen capture."""

    @abstractmethod
    def capture_region(self, x: int, y: int, width: int, height: int) -> CaptureResult:
        """Capture a screen region."""
        ...

    @abstractmethod
    def capture_window(self, window_id: int | None = None) -> CaptureResult | None:
        """Capture a specific window or the foreground window."""
        ...

    @abstractmethod
    def get_virtual_screen_bounds(self) -> ScreenBounds:
        """Get virtual screen bounds (all monitors combined)."""
        ...

    @abstractmethod
    def list_windows(self) -> list[WindowInfo]:
        """List available windows for capture."""
        ...


@dataclass(frozen=True)
class WindowInfo:
    """Information about a window."""
    id: int
    title: str
    x: int
    y: int
    width: int
    height: int
    is_visible: bool
    is_minimized: bool
    process_name: str | None = None


def create_capture_backend() -> CaptureBackend:
    """Factory function to create platform-appropriate capture backend."""
    platform = current_platform()

    if platform == Platform.WINDOWS:
        from pylens.capture.windows_backend import WindowsCaptureBackend
        return WindowsCaptureBackend()
    elif platform == Platform.MACOS:
        from pylens.capture.macos_backend import MacOSCaptureBackend
        return MacOSCaptureBackend()
    elif platform == Platform.LINUX:
        from pylens.capture.linux_backend import LinuxCaptureBackend
        return LinuxCaptureBackend()
    else:
        raise RuntimeError(f"Unsupported platform: {platform}")


def create_region_selector(on_capture: callable, on_cancel: callable) -> RegionSelector:
    """Factory function to create platform-appropriate region selector."""
    platform = current_platform()

    if platform == Platform.WINDOWS:
        from pylens.capture.windows_region import WindowsRegionSelector
        return WindowsRegionSelector(on_capture, on_cancel)
    elif platform == Platform.MACOS:
        from pylens.capture.macos_region import MacOSRegionSelector
        return MacOSRegionSelector(on_capture, on_cancel)
    elif platform == Platform.LINUX:
        from pylens.capture.linux_region import LinuxRegionSelector
        return LinuxRegionSelector(on_capture, on_cancel)
    else:
        raise RuntimeError(f"Unsupported platform: {platform}")