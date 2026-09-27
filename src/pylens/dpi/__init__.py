from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from pylens.platform import current_platform, Platform


@dataclass(frozen=True)
class DpiInfo:
    """DPI information for a screen."""
    logical_dpi: int
    physical_dpi: int
    scale_factor: float


class DpiBackend(ABC):
    """Abstract base for platform-specific DPI handling."""

    @abstractmethod
    def set_dpi_awareness(self) -> None:
        """Set process DPI awareness (Windows) or equivalent."""
        ...

    @abstractmethod
    def get_system_dpi(self) -> int:
        """Get system DPI (usually 96 on Windows, 72 on macOS)."""
        ...

    @abstractmethod
    def get_screen_dpi(self, screen_index: int = 0) -> DpiInfo:
        """Get DPI info for a specific screen."""
        ...

    @abstractmethod
    def physical_to_logical(self, value: float, screen_index: int = 0) -> float:
        """Convert physical pixels to logical pixels."""
        ...

    @abstractmethod
    def logical_to_physical(self, value: float, screen_index: int = 0) -> float:
        """Convert logical pixels to physical pixels."""
        ...


def create_dpi_backend() -> DpiBackend:
    """Factory function to create platform-appropriate DPI backend."""
    platform = current_platform()

    if platform == Platform.WINDOWS:
        from pylens.dpi.windows_dpi import WindowsDpiBackend
        return WindowsDpiBackend()
    elif platform == Platform.MACOS:
        from pylens.dpi.macos_dpi import MacOSDpiBackend
        return MacOSDpiBackend()
    elif platform == Platform.LINUX:
        from pylens.dpi.linux_dpi import LinuxDpiBackend
        return LinuxDpiBackend()
    else:
        from pylens.dpi.generic_dpi import GenericDpiBackend
        return GenericDpiBackend()