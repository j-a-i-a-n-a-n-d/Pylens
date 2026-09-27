from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from pylens.platform import current_platform, Platform


@dataclass(frozen=True)
class ParsedHotkey:
    """Parsed hotkey representation."""
    modifiers: int
    key: str
    display: str
    key_code: int = 0

    @property
    def vk(self) -> int:
        return self.key_code


class HotkeyBackend(ABC):
    """Abstract base for platform-specific global hotkey registration."""

    @abstractmethod
    def bind_to_window(self, window_handle: int) -> None:
        """Bind hotkeys to a window handle."""
        ...

    @abstractmethod
    def register(self, spec: str, callback: Callable[[], None]) -> int:
        """Register a global hotkey. Returns hotkey ID."""
        ...

    @abstractmethod
    def unregister_all(self) -> None:
        """Unregister all hotkeys."""
        ...

    @staticmethod
    @abstractmethod
    def parse_hotkey(spec: str) -> ParsedHotkey:
        """Parse a hotkey specification string."""
        ...


def create_hotkey_backend() -> HotkeyBackend:
    """Factory function to create platform-appropriate hotkey backend."""
    platform = current_platform()

    if platform == Platform.WINDOWS:
        from pylens.hotkeys.windows_hotkeys import WindowsHotkeyBackend
        return WindowsHotkeyBackend()
    elif platform == Platform.MACOS:
        from pylens.hotkeys.macos_hotkeys import MacOSHotkeyBackend
        return MacOSHotkeyBackend()
    elif platform == Platform.LINUX:
        from pylens.hotkeys.linux_hotkeys import LinuxHotkeyBackend
        return LinuxHotkeyBackend()
    else:
        raise RuntimeError(f"Unsupported platform: {platform}")