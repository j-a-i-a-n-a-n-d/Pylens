from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# Re-export for backward compatibility
from pylens.hotkeys import create_hotkey_backend, ParsedHotkey


@dataclass(frozen=True)
class _ParsedHotkey:
    modifiers: int
    vk: int
    display: str


def parse_hotkey(spec: str) -> ParsedHotkey:
    """Parse a hotkey specification string (platform-independent)."""
    backend = create_hotkey_backend()
    return backend.parse_hotkey(spec)


class HotkeyManager:
    """Cross-platform global hotkey manager."""

    def __init__(self) -> None:
        self._backend = create_hotkey_backend()

    def bind_to_widget(self, hwnd: int) -> None:
        self._backend.bind_to_window(hwnd)

    def register(self, spec: str, callback: Callable[[], None]) -> int:
        return self._backend.register(spec, callback)

    def unregister_all(self) -> None:
        self._backend.unregister_all()