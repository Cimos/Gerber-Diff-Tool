"""Pixel-diff two aligned raster layers and build a red/green/grey overlay.

This module is renderer-agnostic: it operates on :class:`PIL.Image.Image`
objects that are assumed to already share a coordinate frame (alignment is
handled in :mod:`gerberdiff.render`). It therefore unit-tests with plain
synthetic images and never needs a Gerber renderer present.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from .models import LayerDiff, LayerPair

# Overlay colours, RGB.
COLOR_BACKGROUND = (18, 18, 18)
COLOR_COMMON = (110, 110, 110)   # ink present in both revisions
COLOR_ADDED = (40, 200, 60)      # present in B (new), absent in A  -> green
COLOR_REMOVED = (220, 50, 50)    # present in A (old), absent in B  -> red


def presence_mask(image: Image.Image, threshold: int) -> np.ndarray:
    """Boolean mask of 'ink present' pixels for a rendered layer.

    A pixel counts as ink if its luminance exceeds *threshold*, which assumes
    layers are rendered light-on-dark (the pygerber default we use).
    """
    arr = np.asarray(image.convert("L"))
    return arr > threshold


def _pad_to(mask: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Pad a mask up to *size* (height, width), anchored top-left."""
    h, w = mask.shape
    height, width = size
    if (h, w) == (height, width):
        return mask
    out = np.zeros((height, width), dtype=bool)
    out[:h, :w] = mask
    return out


def diff_masks(
    mask_a: np.ndarray, mask_b: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (added, removed, common) boolean masks for A=old, B=new."""
    height = max(mask_a.shape[0], mask_b.shape[0])
    width = max(mask_a.shape[1], mask_b.shape[1])
    a = _pad_to(mask_a, (height, width))
    b = _pad_to(mask_b, (height, width))
    return (b & ~a), (a & ~b), (a & b)


def overlay_image(
    added: np.ndarray, removed: np.ndarray, common: np.ndarray
) -> Image.Image:
    """Compose the three masks into a single RGB overlay image."""
    height, width = added.shape
    rgb = np.empty((height, width, 3), dtype=np.uint8)
    rgb[:] = COLOR_BACKGROUND
    rgb[common] = COLOR_COMMON
    rgb[added] = COLOR_ADDED
    rgb[removed] = COLOR_REMOVED
    return Image.fromarray(rgb, mode="RGB")


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def diff_layer(
    pair: LayerPair,
    image_a: Image.Image | None,
    image_b: Image.Image | None,
    *,
    threshold: int = 10,
) -> LayerDiff:
    """Diff two aligned images. Either side may be ``None`` (added/removed layer)."""
    sizes = [im.size for im in (image_a, image_b) if im is not None]
    if not sizes:
        return LayerDiff(pair=pair, error="no image rendered on either side")

    width = max(w for (w, _h) in sizes)
    height = max(h for (_w, h) in sizes)
    blank = np.zeros((height, width), dtype=bool)

    mask_a = presence_mask(image_a, threshold) if image_a is not None else blank
    mask_b = presence_mask(image_b, threshold) if image_b is not None else blank

    added, removed, common = diff_masks(mask_a, mask_b)
    return LayerDiff(
        pair=pair,
        width=width,
        height=height,
        added_pixels=int(added.sum()),
        removed_pixels=int(removed.sum()),
        common_pixels=int(common.sum()),
        overlay_png=png_bytes(overlay_image(added, removed, common)),
    )
