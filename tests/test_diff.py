"""Unit tests for the pixel-diff engine using synthetic images (no renderer)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from gerberdiff.diff import diff_layer
from gerberdiff.models import LayerPair, PairStatus


def _image(white_pixels: set[tuple[int, int]], size: int = 10) -> Image.Image:
    arr = np.zeros((size, size), dtype=np.uint8)
    for x, y in white_pixels:
        arr[y, x] = 255
    return Image.fromarray(arr, mode="L")


def _pair() -> LayerPair:
    return LayerPair(
        key="x-f_cu.gbr",
        layer_type="Top Copper",
        status=PairStatus.MATCHED,
        path_a=Path("a"),
        path_b=Path("b"),
    )


def test_identical_images_have_no_change():
    img = _image({(1, 1), (2, 2), (3, 3)})
    result = diff_layer(_pair(), img, img.copy())
    assert result.changed_pixels == 0
    assert result.common_pixels == 3
    assert result.changed is False
    assert result.overlay_png is not None


def test_added_and_removed_pixels_counted():
    image_a = _image({(1, 1), (5, 5)})          # (5,5) only in A -> removed
    image_b = _image({(1, 1), (8, 8)})          # (8,8) only in B -> added
    result = diff_layer(_pair(), image_a, image_b)
    assert result.removed_pixels == 1
    assert result.added_pixels == 1
    assert result.common_pixels == 1
    assert result.changed is True


def test_added_layer_with_missing_side():
    pair = LayerPair(
        key="x-f_mask.gbr",
        layer_type="Top Soldermask",
        status=PairStatus.ADDED,
        path_a=None,
        path_b=Path("b"),
    )
    image_b = _image({(4, 4), (5, 5)})
    result = diff_layer(pair, None, image_b)
    assert result.added_pixels == 2
    assert result.removed_pixels == 0
    assert result.changed is True  # ADDED status is always a change
