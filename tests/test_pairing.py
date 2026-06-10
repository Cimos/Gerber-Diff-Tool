"""Unit tests for layer pairing and classification (no renderer required)."""

from __future__ import annotations

from pathlib import Path

from gerberdiff.models import PairStatus
from gerberdiff.pairing import classify_layer, iter_gerber_files, pair_layers


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


def test_pairing_matched_added_removed(tmp_path: Path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    (old / "x-F_Cu.gbr").write_text("G04*\nM02*\n")
    (new / "x-F_Cu.gbr").write_text("G04*\nM02*\n")
    (old / "x-B_Cu.gbr").write_text("G04*\nM02*\n")  # only in old -> removed
    (new / "x-F_Mask.gbr").write_text("G04*\nM02*\n")  # only in new -> added

    pairs = {p.key: p for p in pair_layers(old, new)}
    assert pairs["x-f_cu.gbr"].status is PairStatus.MATCHED
    assert pairs["x-b_cu.gbr"].status is PairStatus.REMOVED
    assert pairs["x-f_mask.gbr"].status is PairStatus.ADDED
