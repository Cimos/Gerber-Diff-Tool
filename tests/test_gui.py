"""GUI tests that do not require a display."""

from __future__ import annotations

import gerberdiff.gui as gui


def test_gui_module_imports():
    # Must import cleanly even where tkinter is absent (some uv standalone builds).
    assert hasattr(gui, "main")
    assert hasattr(gui, "_TK_AVAILABLE")


def test_gui_main_without_tk_is_graceful(monkeypatch, capsys):
    monkeypatch.setattr(gui, "_TK_AVAILABLE", False)
    code = gui.main()
    assert code == 1
    assert "tkinter" in capsys.readouterr().err.lower()


def test_parse_int_field():
    from gerberdiff.gui import parse_int_field

    assert parse_int_field("42", 0) == 42
    assert parse_int_field("  7 ", 0) == 7
    assert parse_int_field("", 20) == 20
    assert parse_int_field("abc", 99) == 99
    assert parse_int_field(None, 5) == 5
