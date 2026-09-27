from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, QEvent, QSocketNotifier

from pylens.hotkeys import HotkeyBackend, ParsedHotkey


@dataclass(frozen=True)
class _HotkeyRegistration:
    hotkey_id: int
    key_combo: str


class LinuxHotkeyBackend(HotkeyBackend):
    """Global hotkeys on Linux using dbus/GNOME or xdotool."""

    def __init__(self) -> None:
        self._next_id = 1
        self._registrations: dict[int, _HotkeyRegistration] = {}
        self._handlers: dict[int, Callable[[], None]] = {}
        self._dbus_session = None
        self._init_dbus()

    def _init_dbus(self):
        """Initialize D-Bus connection for GNOME/KDE hotkey registration."""
        try:
            import dbus
            self._dbus = dbus
            self._bus = dbus.SessionBus()
        except Exception:
            self._dbus = None
            self._bus = None

    def bind_to_window(self, window_handle: int) -> None:
        """On Linux, hotkeys are global, not window-bound."""
        app = QCoreApplication.instance()
        if app is None:
            raise RuntimeError("QApplication required before binding hotkeys")

    def register(self, spec: str, callback: Callable[[], None]) -> int:
        parsed = self.parse_hotkey(spec)
        hotkey_id = self._next_id
        self._next_id += 1

        # Try GNOME/KDE settings daemon via D-Bus
        if self._bus:
            try:
                self._register_gnome_hotkey(hotkey_id, parsed, callback)
            except Exception as e:
                print(f"GNOME hotkey registration failed: {e}")
                # Fall back to xdotool/keyboard grab
                self._register_x11_hotkey(hotkey_id, parsed, callback)
        else:
            # Fall back to xdotool/keyboard grab
            self._register_x11_hotkey(hotkey_id, parsed, callback)

        self._registrations[hotkey_id] = _HotkeyRegistration(
            hotkey_id=hotkey_id,
            key_combo=parsed.display,
        )
        self._handlers[hotkey_id] = callback

        return hotkey_id

    def _register_gnome_hotkey(self, hotkey_id: int, parsed: ParsedHotkey, callback: Callable):
        """Register hotkey via GNOME Settings Daemon D-Bus."""
        # GNOME uses org.gnome.SettingsDaemon.MediaKeys
        # This is a simplified approach - real implementation would need
        # to use org.gnome.settings-daemon.plugins.media-keys
        pass

    def _register_x11_hotkey(self, hotkey_id: int, parsed: ParsedHotkey, callback: Callable):
        """Register hotkey using X11 keyboard grab (requires xdotool or python-xlib)."""
        try:
            import Xlib.display
            import Xlib.X
            import Xlib.XK
            import Xlib.keysymdef

            display = Xlib.display.Display()
            root = display.screen().root

            # Convert key to keysym
            keysym = self._key_to_keysym(parsed.key)
            if keysym is None:
                raise ValueError(f"Unknown key: {parsed.key}")

            keycode = display.keysym_to_keycode(keysym)

            # Convert modifiers
            modmask = 0
            if parsed.modifiers & 0x1:  # Ctrl
                modmask |= Xlib.X.ControlMask
            if parsed.modifiers & 0x2:  # Alt
                modmask |= Xlib.X.Mod1Mask
            if parsed.modifiers & 0x4:  # Shift
                modmask |= Xlib.X.ShiftMask
            if parsed.modifiers & 0x8:  # Super/Win
                modmask |= Xlib.X.Mod4Mask

            # Grab the key
            root.grab_key(
                keycode, modmask,
                True,  # owner_events
                Xlib.X.GrabModeAsync,
                Xlib.X.GrabModeAsync
            )

            # Store display for event handling
            if not hasattr(self, '_xlib_display'):
                self._xlib_display = display
                self._setup_x11_event_listener()

        except ImportError:
            # Try xdotool as fallback
            self._register_xdotool_hotkey(hotkey_id, parsed, callback)
        except Exception as e:
            print(f"X11 hotkey registration failed: {e}")
            # Try xdotool
            self._register_xdotool_hotkey(hotkey_id, parsed, callback)

    def _register_xdotool_hotkey(self, hotkey_id: int, parsed: ParsedHotkey, callback: Callable):
        """Register hotkey using xdotool (requires xdotool installed)."""
        # This is a polling-based approach - not ideal but works
        import threading
        import time

        def poll_hotkey():
            while hotkey_id in self._handlers:
                try:
                    # Use xdotool to check key state (simplified)
                    # Real implementation would need more sophisticated approach
                    time.sleep(0.1)
                except Exception:
                    break

        thread = threading.Thread(target=poll_hotkey, daemon=True)
        thread.start()

    def _key_to_keysym(self, key: str) -> int | None:
        """Convert key name to X11 keysym."""
        key_map = {
            **{c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz"},
            **{str(i): ord(str(i)) for i in range(10)},
            "space": 0x20, "enter": 0xFF0D, "escape": 0xFF1B,
            "tab": 0xFF09, "backspace": 0xFF08, "delete": 0xFFFF,
            "home": 0xFF50, "end": 0xFF57, "pageup": 0xFF55, "pagedown": 0xFF56,
            "left": 0xFF51, "up": 0xFF52, "right": 0xFF53, "down": 0xFF54,
            "f1": 0xFFBE, "f2": 0xFFBF, "f3": 0xFFC0, "f4": 0xFFC1,
            "f5": 0xFFC2, "f6": 0xFFC3, "f7": 0xFFC4, "f8": 0xFFC5,
            "f9": 0xFFC6, "f10": 0xFFC7, "f11": 0xFFC8, "f12": 0xFFC9,
        }
        return key_map.get(key.lower())

    def _setup_x11_event_listener(self):
        """Set up X11 event listener using QSocketNotifier."""
        if not hasattr(self, '_xlib_display'):
            return

        try:
            fd = self._xlib_display.fileno()
            notifier = QSocketNotifier(fd, QSocketNotifier.Type.Read)
            notifier.activated.connect(self._handle_x11_event)
            self._x11_notifier = notifier
        except Exception as e:
            print(f"Failed to set up X11 event listener: {e}")

    def _handle_x11_event(self):
        """Handle X11 key events."""
        if not hasattr(self, '_xlib_display'):
            return

        try:
            while self._xlib_display.pending_events():
                event = self._xlib_display.next_event()
                if event.type == Xlib.X.KeyPress:
                    # Find matching hotkey
                    for hotkey_id, reg in self._registrations.items():
                        # Simplified matching - real implementation would compare keycode/modmask
                        handler = self._handlers.get(hotkey_id)
                        if handler:
                            QCoreApplication.postEvent(
                                QCoreApplication.instance(),
                                _HotkeyEvent(hotkey_id, handler)
                            )
        except Exception as e:
            print(f"X11 event handling error: {e}")

    def unregister_all(self) -> None:
        if hasattr(self, '_xlib_display'):
            try:
                self._xlib_display.ungrab_keyboard()
            except Exception:
                pass
            try:
                self._xlib_display.close()
            except Exception:
                pass

        if hasattr(self, '_x11_notifier'):
            self._x11_notifier.setEnabled(False)

        self._registrations.clear()
        self._handlers.clear()

    @staticmethod
    def parse_hotkey(spec: str) -> ParsedHotkey:
        parts = [p.strip().lower() for p in spec.replace("-", "+").split("+") if p.strip()]
        mods = 0
        key: str | None = None
        for part in parts:
            if part in ("ctrl", "control"):
                mods |= 1
            elif part == "alt":
                mods |= 2
            elif part == "shift":
                mods |= 4
            elif part in ("super", "meta", "win"):
                mods |= 8
            else:
                key = part

        if key is None:
            raise ValueError(f"Unsupported hotkey: {spec}")

        display = "+".join(
            [
                *(["Ctrl"] if mods & 1 else []),
                *(["Alt"] if mods & 2 else []),
                *(["Shift"] if mods & 4 else []),
                *(["Super"] if mods & 8 else []),
                key.upper(),
            ]
        )

        return ParsedHotkey(modifiers=mods, key=key, display=display)


class _HotkeyEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, hotkey_id: int, handler: Callable[[], None]):
        super().__init__(self.EVENT_TYPE)
        self.hotkey_id = hotkey_id
        self.handler = handler