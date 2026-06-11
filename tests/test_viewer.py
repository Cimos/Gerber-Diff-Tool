"""Tests for the native viewer's pure helpers (no display required)."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from gerberdiff.compose import (
    action_for_key,
    compose_master,
    decode_png,
    order_layers,
    visible_crop,
)


class _Pair:
    def __init__(self, layer_type: str) -> None:
        self.layer_type = layer_type
        self.key = layer_type.lower()


class _LD:
    def __init__(self, changed: bool, changed_pixels: int) -> None:
        self.changed = changed
        self.changed_pixels = changed_pixels
        self.pair = _Pair("Layer")


def _img(color, size=(4, 4)) -> Image.Image:
    return Image.new("RGB", size, color)


def _png(color) -> bytes:
    buf = io.BytesIO()
    _img(color).save(buf, "PNG")
    return buf.getvalue()


def test_order_layers_changed_first_then_biggest():
    unchanged = _LD(False, 0)
    small = _LD(True, 5)
    big = _LD(True, 99)
    assert order_layers([unchanged, small, big]) == [big, small, unchanged]


def test_decode_png_none_and_roundtrip():
    assert decode_png(None) is None
    img = decode_png(_png((10, 20, 30)))
    assert img is not None and img.mode == "RGB" and img.size == (4, 4)


def test_compose_master_basic_modes():
    ov, a, b = _img("red"), _img("blue"), _img("green")
    assert compose_master("overlay", ov, a, b) is ov
    assert compose_master("a", ov, a, b) is a
    assert compose_master("b", ov, a, b) is b
    assert compose_master("split", ov, a, b) is a  # split shows A on the primary canvas


def test_compose_master_falls_back_when_side_missing():
    ov = _img("red")
    assert compose_master("swipe", ov, None, None) is ov
    assert compose_master("onion", ov, None, None) is ov
    assert compose_master("a", ov, None, _img("green")) is ov


def test_compose_master_onion_blends_midpoint():
    a, b = _img((0, 0, 0)), _img((100, 100, 100))
    assert compose_master("onion", a, a, b, alpha=0.5).getpixel((0, 0)) == (50, 50, 50)


def test_compose_master_swipe_splits_left_right():
    a = _img((255, 0, 0), (10, 1))
    b = _img((0, 0, 255), (10, 1))
    out = compose_master("swipe", b, a, b, swipe=0.5)
    assert out.getpixel((0, 0)) == (255, 0, 0)  # left half = A
    assert out.getpixel((9, 0)) == (0, 0, 255)  # right half = B


def test_visible_crop_clamps_to_image_bounds():
    sx0, sy0, sx1, sy1 = visible_crop(100, 100, 1.0, 0, 0, 40, 40)
    assert (sx0, sy0) == (0, 0)
    assert 0 < sx1 <= 100 and 0 < sy1 <= 100


def test_visible_crop_accounts_for_pan():
    sx0, _sy0, _sx1, _sy1 = visible_crop(100, 100, 1.0, -50, 0, 40, 40)
    assert sx0 == 50  # the left 50px are panned off-screen


def test_action_for_key_navigation_and_zoom():
    assert action_for_key("Left") == "prev"
    assert action_for_key("Up") == "prev"
    assert action_for_key("Right") == "next"
    assert action_for_key("space") == "next"
    assert action_for_key("plus") == "zoom_in"
    assert action_for_key("minus") == "zoom_out"
    assert action_for_key("Home") == "fit"
    assert action_for_key("0") == "fit"


def test_action_for_key_digits_select_modes_in_order():
    assert action_for_key("1") == "mode:overlay"
    assert action_for_key("2") == "mode:a"
    assert action_for_key("4") == "mode:split"
    assert action_for_key("6") == "mode:onion"


def test_action_for_key_unmapped_returns_none():
    assert action_for_key("q") is None
    assert action_for_key("7") is None
    assert action_for_key("Escape") is None


def test_viewer_module_imports():
    # viewer.py is the Tk shell; some headless CPython builds ship without tkinter.
    pytest.importorskip("tkinter")
    import gerberdiff.viewer  # noqa: F401
