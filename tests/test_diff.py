"""Unit tests for the pixel-diff engine using synthetic images (no renderer)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from gerberdiff.diff import (
    COLOR_ADDED,
    COLOR_COMMON,
    COLOR_REMOVED,
    diff_layer,
    diff_masks,
    overlay_image,
    png_bytes,
    presence_mask,
)
from gerberdiff.models import LayerPair, PairStatus


def _image(white_pixels: set[tuple[int, int]], size: int = 10) -> Image.Image:
    arr = np.zeros((size, size), dtype=np.uint8)
    for x, y in white_pixels:
        arr[y, x] = 255
    return Image.fromarray(arr, mode="L")


def _pair(status: PairStatus = PairStatus.MATCHED, key: str = "x-f_cu.gbr") -> LayerPair:
    return LayerPair(
        key=key, layer_type="Top Copper", status=status, path_a=Path("a"), path_b=Path("b")
    )


def test_identical_images_have_no_change():
    img = _image({(1, 1), (2, 2), (3, 3)})
    result = diff_layer(_pair(), img, img.copy())
    assert result.changed_pixels == 0
    assert result.common_pixels == 3
    assert result.changed is False
    assert result.overlay_png is not None


def test_added_and_removed_pixels_counted():
    image_a = _image({(1, 1), (5, 5)})  # (5,5) only in A -> removed
    image_b = _image({(1, 1), (8, 8)})  # (8,8) only in B -> added
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
    assert result.changed is True


def test_diff_layer_both_sides_none_is_error():
    result = diff_layer(_pair(), None, None)
    assert result.error is not None
    assert "no image" in result.error.lower()


def test_threshold_controls_ink_detection():
    image_a = _image(set())
    arr = np.zeros((10, 10), dtype=np.uint8)
    arr[0, 0] = 50  # dim pixel
    image_b = Image.fromarray(arr, mode="L")
    assert diff_layer(_pair(), image_a, image_b, threshold=10).added_pixels == 1
    assert diff_layer(_pair(), image_a, image_b, threshold=200).added_pixels == 0


def test_presence_mask_luminance_threshold():
    img = Image.fromarray(np.array([[0, 50, 255]], dtype=np.uint8), mode="L")
    assert presence_mask(img, threshold=10).tolist() == [[False, True, True]]
    assert presence_mask(img, threshold=200).tolist() == [[False, False, True]]


def test_presence_mask_rgba_black_is_absent():
    rgba = Image.fromarray(np.zeros((1, 3, 4), dtype=np.uint8), mode="RGBA")
    assert presence_mask(rgba, threshold=10).tolist() == [[False, False, False]]


def test_diff_masks_pads_to_common_size():
    a = np.array([[True, False]])  # 1x2
    b = np.array([[True], [True]])  # 2x1
    added, removed, common = diff_masks(a, b)
    assert added.shape == removed.shape == common.shape == (2, 2)
    assert bool(common[0, 0]) is True


def test_overlay_image_uses_expected_colours():
    added = np.array([[True, False, False]])
    removed = np.array([[False, True, False]])
    common = np.array([[False, False, True]])
    px = np.asarray(overlay_image(added, removed, common))
    assert tuple(px[0, 0]) == COLOR_ADDED
    assert tuple(px[0, 1]) == COLOR_REMOVED
    assert tuple(px[0, 2]) == COLOR_COMMON


def test_png_bytes_has_png_signature():
    assert png_bytes(Image.new("RGB", (2, 2)))[:8] == b"\x89PNG\r\n\x1a\n"


def test_overlay_background_is_filled():
    from gerberdiff.diff import COLOR_BACKGROUND

    blank = np.zeros((2, 2), dtype=bool)
    px = np.asarray(overlay_image(blank, blank, blank))
    assert tuple(px[0, 0]) == COLOR_BACKGROUND


def test_png_bytes_roundtrips_to_overlay_colour():
    import io

    img = overlay_image(np.array([[True]]), np.array([[False]]), np.array([[False]]))
    reloaded = Image.open(io.BytesIO(png_bytes(img)))
    assert reloaded.size == (1, 1)
    assert tuple(np.asarray(reloaded.convert("RGB"))[0, 0]) == COLOR_ADDED


def test_diff_layer_is_deterministic():
    a = _image({(1, 1), (5, 5)})
    b = _image({(1, 1), (8, 8)})
    first = diff_layer(_pair(), a, b)
    second = diff_layer(_pair(), a.copy(), b.copy())
    assert first.overlay_png == second.overlay_png
    assert (first.added_pixels, first.removed_pixels) == (
        second.added_pixels,
        second.removed_pixels,
    )
