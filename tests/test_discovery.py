"""Tests for fab-data-pack discovery (flat / wrapped / nested / Altium / zip)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from gerberdiff.discovery import (
    GerberSourceError,
    extract_flat,
    locate_gerber_dir,
    merge_into_tempdir,
)


def _gerbers(d: Path, n: int, ext: str = ".gbr", stem: str = "layer") -> None:
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (d / f"{stem}{i}{ext}").write_text("G04*\nM02*\n")


def test_flat_folder_returned_as_is(tmp_path: Path):
    _gerbers(tmp_path, 4)
    chosen, drill = locate_gerber_dir(tmp_path)
    assert chosen == tmp_path
    assert drill is None


def test_flat_folder_two_files_still_works(tmp_path: Path):
    # Regression: the bundled fixtures hold only 2 layers — must not be rejected.
    _gerbers(tmp_path, 2)
    chosen, _ = locate_gerber_dir(tmp_path)
    assert chosen == tmp_path


def test_single_wrapper_subdir(tmp_path: Path):
    board = tmp_path / "GERBER-myboard"
    _gerbers(board, 5)
    chosen, _ = locate_gerber_dir(tmp_path)
    assert chosen == board


def test_deeply_nested(tmp_path: Path):
    deep = tmp_path / "outputs" / "gerbers"
    _gerbers(deep, 4)
    chosen, _ = locate_gerber_dir(tmp_path)
    assert chosen == deep


def test_clutter_does_not_fool_scoring(tmp_path: Path):
    board = tmp_path / "fab"
    _gerbers(board, 4)
    (board / "README.txt").write_text("notes")  # .txt excluded from scoring
    (board / "bom.csv").write_text("a,b")
    chosen, _ = locate_gerber_dir(tmp_path)
    assert chosen == board


def test_multiple_boards_is_ambiguous(tmp_path: Path):
    _gerbers(tmp_path / "boardA", 4)
    _gerbers(tmp_path / "boardB", 4)
    with pytest.raises(GerberSourceError, match="more than one board"):
        locate_gerber_dir(tmp_path)


def test_altium_sibling_drill_is_returned(tmp_path: Path):
    wrap = tmp_path / "Project Outputs"
    gerber = wrap / "Gerber"
    _gerbers(gerber, 5)
    drill = wrap / "NC Drill"
    drill.mkdir(parents=True)
    (drill / "board.drl").write_text("M48\nM30\n")
    chosen, drill_dir = locate_gerber_dir(tmp_path)
    assert chosen == gerber
    assert drill_dir == drill


def test_no_gerbers_raises(tmp_path: Path):
    (tmp_path / "README.md").write_text("nothing here")
    with pytest.raises(GerberSourceError):
        locate_gerber_dir(tmp_path)


def test_extract_flat_unpacks_nested_zip(tmp_path: Path):
    inner_src = tmp_path / "inner_src"
    _gerbers(inner_src, 4)
    inner_zip = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner_zip, "w") as z:
        for p in inner_src.iterdir():
            z.write(p, p.name)
    outer_zip = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer_zip, "w") as z:
        z.write(inner_zip, "inner.zip")

    dest = tmp_path / "extracted"
    dest.mkdir()
    extract_flat(outer_zip, dest)
    chosen, _ = locate_gerber_dir(dest)
    assert chosen.name == "inner"  # nested zip was flattened, then located


def test_sibling_drill_dir_ignores_mixed_folder(tmp_path: Path):
    # A sibling that holds drills *and* other files (notes, fab docs) is not the
    # split NC-Drill folder — only an all-drill sibling counts.
    wrap = tmp_path / "out"
    gerber = wrap / "Gerber"
    _gerbers(gerber, 4)
    mixed = wrap / "Extras"
    mixed.mkdir(parents=True)
    (mixed / "x.drl").write_text("M48\nM30\n")
    (mixed / "assembly.pdf").write_text("not a drill")
    chosen, drill_dir = locate_gerber_dir(tmp_path)
    assert chosen == gerber
    assert drill_dir is None


def test_merge_into_tempdir_combines_without_mutating_source(tmp_path: Path):
    gerber = tmp_path / "Gerber"
    _gerbers(gerber, 3)
    drill = tmp_path / "NC Drill"
    drill.mkdir()
    (drill / "board.drl").write_text("M48\nM30\n")
    dest = tmp_path / "merged"
    dest.mkdir()

    out = merge_into_tempdir(gerber, drill, dest)
    assert out == dest
    names = {p.name for p in dest.iterdir()}
    assert {"layer0.gbr", "layer1.gbr", "layer2.gbr", "board.drl"} <= names
    # source folders are never mutated
    assert (gerber / "layer0.gbr").exists()
    assert (drill / "board.drl").exists()
    assert not (gerber / "board.drl").exists()


def test_merge_into_tempdir_does_not_let_drill_clobber_a_gerber(tmp_path: Path):
    gerber = tmp_path / "g"
    gerber.mkdir()
    (gerber / "shared.drl").write_text("FROM-GERBER")
    drill = tmp_path / "d"
    drill.mkdir()
    (drill / "shared.drl").write_text("FROM-DRILL")
    dest = tmp_path / "m"
    dest.mkdir()
    merge_into_tempdir(gerber, drill, dest)
    assert (dest / "shared.drl").read_text() == "FROM-GERBER"  # gerber copied first, drill skipped


def test_materialize_merges_altium_split_pack(tmp_path: Path):
    # End-to-end wiring (no pygerber): locate the Gerber dir, find the sibling
    # NC-Drill folder, and merge both into one temp dir for the renderer.
    from contextlib import ExitStack

    from gerberdiff.runner import _materialize

    wrap = tmp_path / "Project Outputs"
    _gerbers(wrap / "Gerber", 3)
    drill = wrap / "NC Drill"
    drill.mkdir(parents=True)
    (drill / "board.drl").write_text("M48\nM30\n")

    with ExitStack() as stack:
        out = _materialize(wrap, stack)
        names = {p.name for p in out.iterdir()}
    assert "board.drl" in names
    assert sum(1 for n in names if n.endswith(".gbr")) == 3


def test_run_diff_accepts_a_flat_zip(tmp_path: Path):
    pytest.importorskip("pygerber")
    from gerberdiff.runner import run_diff

    fixtures = Path(__file__).parent / "fixtures"
    zip_a = tmp_path / "revA.zip"
    with zipfile.ZipFile(zip_a, "w") as z:
        for p in (fixtures / "revA").iterdir():
            z.write(p, p.name)  # flat zip (mirrors a real fab-pack download)
    result = run_diff(zip_a, fixtures / "revB", dpmm=20)
    assert result.subject == "layer"
    assert result.any_changes  # the moved pad still diffs through the zip
