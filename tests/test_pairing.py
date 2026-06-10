"""Unit tests for layer pairing and classification."""

from __future__ import annotations

from pathlib import Path

import pytest

from gerberdiff.models import PairStatus
from gerberdiff.pairing import classify_layer, iter_gerber_files, pair_layers

# Minimal but valid single-flash gerber, enough for gerbonara to parse.
_MIN_GERBER = (
    "G04 minimal*\n%FSLAX46Y46*%\n%MOMM*%\n%ADD10C,1.000*%\nD10*\n"
    "X1000000Y1000000D03*\nM02*\n"
)


def test_classify_common_layers():
    assert classify_layer("board-F_Cu.gbr") == "Top Copper"
    assert classify_layer("board-B_Cu.gbr") == "Bottom Copper"
    assert classify_layer("board-F_Mask.gbr") == "Top Soldermask"
    assert classify_layer("board.gtl") == "Top Copper"
    assert classify_layer("board.gbl") == "Bottom Copper"
    assert classify_layer("board.drl") == "Drill"
    assert classify_layer("mystery.gbr") == "Unknown layer"


def test_iter_filters_non_gerber(tmp_path: Path):
    (tmp_path / "a-F_Cu.gbr").write_text("G04*\nM02*\n")
    (tmp_path / "README.md").write_text("not a gerber")
    found = [p.name for p in iter_gerber_files(tmp_path)]
    assert found == ["a-F_Cu.gbr"]


def test_pairing_filename_fallback(tmp_path: Path):
    """Names gerbonara can't classify fall back to filename pairing."""
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    (old / "layer-a.gbr").write_text(_MIN_GERBER)
    (new / "layer-a.gbr").write_text(_MIN_GERBER)
    (old / "layer-b.gbr").write_text(_MIN_GERBER)  # only in old -> removed
    (new / "layer-c.gbr").write_text(_MIN_GERBER)  # only in new -> added

    pairs = {p.key: p for p in pair_layers(old, new)}
    assert pairs["layer-a.gbr"].status is PairStatus.MATCHED
    assert pairs["layer-b.gbr"].status is PairStatus.REMOVED
    assert pairs["layer-c.gbr"].status is PairStatus.ADDED


def test_gerbonara_semantic_pairing_survives_rename(tmp_path: Path):
    """A board renamed between revisions still pairs by layer identity."""
    pytest.importorskip("gerbonara")
    rev_a = tmp_path / "rev_a"
    rev_b = tmp_path / "rev_b"
    rev_a.mkdir()
    rev_b.mkdir()
    layers = ["F_Cu", "B_Cu", "F_Mask", "B_Mask", "F_Silkscreen", "B_Silkscreen", "Edge_Cuts"]
    for layer in layers:
        (rev_a / f"alpha-{layer}.gbr").write_text(_MIN_GERBER)  # board "alpha"
        (rev_b / f"beta-{layer}.gbr").write_text(_MIN_GERBER)   # ...renamed "beta"

    pairs = {p.key: p for p in pair_layers(rev_a, rev_b)}
    assert "top copper" in pairs, f"semantic pairing did not run; keys={sorted(pairs)}"
    top = pairs["top copper"]
    assert top.status is PairStatus.MATCHED
    assert top.layer_type == "Top Copper"
    assert top.path_a is not None and top.path_a.name == "alpha-F_Cu.gbr"
    assert top.path_b is not None and top.path_b.name == "beta-F_Cu.gbr"
