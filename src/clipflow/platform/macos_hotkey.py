"""Global shortcut on macOS via Carbon ``RegisterEventHotKey`` (ctypes; PyObjC has no Carbon).

Why this API (see docs/technical_decisions.md, D15):
* Needs no Accessibility, Input Monitoring, or Screen Recording permission. Verified on
  macOS 26.5: registration triggers no permission request.
* The OS delivers only *this* key combination to us and consumes it. We never observe other
  keystrokes, never post or simulate input, never read the clipboard.
* Event taps and NSEvent global monitors would need Input Monitoring/Accessibility.

Conflicts: macOS's own shortcuts are found with ``CopySymbolicHotKeys`` (live, including
user-customised ones). Other apps' hotkeys can't be detected — the OS accepts duplicates.
"""

from __future__ import annotations

import ctypes
import itertools
import logging
from collections.abc import Callable
from ctypes import (
    CFUNCTYPE,
    POINTER,
    Structure,
    byref,
    c_int32,
    c_size_t,
    c_uint32,
    c_void_p,
)

from clipflow.models.hotkey import MAC_KEY_CODES, Hotkey
from clipflow.platform.hotkey import HotkeyError

logger = logging.getLogger(__name__)

CARBON_PATH = "/System/Library/Frameworks/Carbon.framework/Carbon"
CORE_FOUNDATION_PATH = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"

CARBON_MODIFIERS = {"cmd": 1 << 8, "shift": 1 << 9, "option": 1 << 11, "ctrl": 1 << 12}
MODIFIER_MASK = sum(CARBON_MODIFIERS.values())
NO_ERR = 0
EVENT_NOT_HANDLED_ERR = -9874
EVENT_HOTKEY_EXISTS_ERR = -9878


def fourcc(text: str) -> int:
    return int.from_bytes(text.encode("ascii"), "big")


SIGNATURE = fourcc("VbBd")
EVENT_CLASS_KEYBOARD = fourcc("keyb")
EVENT_HOTKEY_PRESSED = 5
PARAM_DIRECT_OBJECT = fourcc("----")
TYPE_HOTKEY_ID = fourcc("hkid")


class EventHotKeyID(Structure):
    _fields_ = [("signature", c_uint32), ("id", c_uint32)]


class EventTypeSpec(Structure):
    _fields_ = [("eventClass", c_uint32), ("eventKind", c_uint32)]


EventHandlerProc = CFUNCTYPE(c_int32, c_void_p, c_void_p, c_void_p)


def _load_carbon() -> ctypes.CDLL:
    carbon = ctypes.CDLL(CARBON_PATH)
    carbon.GetApplicationEventTarget.restype = c_void_p
    carbon.GetApplicationEventTarget.argtypes = []
    carbon.InstallEventHandler.argtypes = [
        c_void_p,
        EventHandlerProc,
        c_size_t,
        POINTER(EventTypeSpec),
        c_void_p,
        POINTER(c_void_p),
    ]
    carbon.InstallEventHandler.restype = c_int32
    carbon.RemoveEventHandler.argtypes = [c_void_p]
    carbon.RemoveEventHandler.restype = c_int32
    carbon.RegisterEventHotKey.argtypes = [
        c_uint32,
        c_uint32,
        EventHotKeyID,
        c_void_p,
        c_uint32,
        POINTER(c_void_p),
    ]
    carbon.RegisterEventHotKey.restype = c_int32
    carbon.UnregisterEventHotKey.argtypes = [c_void_p]
    carbon.UnregisterEventHotKey.restype = c_int32
    carbon.GetEventParameter.argtypes = [
        c_void_p,
        c_uint32,
        c_uint32,
        c_void_p,
        c_size_t,
        c_void_p,
        c_void_p,
    ]
    carbon.GetEventParameter.restype = c_int32
    carbon.CopySymbolicHotKeys.argtypes = [POINTER(c_void_p)]
    carbon.CopySymbolicHotKeys.restype = c_int32
    return carbon


def carbon_modifiers(hotkey: Hotkey) -> int:
    return sum(CARBON_MODIFIERS[m] for m in hotkey.modifiers)


# Process-wide state. Carbon keeps a raw pointer to the installed handler, so there is
# exactly one handler for the whole process, installed once and never freed (a handler per
# backend instance would leave dangling pointers behind when an instance is collected).
_lib: ctypes.CDLL | None = None
_callbacks: dict[int, Callable[[], None]] = {}
_ids = itertools.count(1)
_handler_ref = c_void_p()
_handler_installed = False


def _carbon() -> ctypes.CDLL:
    global _lib
    if _lib is None:
        _lib = _load_carbon()
    return _lib


