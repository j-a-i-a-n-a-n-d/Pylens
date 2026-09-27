from __future__ import annotations

import ctypes
import ctypes.util
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, QTimer

from pylens.hotkeys import HotkeyBackend, ParsedHotkey


class EventHotKeyID(ctypes.Structure):
    _fields_ = [
        ("signature", ctypes.c_uint32),
        ("id", ctypes.c_uint32),
    ]


class EventTypeSpec(ctypes.Structure):
    _fields_ = [
        ("eventClass", ctypes.c_uint32),
        ("eventKind", ctypes.c_uint32),
    ]


_EVENT_HANDLER_PROTO = ctypes.CFUNCTYPE(
    ctypes.c_int32,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
)


@dataclass
class _HotkeyRegistration:
    hotkey_id: int
    key_code: int
    modifiers: int
    hotkey_ref: ctypes.c_void_p


_FOURCC_KEYB = 0x6B657962  # 'keyb'
_FOURCC_HKID = 0x686B6964  # 'hkid'
_FOURCC_PLNS = 0x504C4E53  # 'PLNS'
_EVENT_HOT_KEY_PRESSED = 6

# Carbon modifier masks (Events.h)
_MOD_CMD = 0x0100      # cmdKey (256)
_MOD_SHIFT = 0x0200    # shiftKey (512)
_MOD_OPTION = 0x0800   # optionKey (2048)
_MOD_CONTROL = 0x1000  # controlKey (4096)

# macOS virtual key codes (HIToolbox/Events.h)
_MAC_KEY_CODES: dict[str, int] = {
    # Letters (ANSI)
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04,
    "g": 0x05, "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09,
    "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E, "r": 0x0F,
    "y": 0x10, "t": 0x11, "1": 0x12, "2": 0x13, "3": 0x14,
    "4": 0x15, "6": 0x16, "5": 0x17, "9": 0x19, "7": 0x1A,
    "8": 0x1C, "0": 0x1D, "o": 0x1F, "u": 0x20, "i": 0x22,
    "p": 0x23, "l": 0x25, "j": 0x26, "k": 0x28, "n": 0x2D,
    "m": 0x2E,
    # Function keys
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76,
    "f5": 0x60, "f6": 0x61, "f7": 0x62, "f8": 0x64,
    "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
    # Navigation / Special
    "space": 0x31, "enter": 0x24, "return": 0x24,
    "escape": 0x35, "esc": 0x35, "tab": 0x30,
    "backspace": 0x33, "delete": 0x75,
    "home": 0x73, "end": 0x77, "pageup": 0x74, "pagedown": 0x79,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
}


