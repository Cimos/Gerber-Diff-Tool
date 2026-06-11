"""Pixel-diff two aligned raster layers and build a colour + pattern overlay.

Renderer-agnostic: operates on :class:`PIL.Image.Image` objects assumed to share
a coordinate frame (alignment is handled in :mod:`gerberdiff.render`). The diff
encoding is colour-blind-safe: **added = blue, removed = orange**, and removed is
additionally **hatched** so the two classes stay distinguishable in greyscale and
for monochromacy (no reliance on hue alone).
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageDraw

from .models import LayerDiff, LayerPair

# Overlay colours, RGB. Blue/orange is the most colour-blind-safe diverging pair.
COLOR_BACKGROUND = (18, 18, 18)
COLOR_COMMON = (88, 88, 88)  # ink present in both revisions -> dark grey
COLOR_ADDED = (56, 135, 255)  # present in B (new), absent in A -> blue, solid
COLOR_REMOVED = (255, 140, 0)  # present in A (old), absent in B -> orange, hatched
COLOR_REMOVED_HATCH = (150, 78, 0)  # darker-orange stripes -> redundant texture channel
COLOR_MARKER = (120, 180, 255)  # changed-region marker outline


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


def diff_masks(mask_a: np.ndarray, mask_b: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (added, removed, common) boolean masks for A=old, B=new."""
    height = max(mask_a.shape[0], mask_b.shape[0])
    width = max(mask_a.shape[1], mask_b.shape[1])
    a = _pad_to(mask_a, (height, width))
    b = _pad_to(mask_b, (height, width))
    return (b & ~a), (a & ~b), (a & b)


def overlay_image(added: np.ndarray, removed: np.ndarray, common: np.ndarray) -> Image.Image:
    """Compose the masks into an RGB overlay.

    added = solid blue, removed = orange with a diagonal hatch, common = grey.
    The hatch is the redundant non-colour channel that keeps add vs remove
    distinguishable without relying on hue.
    """
    height, width = added.shape
    rgb = np.empty((height, width, 3), dtype=np.uint8)
    rgb[:] = COLOR_BACKGROUND
    rgb[common] = COLOR_COMMON
    rgb[added] = COLOR_ADDED
    rgb[removed] = COLOR_REMOVED
    yy, xx = np.indices((height, width))
    hatch = ((xx + yy) % 8) < 3  # diagonal bands
    rgb[removed & hatch] = COLOR_REMOVED_HATCH
    return Image.fromarray(rgb, mode="RGB")


def bbox_of(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Bounding box (x0, y0, x1, y1) of True pixels, or None if the mask is empty."""
    rows = np.any(mask, axis=1)
    if not rows.any():
        return None
    cols = np.any(mask, axis=0)
    y0, y1 = np.where(rows)[0][[0, -1]]
    x0, x1 = np.where(cols)[0][[0, -1]]
    return (int(x0), int(y0), int(x1), int(y1))


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _padded_rgb(image: Image.Image, width: int, height: int) -> Image.Image:
    canvas = Image.new("RGB", (width, height), COLOR_BACKGROUND)
    canvas.paste(image.convert("RGB"), (0, 0))
    return canvas


def diff_layer(
    pair: LayerPair,
    image_a: Image.Image | None,
    image_b: Image.Image | None,
    *,
    threshold: int = 10,
    dpmm: float | None = None,
) -> LayerDiff:
    """Diff two aligned images. Either side may be ``None`` (added/removed layer).

    Draws a marker around the changed region on the overlay, and — for layers
    that actually changed — captures the two source rasters so the report can
    offer side-by-side / swipe views.
    """
    sizes = [im.size for im in (image_a, image_b) if im is not None]
    if not sizes:
        return LayerDiff(pair=pair, error="no image rendered on either side")

    width = max(w for (w, _h) in sizes)
    height = max(h for (_w, h) in sizes)
    blank = np.zeros((height, width), dtype=bool)
    mask_a = presence_mask(image_a, threshold) if image_a is not None else blank
    mask_b = presence_mask(image_b, threshold) if image_b is not None else blank

    added, removed, common = diff_masks(mask_a, mask_b)
    overlay = overlay_image(added, removed, common)

    changed_bbox = bbox_of(added | removed)
    changed_size_mm = None
    if changed_bbox is not None:
        x0, y0, x1, y1 = changed_bbox
        margin = 2
        ImageDraw.Draw(overlay).rectangle(
            [
                max(0, x0 - margin),
                max(0, y0 - margin),
                min(width - 1, x1 + margin),
                min(height - 1, y1 + margin),
            ],
            outline=COLOR_MARKER,
            width=1,
        )
        if dpmm:
            changed_size_mm = ((x1 - x0 + 1) / dpmm, (y1 - y0 + 1) / dpmm)

    diff = LayerDiff(
        pair=pair,
        width=width,
        height=height,
        added_pixels=int(added.sum()),
        removed_pixels=int(removed.sum()),
        common_pixels=int(common.sum()),
        overlay_png=png_bytes(overlay),
        changed_bbox=changed_bbox,
        changed_size_mm=changed_size_mm,
    )
    if diff.changed:
        if image_a is not None:
            diff.image_a_png = png_bytes(_padded_rgb(image_a, width, height))
        if image_b is not None:
            diff.image_b_png = png_bytes(_padded_rgb(image_b, width, height))
    return diff