def _on_event(_call: int, event: int, _data: int) -> int:
    # Runs on the main thread inside the Cocoa event loop. Never raise into C.
    try:
        hotkey_id = EventHotKeyID()
        status = _carbon().GetEventParameter(
            event,
            PARAM_DIRECT_OBJECT,
            TYPE_HOTKEY_ID,
            None,
            ctypes.sizeof(hotkey_id),
            None,
            byref(hotkey_id),
        )
        if status != NO_ERR or hotkey_id.signature != SIGNATURE:
            return EVENT_NOT_HANDLED_ERR
        callback = _callbacks.get(hotkey_id.id)
        if callback is None:
            return EVENT_NOT_HANDLED_ERR
        callback()
        return NO_ERR
    except Exception as exc:
        logger.warning("Global shortcut handler failed (%s)", type(exc).__name__)
        return EVENT_NOT_HANDLED_ERR


_HANDLER = EventHandlerProc(_on_event)  # module-level: lives as long as the process


def _install_handler() -> None:
    global _handler_installed
    if _handler_installed:
        return
    lib = _carbon()
    spec = EventTypeSpec(EVENT_CLASS_KEYBOARD, EVENT_HOTKEY_PRESSED)
    status = lib.InstallEventHandler(
        lib.GetApplicationEventTarget(), _HANDLER, 1, byref(spec), None, byref(_handler_ref)
    )
    if status != NO_ERR:
        raise HotkeyError(f"macOS couldn't set up global shortcuts (error {status}).")
    _handler_installed = True


class _CarbonRegistration:
    def __init__(self, ident: int, ref: c_void_p) -> None:
        self.ident = ident
        self._ref = ref
        self.active = True

    def unregister(self) -> None:
        if not self.active:
            return
        self.active = False
        _callbacks.pop(self.ident, None)
        status = _carbon().UnregisterEventHotKey(self._ref)
        if status != NO_ERR:
            logger.warning("UnregisterEventHotKey failed (%d)", status)


class CarbonHotkeyBackend:
    # -- conflicts --------------------------------------------------------------------

    def system_conflict(self, hotkey: Hotkey) -> str | None:
        code = MAC_KEY_CODES.get(hotkey.key)
        if code is None:
            return None
        try:
            entries = self._symbolic_hotkeys()
        except Exception as exc:  # OS boundary: never block a shortcut on a lookup failure
            logger.warning("Could not read macOS shortcuts (%s)", type(exc).__name__)
            return None
        wanted = carbon_modifiers(hotkey)
        for entry in entries:
            if (
                entry.get("kHISymbolicHotKeyEnabled")
                and int(entry.get("kHISymbolicHotKeyCode", -1)) == code
                and int(entry.get("kHISymbolicHotKeyModifiers", 0)) & MODIFIER_MASK == wanted
            ):
                return (
                    f"{hotkey.display()} is already a macOS shortcut "
                    "(System Settings → Keyboard → Keyboard Shortcuts)"
                )
        return None

    def _symbolic_hotkeys(self) -> list[dict]:
        import objc  # PyObjC bridges the CFArray of CFDictionaries

        out = c_void_p()
        status = _carbon().CopySymbolicHotKeys(byref(out))
        if status != NO_ERR or not out.value:
            raise OSError(f"CopySymbolicHotKeys failed ({status})")
        try:
            array = objc.objc_object(c_void_p=out.value)
            return [dict(entry) for entry in array]
        finally:
            core_foundation = ctypes.CDLL(CORE_FOUNDATION_PATH)
            core_foundation.CFRelease.argtypes = [c_void_p]
            core_foundation.CFRelease(out)

    # -- registration -----------------------------------------------------------------

    def register(self, hotkey: Hotkey, callback: Callable[[], None]) -> _CarbonRegistration:
        code = MAC_KEY_CODES.get(hotkey.key)
        if code is None:
            raise HotkeyError("That key can't be used for a global shortcut.")
        _install_handler()
        lib = _carbon()
        ident = next(_ids)
        ref = c_void_p()
        status = lib.RegisterEventHotKey(
            code,
            carbon_modifiers(hotkey),
            EventHotKeyID(SIGNATURE, ident),
            lib.GetApplicationEventTarget(),
            0,
            byref(ref),
        )
        if status == EVENT_HOTKEY_EXISTS_ERR:
            raise HotkeyError(f"{hotkey.display()} is already registered.")
        if status != NO_ERR:
            raise HotkeyError(f"macOS refused {hotkey.display()} (error {status}).")
        _callbacks[ident] = callback
        return _CarbonRegistration(ident, ref)
