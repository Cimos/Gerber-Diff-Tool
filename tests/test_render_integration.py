"""End-to-end render + align + diff on the synthetic fixtures.

These exercise the real renderer (pygerber) and bounding-box alignment; they are
skipped automatically if pygerber is absent so the pure-logic tests can still
run anywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pygerber")

from gerberdiff.diff import diff_layer  # noqa: E402
from gerberdiff.pairing import pair_layers  # noqa: E402
from gerberdiff.render import render_pair_aligned  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _pairs():
    return {p.key: p for p in pair_layers(FIXTURES / "revA", FIXTURES / "revB")}


def test_moved_pad_shows_added_removed_and_common():
    """The moved pad must register as both added and removed; the shared pad as
    common. A non-zero common count is the proof that alignment is correct."""
    pair = _pairs()["fixture-f_cu.gbr"]
    image_a, image_b = render_pair_aligned(pair.path_a, pair.path_b, dpmm=20)
    diff = diff_layer(pair, image_a, image_b)
    assert diff.added_pixels > 0, "moved-to position should appear as added"
    assert diff.removed_pixels > 0, "moved-from position should appear as removed"
    assert diff.common_pixels > 0, "shared pad should overlap (alignment correct)"


def test_identical_mask_is_unchanged():
    pair = _pairs()["fixture-f_mask.gbr"]
    image_a, image_b = render_pair_aligned(pair.path_a, pair.path_b, dpmm=20)
    diff = diff_layer(pair, image_a, image_b)
    assert diff.changed_pixels == 0
    assert diff.common_pixels > 0
