from __future__ import annotations

import ctypes
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QAbstractNativeEventFilter, QByteArray, QCoreApplication

from pylens.hotkeys import HotkeyBackend, ParsedHotkey

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

_VK_MAP = {
    **{c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz"},
    **{str(i): ord(str(i)) for i in range(10)},
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
    "space": 0x20,
    "enter": 0x0D,
    "escape": 0x1B,
    "tab": 0x09,
    "backspace": 0x08,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "printscreen": 0x2C,
}


@dataclass(frozen=True)
class _ParsedHotkey:
    modifiers: int
    vk: int
    display: str


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, handlers: dict[int, Callable[[], None]]) -> None:
        super().__init__()
        self._handlers = handlers

    def nativeEventFilter(self, eventType: QByteArray | bytes | bytearray, message: int) -> object:
        if bytes(eventType) not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            return False, 0
        msg = ctypes.wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY:
            hotkey_id = int(msg.wParam)
            handler = self._handlers.get(hotkey_id)
            if handler:
                handler()
                return True, 0
        return False, 0


class WindowsHotkeyBackend(HotkeyBackend):
    """Register global hotkeys with Win32 RegisterHotKey bound to the Qt app hwnd."""

    def __init__(self) -> None:
        self._user32 = getattr(ctypes, "windll", None).user32 if hasattr(ctypes, "windll") else None
        self._next_id = 1
        self._registered: dict[int, _ParsedHotkey] = {}
        self._handlers: dict[int, Callable[[], None]] = {}
        self._filter: _HotkeyFilter | None = None
        self._hwnd: int | None = None

    def bind_to_window(self, window_handle: int) -> None:
        self._hwnd = int(window_handle)
        app = QCoreApplication.instance()
        if app is None:
            raise RuntimeError("QApplication required before binding hotkeys")
        self._filter = _HotkeyFilter(self._handlers)
        app.installNativeEventFilter(self._filter)

    def register(self, spec: str, callback: Callable[[], None]) -> int:
        if self._hwnd is None:
            raise RuntimeError("Call bind_to_window first")
        parsed = self.parse_hotkey(spec)
        hotkey_id = self._next_id
        self._next_id += 1
        ok = self._user32.RegisterHotKey(
            self._hwnd,
            hotkey_id,
            parsed.modifiers,
            parsed.vk,
        )
        if not ok:
            raise OSError(f"Failed to register hotkey {parsed.display}")
        self._registered[hotkey_id] = parsed
        self._handlers[hotkey_id] = callback
        return hotkey_id

    def unregister_all(self) -> None:
        if self._hwnd is None:
            return
        for hotkey_id in list(self._registered):
            self._user32.UnregisterHotKey(self._hwnd, hotkey_id)
        self._registered.clear()
        self._handlers.clear()

    @staticmethod
    def parse_hotkey(spec: str) -> ParsedHotkey:
        parts = [p.strip().lower() for p in spec.replace("-", "+").split("+") if p.strip()]
        mods = 0
        key: str | None = None
        for part in parts:
            if part in ("ctrl", "control"):
                mods |= MOD_CONTROL
            elif part == "alt":
                mods |= MOD_ALT
            elif part == "shift":
                mods |= MOD_SHIFT
            elif part in ("win", "meta", "super"):
                mods |= MOD_WIN
            else:
                key = part
        if key is None or key not in _VK_MAP:
            raise ValueError(f"Unsupported hotkey: {spec}")
        display = "+".join(
            [
                *(["Ctrl"] if mods & MOD_CONTROL else []),
                *(["Alt"] if mods & MOD_ALT else []),
                *(["Shift"] if mods & MOD_SHIFT else []),
                *(["Win"] if mods & MOD_WIN else []),
                key.upper(),
            ]
        )
        return ParsedHotkey(
            modifiers=mods | MOD_NOREPEAT,
            key=key,
            display=display,
            key_code=_VK_MAP[key],
        )