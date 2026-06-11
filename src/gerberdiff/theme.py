"""Shared dark-theme palette for the desktop GUI and the in-app viewer.

The accent is darkened so white-on-accent text meets WCAG AA (4.7:1); hover is
darker still, so contrast improves on interaction. Colours match the brand mark
(branding/logo-mark.svg) and the colour-blind-safe diff overlay.
"""

from __future__ import annotations

_BG = "#16181d"
_SURFACE = "#1e2128"
_FIELD = "#262a33"
_BORDER = "#30343d"
_TEXT = "#e7e9ee"
_MUTED = "#9aa0aa"
_ACCENT = "#2f6fe0"  # white text on this = 4.7:1 (AA)
_ACCENT_HI = "#2862c9"  # hover/focus: darker, so contrast improves on interaction
_ACCENT_DIM = "#33436b"  # disabled/busy accent
_SUCCESS = "#37c95a"
_DANGER = "#ff6b61"
_ON_ACCENT = "#ffffff"
_ADDED = "#2f6fe0"  # revision B added geometry (blue)
_REMOVED = "#e07b2d"  # revision A removed geometry (orange)
