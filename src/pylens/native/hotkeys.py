from __future__ import annotations

import ctypes
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QAbstractNativeEventFilter, QByteArray, QCoreApplication

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
}


@dataclass(frozen=True)
class ParsedHotkey:
    modifiers: int
    vk: int
    display: str


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
    return ParsedHotkey(modifiers=mods | MOD_NOREPEAT, vk=_VK_MAP[key], display=display)


class HotkeyFilter(QAbstractNativeEventFilter):
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


class HotkeyManager:
    """Register global hotkeys with Win32 RegisterHotKey bound to the Qt app hwnd."""

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._next_id = 1
        self._registered: dict[int, ParsedHotkey] = {}
        self._handlers: dict[int, Callable[[], None]] = {}
        self._filter: HotkeyFilter | None = None
        self._hwnd: int | None = None

    def bind_to_widget(self, hwnd: int) -> None:
        self._hwnd = int(hwnd)
        app = QCoreApplication.instance()
        if app is None:
            raise RuntimeError("QApplication required before binding hotkeys")
        self._filter = HotkeyFilter(self._handlers)
        app.installNativeEventFilter(self._filter)

    def register(self, spec: str, callback: Callable[[], None]) -> int:
        if self._hwnd is None:
            raise RuntimeError("Call bind_to_widget first")
        parsed = parse_hotkey(spec)
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
