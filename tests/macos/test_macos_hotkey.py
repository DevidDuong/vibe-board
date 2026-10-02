"""Real Carbon hot-key backend tests (macOS only).

They register obscure combinations (⌃⌥⇧⌘F18/F19), never the user's shortcut, and release
them immediately. The "pressed" check sends an in-process Carbon event straight to our own
application target — it is not keyboard input and never reaches any other app. A real key
press can only be verified by a person (tests/manual_macos_checklist.md, section H).
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import POINTER, byref, c_double, c_size_t, c_uint32, c_void_p

import pytest

from clipflow.models.hotkey import MAC_KEY_NAMES, Hotkey
from clipflow.platform.hotkey import HotkeyError

pytestmark = [
    pytest.mark.macos,
    pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS Carbon"),
]

PROBE = Hotkey.of("F19", "ctrl", "option", "shift", "cmd")
PROBE_2 = Hotkey.of("F18", "ctrl", "option", "shift", "cmd")


@pytest.fixture
def backend(qapp):
    from clipflow.platform.macos_hotkey import CarbonHotkeyBackend

    return CarbonHotkeyBackend()


def send_in_process_hotkey_event(ident: int) -> int:
    from clipflow.platform import macos_hotkey as mh

    carbon = ctypes.CDLL(mh.CARBON_PATH)
    carbon.CreateEvent.argtypes = [
        c_void_p,
        c_uint32,
        c_uint32,
        c_double,
        c_uint32,
        POINTER(c_void_p),
    ]
    carbon.SetEventParameter.argtypes = [c_void_p, c_uint32, c_uint32, c_size_t, c_void_p]
    carbon.SendEventToEventTarget.argtypes = [c_void_p, c_void_p]
    carbon.GetApplicationEventTarget.restype = c_void_p
    carbon.ReleaseEvent.argtypes = [c_void_p]
    event = c_void_p()
    carbon.CreateEvent(None, mh.EVENT_CLASS_KEYBOARD, mh.EVENT_HOTKEY_PRESSED, 0.0, 0, byref(event))
    hotkey_id = mh.EventHotKeyID(mh.SIGNATURE, ident)
    carbon.SetEventParameter(
        event, mh.PARAM_DIRECT_OBJECT, mh.TYPE_HOTKEY_ID, ctypes.sizeof(hotkey_id), byref(hotkey_id)
    )
    status = carbon.SendEventToEventTarget(event, carbon.GetApplicationEventTarget())
    carbon.ReleaseEvent(event)
    return status


def test_register_receive_and_unregister(backend):
    pressed = []
    registration = backend.register(PROBE, lambda: pressed.append(PROBE))
    try:
        assert send_in_process_hotkey_event(registration.ident) == 0
        assert pressed == [PROBE]
    finally:
        registration.unregister()
        registration.unregister()  # idempotent
    assert send_in_process_hotkey_event(registration.ident) != 0  # no longer handled


def test_duplicate_registration_is_reported(backend):
    first = backend.register(PROBE_2, lambda: None)
    try:
        with pytest.raises(HotkeyError, match="already registered"):
            backend.register(PROBE_2, lambda: None)
    finally:
        first.unregister()


def test_enabled_macos_shortcut_is_detected(backend):
    from clipflow.platform.macos_hotkey import CARBON_MODIFIERS, MODIFIER_MASK

    for entry in backend._symbolic_hotkeys():
        name = MAC_KEY_NAMES.get(int(entry.get("kHISymbolicHotKeyCode", -1)))
        mods = int(entry.get("kHISymbolicHotKeyModifiers", 0)) & MODIFIER_MASK
        if entry.get("kHISymbolicHotKeyEnabled") and name and mods:
            hotkey = Hotkey(name, frozenset(m for m, bit in CARBON_MODIFIERS.items() if mods & bit))
            assert "macOS shortcut" in backend.system_conflict(hotkey)
            return
    pytest.skip("no enabled macOS shortcut with a supported key on this Mac")


def test_default_shortcut_is_not_a_macos_shortcut_here(backend):
    from clipflow.models.hotkey import DEFAULT_HOTKEY

    assert backend.system_conflict(DEFAULT_HOTKEY) is None
