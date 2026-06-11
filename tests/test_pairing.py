"""Unit tests for layer pairing and classification."""

from __future__ import annotations

from pathlib import Path

import pytest

from gerberdiff.models import PairStatus
from gerberdiff.pairing import classify_layer, iter_gerber_files, pair_layers

# Minimal but valid single-flash gerber, enough for gerbonara to parse.
_MIN_GERBER = (
    "G04 minimal*\n%FSLAX46Y46*%\n%MOMM*%\n%ADD10C,1.000*%\nD10*\nX1000000Y1000000D03*\nM02*\n"
)
_MIN_DRILL = "M48\nMETRIC\nT1C0.800\n%\nT1\nX1.0Y1.0\nM30\n"


def test_classify_common_layers():
    assert classify_layer("board-F_Cu.gbr") == "Top Copper"
    assert classify_layer("board-B_Cu.gbr") == "Bottom Copper"
    assert classify_layer("board-F_Mask.gbr") == "Top Soldermask"
    assert classify_layer("board.gtl") == "Top Copper"
    assert classify_layer("board.gbl") == "Bottom Copper"
    assert classify_layer("board.drl") == "Drill"
    assert classify_layer("mystery.gbr") == "Unknown layer"


def test_classify_all_rule_branches():
    assert classify_layer("brd-B_Mask.gbr") == "Bottom Soldermask"
    assert classify_layer("brd-F_Silkscreen.gbr") == "Top Silkscreen"
    assert classify_layer("brd-B_SilkS.gbr") == "Bottom Silkscreen"
    assert classify_layer("brd-F_Paste.gbr") == "Top Paste"
    assert classify_layer("brd-B_Paste.gbr") == "Bottom Paste"
    assert classify_layer("brd-In1_Cu.gbr") == "Inner Copper"
    assert classify_layer("brd-Edge_Cuts.gbr") == "Board Outline"
    assert classify_layer("brd.gko") == "Board Outline"
    assert classify_layer("brd.xln") == "Drill"


def test_iter_filters_non_gerber(tmp_path: Path):
    (tmp_path / "a-F_Cu.gbr").write_text("G04*\nM02*\n")
    (tmp_path / "README.md").write_text("not a gerber")
    assert [p.name for p in iter_gerber_files(tmp_path)] == ["a-F_Cu.gbr"]


def test_iter_gerber_files_raises_on_missing_dir(tmp_path: Path):
    with pytest.raises(NotADirectoryError):
        iter_gerber_files(tmp_path / "nope")


def test_iter_gerber_files_raises_on_a_file(tmp_path: Path):
    f = tmp_path / "x.gbr"
    f.write_text("")
    with pytest.raises(NotADirectoryError):
        iter_gerber_files(f)


def test_pair_layers_empty_dirs(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert pair_layers(a, b) == []


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
        (rev_b / f"beta-{layer}.gbr").write_text(_MIN_GERBER)  # ...renamed "beta"

    pairs = {p.key: p for p in pair_layers(rev_a, rev_b)}
    assert "top copper" in pairs, f"semantic pairing did not run; keys={sorted(pairs)}"
    top = pairs["top copper"]
    assert top.status is PairStatus.MATCHED
    assert top.layer_type == "Top Copper"
    assert top.path_a is not None and top.path_a.name == "alpha-F_Cu.gbr"
    assert top.path_b is not None and top.path_b.name == "beta-F_Cu.gbr"


def test_pairing_hybrid_semantic_plus_filename_leftover(tmp_path: Path):
    """gerbonara handles the standard layers; an extra drill file falls back to filename."""
    pytest.importorskip("gerbonara")
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    for layer in ["F_Cu", "B_Cu", "F_Mask", "B_Mask", "F_Silkscreen", "B_Silkscreen", "Edge_Cuts"]:
        (a / f"brd-{layer}.gbr").write_text(_MIN_GERBER)
        (b / f"brd-{layer}.gbr").write_text(_MIN_GERBER)
    (a / "brd.drl").write_text(_MIN_DRILL)
    (b / "brd.drl").write_text(_MIN_DRILL)

    keys = {p.key for p in pair_layers(a, b)}
    assert "top copper" in keys  # semantic (gerbonara)
    assert "brd.drl" in keys  # filename leftover