class MacOSHotkeyBackend(HotkeyBackend):
    """Global hotkeys on macOS using Carbon HotKey API via ctypes."""

    def __init__(self) -> None:
        self._carbon: ctypes.CDLL | None = None
        self._next_id = 1
        self._registrations: dict[int, _HotkeyRegistration] = {}
        self._handlers: dict[int, Callable[[], None]] = {}
        self._event_target: ctypes.c_void_p | None = None
        self._event_handler_c: object | None = None
        self._handler_ref: ctypes.c_void_p | None = None
        self._init_carbon()

    def _init_carbon(self) -> None:
        """Initialize Carbon framework function signatures."""
        try:
            carbon_path = ctypes.util.find_library("Carbon")
            if not carbon_path:
                return
            self._carbon = ctypes.CDLL(carbon_path)

            if hasattr(self._carbon, "GetEventDispatcherTarget"):
                self._carbon.GetEventDispatcherTarget.restype = ctypes.c_void_p
                self._carbon.GetEventDispatcherTarget.argtypes = []

            self._carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
            self._carbon.GetApplicationEventTarget.argtypes = []

            self._carbon.RegisterEventHotKey.restype = ctypes.c_int32
            self._carbon.RegisterEventHotKey.argtypes = [
                ctypes.c_uint32,                 # inHotKeyCode
                ctypes.c_uint32,                 # inHotKeyModifiers
                EventHotKeyID,                   # inHotKeyID
                ctypes.c_void_p,                 # inTarget
                ctypes.c_uint32,                 # inOptions
                ctypes.POINTER(ctypes.c_void_p), # outHotKeyRef
            ]

            self._carbon.UnregisterEventHotKey.restype = ctypes.c_int32
            self._carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]

            self._carbon.InstallEventHandler.restype = ctypes.c_int32
            self._carbon.InstallEventHandler.argtypes = [
                ctypes.c_void_p,                 # inTarget
                _EVENT_HANDLER_PROTO,            # inHandler
                ctypes.c_uint32,                 # inNumTypes
                ctypes.POINTER(EventTypeSpec),   # inList
                ctypes.c_void_p,                 # inUserData
                ctypes.POINTER(ctypes.c_void_p), # outHandlerRef
            ]

            self._carbon.RemoveEventHandler.restype = ctypes.c_int32
            self._carbon.RemoveEventHandler.argtypes = [ctypes.c_void_p]

            self._carbon.GetEventParameter.restype = ctypes.c_int32
            self._carbon.GetEventParameter.argtypes = [
                ctypes.c_void_p,                 # inEvent
                ctypes.c_uint32,                 # inName
                ctypes.c_uint32,                 # inDesiredType
                ctypes.POINTER(ctypes.c_uint32), # outActualType
                ctypes.c_ulong,                  # inBufferSize
                ctypes.POINTER(ctypes.c_ulong),  # outActualSize
                ctypes.c_void_p,                 # outData
            ]
        except Exception:
            self._carbon = None

    def bind_to_window(self, window_handle: int) -> None:
        """On macOS, we use the dispatcher event target for global hotkey dispatch."""
        app = QCoreApplication.instance()
        if app is None:
            raise RuntimeError("QApplication required before binding hotkeys")

        if self._carbon:
            try:
                self._event_target = self._carbon.GetEventDispatcherTarget()
            except Exception:
                try:
                    self._event_target = self._carbon.GetApplicationEventTarget()
                except Exception:
                    self._event_target = None

    def register(self, spec: str, callback: Callable[[], None]) -> int:
        if self._event_target is None or self._carbon is None:
            raise RuntimeError("Carbon framework not available")

        parsed = self.parse_hotkey(spec)
        hotkey_id = self._next_id
        self._next_id += 1

        hk_id_struct = EventHotKeyID(signature=_FOURCC_PLNS, id=hotkey_id)
        hotkey_ref = ctypes.c_void_p(0)

        result = self._carbon.RegisterEventHotKey(
            parsed.key_code,
            parsed.modifiers,
            hk_id_struct,
            self._event_target,
            0,
            ctypes.byref(hotkey_ref),
        )

        if result != 0:
            raise OSError(f"Failed to register hotkey {parsed.display} (error {result})")

        self._registrations[hotkey_id] = _HotkeyRegistration(
            hotkey_id=hotkey_id,
            key_code=parsed.key_code,
            modifiers=parsed.modifiers,
            hotkey_ref=hotkey_ref,
        )
        self._handlers[hotkey_id] = callback

        if self._handler_ref is None:
            self._install_event_handler()

        return hotkey_id

    def _install_event_handler(self) -> None:
        if self._carbon is None or self._event_target is None:
            return

        def _on_carbon_event(next_handler, event, user_data):
            hk_id = EventHotKeyID()
            status = self._carbon.GetEventParameter(
                event,
                _FOURCC_HKID,
                _FOURCC_HKID,
                None,
                ctypes.sizeof(EventHotKeyID),
                None,
                ctypes.byref(hk_id),
            )
            if status == 0:
                handler = self._handlers.get(hk_id.id)
                if handler:
                    QTimer.singleShot(0, handler)
                    return 0
            return -9874  # eventNotHandledErr

        self._event_handler_c = _EVENT_HANDLER_PROTO(_on_carbon_event)
        event_spec = EventTypeSpec(eventClass=_FOURCC_KEYB, eventKind=_EVENT_HOT_KEY_PRESSED)
        handler_ref = ctypes.c_void_p(0)

        status = self._carbon.InstallEventHandler(
            self._event_target,
            self._event_handler_c,
            1,
            ctypes.byref(event_spec),
            None,
            ctypes.byref(handler_ref),
        )
        if status == 0:
            self._handler_ref = handler_ref

    def unregister_all(self) -> None:
        if self._carbon is None:
            return

        for reg in self._registrations.values():
            if reg.hotkey_ref:
                try:
                    self._carbon.UnregisterEventHotKey(reg.hotkey_ref)
                except Exception:
                    pass

        self._registrations.clear()
        self._handlers.clear()

    @staticmethod
    def parse_hotkey(spec: str) -> ParsedHotkey:
        parts = [p.strip().lower() for p in spec.replace("-", "+").split("+") if p.strip()]
        mods = 0
        key: str | None = None
        for part in parts:
            if part in ("ctrl", "control"):
                mods |= _MOD_CONTROL
            elif part in ("alt", "option", "opt"):
                mods |= _MOD_OPTION
            elif part == "shift":
                mods |= _MOD_SHIFT
            elif part in ("cmd", "command", "meta", "super", "win"):
                mods |= _MOD_CMD
            else:
                key = part

        if key is None or key not in _MAC_KEY_CODES:
            raise ValueError(f"Unsupported hotkey: {spec}")

        key_code = _MAC_KEY_CODES[key]

        display_parts = []
        if mods & _MOD_OPTION:
            display_parts.append("Option")
        if mods & _MOD_CONTROL:
            display_parts.append("Ctrl")
        if mods & _MOD_SHIFT:
            display_parts.append("Shift")
        if mods & _MOD_CMD:
            display_parts.append("Cmd")
        display_parts.append(key.upper())
        display = "+".join(display_parts)

        return ParsedHotkey(
            modifiers=mods,
            key=key,
            display=display,
            key_code=key_code,
        )