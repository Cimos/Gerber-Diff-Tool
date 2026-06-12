"""Render Gerber/Excellon files to raster images and align two revisions.

Gerber rendering uses pygerber's native Pillow raster backend (no cairo / no
system libraries); its ``get_info()`` provides each file's bounding box in
millimetres, so the bbox and the rendered pixels come from one source and line
up exactly. **Excellon drill files** (which pygerber cannot parse) are detected
by their ``M48`` header and rasterised directly: gerbonara parses the hits and
each hole is drawn as a filled circle at its tool diameter. Two revisions are
composited onto the union of their bounding boxes before being diffed; the
per-file bounding boxes are also surfaced so callers can detect when two
revisions aren't co-registered. Imports are deferred so the rest of the package
stays importable without a renderer present.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

BBox = tuple[float, float, float, float]  # (min_x, min_y, max_x, max_y) in mm

# Cap on rendered pixels per layer (width x height). At 16 MP a 250x200 mm board
# still renders at ~17.8 dpmm (0.056 mm/px — well under a 0.1 mm trace), while a
# huge panel no longer multiplies every downstream cost (raster, masks, encode,
# report size) without bound. 0 disables the cap.
DEFAULT_MAX_PIXELS = 16_000_000


def effective_dpmm(frame: BBox, dpmm: int, max_pixels: int) -> int:
    """The dpmm to actually rasterise at so the frame stays under *max_pixels*."""
    if max_pixels <= 0:
        return int(dpmm)
    width_mm = max(frame[2] - frame[0], 1e-3)
    height_mm = max(frame[3] - frame[1], 1e-3)
    cap = int((max_pixels / (width_mm * height_mm)) ** 0.5)
    return max(1, min(int(dpmm), cap))


@dataclass
class Rendered:
    image: Image.Image  # RGBA: transparent background, bright geometry
    bbox_mm: BBox
    note: str | None = None  # non-fatal renderer caveat (e.g. slots skipped)


@dataclass
class AlignedPair:
    """Two revisions of one layer, composited onto a shared coordinate frame."""

    image_a: Image.Image | None
    image_b: Image.Image | None
    bbox_a: BBox | None
    bbox_b: BBox | None
    note: str | None = None

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


@dataclass
class _Prepared:
    """A parsed layer that can be rasterised at any dpmm without re-parsing.

    Parsing dominates render cost (pyparsing grammar — seconds per MB), so
    :func:`render_aligned_pair` parses both sides first, picks one effective
    dpmm from the union bbox, then rasterises. The raster callable closes over
    the parsed document.
    """

    raster: Callable[[int], Image.Image]
    bbox_mm: BBox
    note: str | None = None


def _prepare_gerber(path: Path) -> _Prepared:
    from pygerber.gerberx3.api.v2 import GerberFile, ImageFormatEnum, PixelFormatEnum

    parsed = GerberFile.from_file(str(path)).parse()
    info = parsed.get_info()
    bbox: BBox = (
        float(info.min_x_mm),
        float(info.min_y_mm),
        float(info.max_x_mm),
        float(info.max_y_mm),
    )

    def raster(dpmm: int) -> Image.Image:
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
        return image.convert("RGBA")

    return _Prepared(raster=raster, bbox_mm=bbox)


def render_gerber(path: Path, *, dpmm: int = 20) -> Rendered:
    """Render one Gerber/drill file to an RGBA image at *dpmm* dots per mm."""
    prepared = _prepare_gerber(path)
    return Rendered(image=prepared.raster(dpmm), bbox_mm=prepared.bbox_mm)


def looks_like_excellon(path: Path) -> bool:
    """Cheap content sniff: Excellon programs open with an ``M48`` header."""
    try:
        with path.open("r", errors="replace") as handle:
            head = handle.read(2048)  # header only — never the whole multi-MB file
    except OSError:
        return False
    return any(line.strip().startswith("M48") for line in head.splitlines())


def _prepare_excellon(path: Path) -> _Prepared:
    import warnings

    from gerbonara import ExcellonFile
    from gerbonara.utils import MM

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # tolerate fab-house header quirks
        excellon = ExcellonFile.open(str(path))
        flashes = [flash.converted(MM) for flash in excellon.drills()]
        n_slots = sum(1 for _ in excellon.slots())
        (min_x, min_y), (max_x, max_y) = excellon.bounding_box(unit="mm")

    if not flashes:
        raise ValueError("no drill hits found in Excellon file")

    bbox: BBox = (float(min_x), float(min_y), float(max_x), float(max_y))

    def raster(dpmm: int) -> Image.Image:
        width = max(1, round((bbox[2] - bbox[0]) * dpmm))
        height = max(1, round((bbox[3] - bbox[1]) * dpmm))
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        for flash in flashes:
            cx = (flash.x - bbox[0]) * dpmm
            cy = (bbox[3] - flash.y) * dpmm  # gerber Y grows up; image Y grows down
            radius = (flash.tool.diameter / 2) * dpmm
            draw.ellipse(
                [cx - radius, cy - radius, cx + radius, cy + radius], fill=(255, 255, 255, 255)
            )
        return image

    note = f"{n_slots} routed slot(s) in this drill file are not rendered" if n_slots else None
    return _Prepared(raster=raster, bbox_mm=bbox, note=note)


def render_excellon(path: Path, *, dpmm: int = 20) -> Rendered:
    """Rasterise an Excellon drill file: each hit becomes a filled circle.

    gerbonara does the parsing (pygerber has no Excellon support). Routed slots
    are not yet drawn — when present, the count is surfaced as a note so the
    omission is never silent.
    """
    prepared = _prepare_excellon(path)
    return Rendered(image=prepared.raster(dpmm), bbox_mm=prepared.bbox_mm, note=prepared.note)


def _prepare_layer(path: Path) -> _Prepared:
    if looks_like_excellon(path):
        return _prepare_excellon(path)
    return _prepare_gerber(path)


def render_layer(path: Path, *, dpmm: int = 20) -> Rendered:
    """Render any supported fabrication file: Excellon via gerbonara, else pygerber."""
    prepared = _prepare_layer(path)
    return Rendered(image=prepared.raster(dpmm), bbox_mm=prepared.bbox_mm, note=prepared.note)


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


def render_aligned_pair(
    path_a: Path | None,
    path_b: Path | None,
    *,
    dpmm: int = 20,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> AlignedPair:
    """Render both revisions onto the union of their bounding boxes.

    Both sides parse first (the expensive step), then rasterise at one shared
    effective dpmm chosen so the union frame stays under *max_pixels* — a very
    large board no longer produces an unboundedly large raster. When the cap
    bites, the note says so.
    """
    prep_a = _prepare_layer(path_a) if path_a else None
    prep_b = _prepare_layer(path_b) if path_b else None

    present = [p for p in (prep_a, prep_b) if p is not None]
    if not present:
        return AlignedPair(None, None, None, None)

    frame: BBox = (
        min(p.bbox_mm[0] for p in present),
        min(p.bbox_mm[1] for p in present),
        max(p.bbox_mm[2] for p in present),
        max(p.bbox_mm[3] for p in present),
    )
    eff_dpmm = effective_dpmm(frame, dpmm, max_pixels)
    notes = [p.note for p in present if p.note]
    if eff_dpmm < dpmm:
        notes.append(
            f"resolution capped at {eff_dpmm} dpmm for this board size "
            f"(requested {dpmm}; raise the max-pixels limit to override)"
        )
    rendered_a = Rendered(prep_a.raster(eff_dpmm), prep_a.bbox_mm) if prep_a else None
    rendered_b = Rendered(prep_b.raster(eff_dpmm), prep_b.bbox_mm) if prep_b else None
    return AlignedPair(
        image_a=_compose_on(frame, rendered_a, eff_dpmm) if rendered_a else None,
        image_b=_compose_on(frame, rendered_b, eff_dpmm) if rendered_b else None,
        bbox_a=rendered_a.bbox_mm if rendered_a else None,
        bbox_b=rendered_b.bbox_mm if rendered_b else None,
        note="; ".join(dict.fromkeys(notes)) if notes else None,
    )


def render_pair_aligned(
    path_a: Path | None, path_b: Path | None, *, dpmm: int = 20
) -> tuple[Image.Image | None, Image.Image | None]:
    """Backwards-compatible helper returning just the aligned ``(image_a, image_b)``."""
    pair = render_aligned_pair(path_a, path_b, dpmm=dpmm)
    return pair.image_a, pair.image_b
