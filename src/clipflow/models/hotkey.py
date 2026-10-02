"""Global shortcut value object, parsing, display, and validation. Platform-neutral data only.

Stored as text such as ``ctrl+option+cmd+V``. ``key`` names a *physical* key on a US
(ANSI) keyboard, so the shortcut keeps working when another input source (e.g. Khmer) is
active — the same behavior as macOS's own shortcuts.
"""

from __future__ import annotations

import string
from dataclasses import dataclass

MODIFIER_ORDER = ("ctrl", "option", "shift", "cmd")
MODIFIER_SYMBOLS = {"ctrl": "⌃", "option": "⌥", "shift": "⇧", "cmd": "⌘"}
PUNCTUATION_KEYS = ("-", "=", "[", "]", "\\", ";", "'", ",", ".", "/", "`")
KEY_NAMES: tuple[str, ...] = (
    *string.ascii_uppercase,
    *string.digits,
    *(f"F{n}" for n in range(1, 21)),
    "Space",
    *PUNCTUATION_KEYS,
)

# macOS virtual key codes (Carbon kVK_*) for each supported physical key. Plain data, used to
# register with the OS and to read the physical key from a key event.
MAC_KEY_CODES: dict[str, int] = {
    "A": 0x00, "S": 0x01, "D": 0x02, "F": 0x03, "H": 0x04, "G": 0x05, "Z": 0x06, "X": 0x07,
    "C": 0x08, "V": 0x09, "B": 0x0B, "Q": 0x0C, "W": 0x0D, "E": 0x0E, "R": 0x0F, "Y": 0x10,
    "T": 0x11, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18,
    "9": 0x19, "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E, "O": 0x1F, "U": 0x20,
    "[": 0x21, "I": 0x22, "P": 0x23, "L": 0x25, "J": 0x26, "'": 0x27, "K": 0x28, ";": 0x29,
    "\\": 0x2A, ",": 0x2B, "/": 0x2C, "N": 0x2D, "M": 0x2E, ".": 0x2F, "Space": 0x31,
    "`": 0x32, "F1": 0x7A, "F2": 0x78, "F3": 0x63, "F4": 0x76, "F5": 0x60, "F6": 0x61,
    "F7": 0x62, "F8": 0x64, "F9": 0x65, "F10": 0x6D, "F11": 0x67, "F12": 0x6F, "F13": 0x69,
    "F14": 0x6B, "F15": 0x71, "F16": 0x6A, "F17": 0x40, "F18": 0x4F, "F19": 0x50, "F20": 0x5A,
}  # fmt: skip
MAC_KEY_NAMES: dict[int, str] = {code: name for name, code in MAC_KEY_CODES.items()}


@dataclass(frozen=True, slots=True)
class Hotkey:
    key: str
    modifiers: frozenset[str]

    @classmethod
    def of(cls, key: str, *modifiers: str) -> Hotkey:
        return cls(key, frozenset(modifiers))

    @classmethod
    def parse(cls, text: str) -> Hotkey:
        """Parse ``ctrl+option+cmd+V``. Raises ``ValueError`` for anything malformed."""
        parts = text.split("+")
        if text.endswith("+") or len(parts) < 2:
            raise ValueError("expected modifiers and a key, e.g. ctrl+option+cmd+V")
        *mods, key = parts
        key = key.upper() if len(key) == 1 else key.capitalize() if key.lower() == "space" else key
        unknown = [m for m in mods if m not in MODIFIER_ORDER]
        if unknown or key not in KEY_NAMES or len(set(mods)) != len(mods):
            raise ValueError(f"unsupported shortcut: {text!r}")
        return cls(key, frozenset(mods))

    def to_text(self) -> str:
        mods = [m for m in MODIFIER_ORDER if m in self.modifiers]
        return "+".join([*mods, self.key])

    def display(self) -> str:
        """macOS style, e.g. ⌃⌥⌘V (modifiers in Apple's standard order)."""
        symbols = "".join(MODIFIER_SYMBOLS[m] for m in MODIFIER_ORDER if m in self.modifiers)
        return f"{symbols}{self.key}"


# Control-Option-Command-V. Not a macOS shortcut (checked against the system's own list),
# not ⌘⇧V (Paste and Match Style), and three modifiers keep it clear of app shortcuts.
DEFAULT_HOTKEY = Hotkey.of("V", "ctrl", "option", "cmd")

# Always refused, with the reason shown to the user. System shortcuts that are *enabled* on
# this Mac are additionally detected live by the platform backend.
RESERVED: dict[Hotkey, str] = {
    Hotkey.of("V", "shift", "cmd"): "⇧⌘V is Paste and Match Style in many apps",
    Hotkey.of("V", "option", "shift", "cmd"): "⌥⇧⌘V is Paste and Match Style in many apps",
    Hotkey.of("Q", "shift", "cmd"): "⇧⌘Q logs you out of macOS",
    Hotkey.of("Q", "option", "shift", "cmd"): "⌥⇧⌘Q logs you out of macOS",
    Hotkey.of("Q", "ctrl", "cmd"): "⌃⌘Q locks the screen",
    Hotkey.of("F", "ctrl", "cmd"): "⌃⌘F toggles full screen",
    Hotkey.of("Space", "ctrl", "cmd"): "⌃⌘Space opens Emoji & Symbols",
    Hotkey.of("Space", "option", "cmd"): "⌥⌘Space opens a Finder search window",
    Hotkey.of("Space", "ctrl", "option"): "⌃⌥Space switches input sources",
    Hotkey.of("D", "option", "cmd"): "⌥⌘D shows and hides the Dock",
    Hotkey.of("H", "option", "cmd"): "⌥⌘H hides other apps",
    Hotkey.of("M", "option", "cmd"): "⌥⌘M minimizes all windows",
    Hotkey.of("W", "option", "cmd"): "⌥⌘W closes all windows",
    Hotkey.of("/", "shift", "cmd"): "⇧⌘/ opens the Help menu",
    **{Hotkey.of(n, "shift", "cmd"): f"⇧⌘{n} takes a screenshot" for n in ("3", "4", "5", "6")},
    **{Hotkey.of(n, "ctrl", "shift", "cmd"): f"⌃⇧⌘{n} takes a screenshot" for n in ("3", "4")},
}


def validation_problem(hotkey: Hotkey) -> str | None:
    """Why ``hotkey`` can't be used, or None. Does not check other apps (see platform)."""
    if hotkey.key not in KEY_NAMES or not hotkey.modifiers <= set(MODIFIER_ORDER):
        return "That key can't be used for a global shortcut."
    if not ({"cmd", "ctrl"} & hotkey.modifiers) or len(hotkey.modifiers) < 2:
        return (
            "Use ⌘ or ⌃ plus at least one more modifier (for example ⌃⌥⌘V), so the shortcut "
            "can't clash with typing or everyday shortcuts like ⌘C."
        )
    if hotkey in RESERVED:
        return f"{RESERVED[hotkey]}."
    return None
