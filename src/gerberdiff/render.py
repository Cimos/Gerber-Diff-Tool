"""Render Gerber files to raster images and align two revisions for diffing.

Rendering uses pygerber's native Pillow raster backend (no cairo / no system
libraries). pygerber's own ``get_info()`` provides each file's bounding box in
millimetres, so the bbox and the rendered pixels come from one source and line
up exactly. Two revisions are composited onto the union of their bounding boxes
before being diffed; the per-file bounding boxes are also surfaced so callers
can detect when two revisions aren't co-registered. Imports are deferred so the
rest of the package stays importable without a renderer present.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image

BBox = tuple[float, float, float, float]  # (min_x, min_y, max_x, max_y) in mm


@dataclass
class Rendered:
    image: Image.Image  # RGBA: opaque-black background, coloured geometry
    bbox_mm: BBox


@dataclass
class AlignedPair:
    """Two revisions of one layer, composited onto a shared coordinate frame."""

    image_a: Image.Image | None
    image_b: Image.Image | None
    bbox_a: BBox | None
    bbox_b: BBox | None

    @property
    def co_registered(self) -> bool:
        """False only for a *pure shift*: same-size bounding box, moved origin.

        A one-sided layer (added/removed) has nothing to mis-register. A genuine
        feature move/add usually changes the extent (box size), which we do NOT
        flag — that's a real diff. But a board whose box is the *same size* yet
        sits at a different origin was exported on a different datum, and the
        top-left alignment here would paint that benign shift as a full-layer
        change — exactly the case worth warning about.
        """
        if self.bbox_a is None or self.bbox_b is None:
            return True
        ax0, ay0, ax1, ay1 = self.bbox_a
        bx0, by0, bx1, by1 = self.bbox_b
        same_size = (
            abs((ax1 - ax0) - (bx1 - bx0)) <= 0.05 and abs((ay1 - ay0) - (by1 - by0)) <= 0.05
        )
        shifted = abs(ax0 - bx0) > 0.05 or abs(ay0 - by0) > 0.05
        return not (same_size and shifted)


def render_gerber(path: Path, *, dpmm: int = 20) -> Rendered:
    """Render one Gerber/drill file to an RGBA image at *dpmm* dots per mm."""
    from pygerber.gerberx3.api.v2 import GerberFile, ImageFormatEnum, PixelFormatEnum

    parsed = GerberFile.from_file(str(path)).parse()
    info = parsed.get_info()
    bbox: BBox = (
        float(info.min_x_mm),
        float(info.min_y_mm),
        float(info.max_x_mm),
        float(info.max_y_mm),
    )
    buffer = BytesIO()
    # image_format must be explicit: with AUTO, pygerber infers from the
    # destination's file extension, which a BytesIO does not have.
    parsed.render_raster(
        buffer,
        dpmm=int(dpmm),
        image_format=ImageFormatEnum.PNG,
        pixel_format=PixelFormatEnum.RGBA,
    )
    buffer.seek(0)
    image = Image.open(buffer)
    image.load()
    return Rendered(image=image.convert("RGBA"), bbox_mm=bbox)


def _compose_on(frame: BBox, rendered: Rendered, dpmm: int) -> Image.Image:
    """Paste *rendered* onto a transparent canvas spanning *frame* at *dpmm*.

    Gerber Y grows upward while image Y grows downward, so the vertical offset is
    measured from the top of the frame down to the top of this layer's bbox.
    """
    f_min_x, _f_min_y, _f_max_x, f_max_y = frame
    width = max(1, round((frame[2] - frame[0]) * dpmm))
    height = max(1, round((frame[3] - frame[1]) * dpmm))
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    b_min_x, _b_min_y, _b_max_x, b_max_y = rendered.bbox_mm
    offset_x = round((b_min_x - f_min_x) * dpmm)
    offset_y = round((f_max_y - b_max_y) * dpmm)
    canvas.alpha_composite(rendered.image, dest=(max(0, offset_x), max(0, offset_y)))
    return canvas


def render_aligned_pair(path_a: Path | None, path_b: Path | None, *, dpmm: int = 20) -> AlignedPair:
    """Render both revisions onto the union of their bounding boxes."""
    rendered_a = render_gerber(path_a, dpmm=dpmm) if path_a else None
    rendered_b = render_gerber(path_b, dpmm=dpmm) if path_b else None

    present = [r for r in (rendered_a, rendered_b) if r is not None]
    if not present:
        return AlignedPair(None, None, None, None)

    frame: BBox = (
        min(r.bbox_mm[0] for r in present),
        min(r.bbox_mm[1] for r in present),
        max(r.bbox_mm[2] for r in present),
        max(r.bbox_mm[3] for r in present),
    )
    return AlignedPair(
        image_a=_compose_on(frame, rendered_a, dpmm) if rendered_a else None,
        image_b=_compose_on(frame, rendered_b, dpmm) if rendered_b else None,
        bbox_a=rendered_a.bbox_mm if rendered_a else None,
        bbox_b=rendered_b.bbox_mm if rendered_b else None,
    )


def render_pair_aligned(
    path_a: Path | None, path_b: Path | None, *, dpmm: int = 20
) -> tuple[Image.Image | None, Image.Image | None]:
    """Backwards-compatible helper returning just the aligned ``(image_a, image_b)``."""
    pair = render_aligned_pair(path_a, path_b, dpmm=dpmm)
    return pair.image_a, pair.image_b
