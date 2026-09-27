from __future__ import annotations

import pytest

from pylens.hotkeys.macos_hotkeys import MacOSHotkeyBackend, _MAC_KEY_CODES
from pylens.hotkeys.windows_hotkeys import WindowsHotkeyBackend
from pylens.settings import Settings, default_hotkey_region, default_hotkey_window
from pylens.platform import current_platform, Platform


def test_macos_parse_hotkey():
    backend = MacOSHotkeyBackend()
    
    # Option + Ctrl + R
    p1 = backend.parse_hotkey("option+ctrl+r")
    assert p1.key == "r"
    assert p1.display == "Option+Ctrl+R"
    assert p1.key_code == _MAC_KEY_CODES["r"]
    assert p1.modifiers & 0x0800  # optionKey
    assert p1.modifiers & 0x1000  # controlKey

    # Ctrl + Alt + R (alias)
    p2 = backend.parse_hotkey("ctrl+alt+r")
    assert p2.display == "Option+Ctrl+R"
    assert p2.key_code == _MAC_KEY_CODES["r"]

    # Option + Ctrl + T
    p3 = backend.parse_hotkey("option+ctrl+t")
    assert p3.display == "Option+Ctrl+T"
    assert p3.key_code == _MAC_KEY_CODES["t"]

    # Cmd + Shift + A
    p4 = backend.parse_hotkey("cmd+shift+a")
    assert p4.display == "Shift+Cmd+A"
    assert p4.key_code == _MAC_KEY_CODES["a"]
    assert p4.modifiers & 0x0100  # cmdKey
    assert p4.modifiers & 0x0200  # shiftKey


def test_macos_parse_invalid_hotkey():
    backend = MacOSHotkeyBackend()
    with pytest.raises(ValueError):
        backend.parse_hotkey("invalid_key_xyz")


def test_windows_parse_hotkey():
    backend = WindowsHotkeyBackend()
    p = backend.parse_hotkey("ctrl+alt+r")
    assert p.key == "r"
    assert p.display == "Ctrl+Alt+R"
    assert p.key_code == ord("R")
    assert p.vk == ord("R")


def test_default_hotkeys_platform():
    if current_platform() == Platform.MACOS:
        assert default_hotkey_region() == "option+ctrl+r"
        assert default_hotkey_window() == "option+ctrl+t"
        s = Settings()
        assert s.hotkey_region == "option+ctrl+r"
        assert s.hotkey_window == "option+ctrl+t"
    elif current_platform() == Platform.WINDOWS:
        assert default_hotkey_region() == "ctrl+alt+r"
        assert default_hotkey_window() == "ctrl+alt+t"
