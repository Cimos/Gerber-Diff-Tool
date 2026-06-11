"""Render + alignment tests (exercise pygerber; skipped if it is absent)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pygerber")

from PIL import Image  # noqa: E402

from gerberdiff.render import (  # noqa: E402
    Rendered,
    _compose_on,
    render_gerber,
    render_pair_aligned,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_render_gerber_returns_rgba_and_correct_bbox():
    rendered = render_gerber(FIXTURES / "revA" / "fixture-F_Cu.gbr", dpmm=20)
    assert rendered.image.mode == "RGBA"
    # Fixture: 1 mm pads at (1,1) and (5,1) -> bbox 0.5..5.5 x 0.5..1.5 mm.
    min_x, min_y, max_x, max_y = rendered.bbox_mm
    assert round(min_x, 1) == 0.5
    assert round(max_x, 1) == 5.5
    assert round(min_y, 1) == 0.5
    assert round(max_y, 1) == 1.5


def test_render_gerber_resolution_scales_image():
    low = render_gerber(FIXTURES / "revA" / "fixture-F_Cu.gbr", dpmm=10)
    high = render_gerber(FIXTURES / "revA" / "fixture-F_Cu.gbr", dpmm=40)
    assert high.image.width > low.image.width


def test_compose_on_sizes_canvas_to_frame():
    img = Image.new("RGBA", (2, 2), (0, 0, 0, 255))
    rendered = Rendered(image=img, bbox_mm=(0.0, 0.0, 2.0, 2.0))
    out = _compose_on(frame=(0.0, 0.0, 2.0, 4.0), rendered=rendered, dpmm=1)
    assert out.size == (2, 4)
    assert out.mode == "RGBA"


def test_render_pair_aligned_missing_side_returns_none():
    a = FIXTURES / "revA" / "fixture-F_Cu.gbr"
    image_a, image_b = render_pair_aligned(a, None, dpmm=20)
    assert image_a is not None
    assert image_b is None


def test_render_pair_aligned_both_none():
    assert render_pair_aligned(None, None, dpmm=20) == (None, None)


def test_render_pair_aligned_same_size_for_diff():
    a = FIXTURES / "revA" / "fixture-F_Cu.gbr"
    b = FIXTURES / "revB" / "fixture-F_Cu.gbr"
    image_a, image_b = render_pair_aligned(a, b, dpmm=20)
    assert image_a is not None and image_b is not None
    assert image_a.size == image_b.size  # aligned onto the shared union frame


def test_render_pair_identical_file_has_no_diff():
    from gerberdiff.diff import diff_layer
    from gerberdiff.models import LayerPair, PairStatus

    a = FIXTURES / "revA" / "fixture-F_Cu.gbr"
    image_a, image_b = render_pair_aligned(a, a, dpmm=20)
    pair = LayerPair(key="x", layer_type="t", status=PairStatus.MATCHED, path_a=a, path_b=a)
    diff = diff_layer(pair, image_a, image_b)
    assert diff.changed_pixels == 0
    assert diff.common_pixels > 0
