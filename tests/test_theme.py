"""Tests for the shared theme tokens and icon resolution."""

from __future__ import annotations

from gerberdiff import theme


def test_app_icon_path_resolves_committed_ico():
    # branding/app.ico is committed, so the dev-tree path resolves it.
    p = theme.app_icon_path()
    assert p is not None
    assert p.name == "app.ico"
    assert p.exists()


def test_palette_tokens_are_7char_hex():
    for token in (theme._BG, theme._ACCENT, theme._ADDED, theme._REMOVED, theme._SURFACE):
        assert isinstance(token, str)
        assert token.startswith("#") and len(token) == 7
