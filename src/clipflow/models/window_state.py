from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WindowState:
    """Remembered palette geometry in logical pixels: frame top-left and client size."""

    x: int
    y: int
    width: int
    height: int
