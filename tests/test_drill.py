"""Excellon drill rendering + diffing (gerbonara parse → PIL circles)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("gerbonara")

from gerberdiff.render import looks_like_excellon, render_excellon, render_layer  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
DRILL_A = FIXTURES / "drillA" / "fixture.drl"
DRILL_B = FIXTURES / "drillB" / "fixture.drl"


def test_looks_like_excellon():
    assert looks_like_excellon(DRILL_A) is True
    assert looks_like_excellon(FIXTURES / "revA" / "fixture-F_Cu.gbr") is False
    assert looks_like_excellon(FIXTURES / "nope.drl") is False  # missing file


def test_render_excellon_geometry():
    rendered = render_excellon(DRILL_A, dpmm=20)
    # Two 0.6 mm holes at (1,1) and (5,1) -> bbox 0.7..5.3 x 0.7..1.3 mm.
    min_x, min_y, max_x, max_y = rendered.bbox_mm
    assert round(min_x, 1) == 0.7
    assert round(max_x, 1) == 5.3
    assert round(min_y, 1) == 0.7
    assert round(max_y, 1) == 1.3
    assert rendered.image.mode == "RGBA"
    assert rendered.note is None  # no slots in the fixture
    # Some ink must have been drawn.
    assert rendered.image.getbbox() is not None


def test_render_layer_routes_drl_to_excellon():
    rendered = render_layer(DRILL_A, dpmm=20)
    assert rendered.bbox_mm[0] != 0 or rendered.image.getbbox() is not None


def test_drill_diff_detects_moved_hole():
    pytest.importorskip("pygerber")
    from gerberdiff.diff import diff_layer
    from gerberdiff.models import LayerPair, PairStatus
    from gerberdiff.render import render_aligned_pair

    aligned = render_aligned_pair(DRILL_A, DRILL_B, dpmm=20)
    pair = LayerPair(
        key="fixture.drl",
        layer_type="Drill",
        status=PairStatus.MATCHED,
        path_a=DRILL_A,
        path_b=DRILL_B,
    )
    diff = diff_layer(pair, aligned.image_a, aligned.image_b)
    assert diff.added_pixels > 0, "moved-to hole should appear as added"
    assert diff.removed_pixels > 0, "moved-from hole should appear as removed"
    assert diff.common_pixels > 0, "shared hole should overlap (alignment correct)"


def test_run_diff_handles_drill_dirs_without_error_layers():
    pytest.importorskip("pygerber")
    from gerberdiff.runner import run_diff

    result = run_diff(FIXTURES / "drillA", FIXTURES / "drillB", dpmm=20)
    assert len(result.layers) == 1
    layer = result.layers[0]
    assert layer.error is None  # previously: pygerber ParseException error-layer
    assert layer.changed
    assert layer.pair.layer_type == "Drill"
