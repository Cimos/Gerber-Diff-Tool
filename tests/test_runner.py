"""Tests for the shared runner used by both the CLI and the GUI."""

from __future__ import annotations

from pathlib import Path

import pytest

from gerberdiff.runner import is_pdf, run_diff

FIXTURES = Path(__file__).parent / "fixtures"


def test_is_pdf(tmp_path: Path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert is_pdf(pdf) is True
    folder = tmp_path / "d"
    folder.mkdir()
    assert is_pdf(folder) is False
    assert is_pdf(tmp_path / "missing.pdf") is False


def test_run_diff_gerber_mode():
    pytest.importorskip("pygerber")
    result = run_diff(FIXTURES / "revA", FIXTURES / "revB", dpmm=20)
    assert result.subject == "layer"
    assert result.resolution == "20 dpmm"
    assert result.any_changes


def test_run_diff_identical_dirs_no_change():
    pytest.importorskip("pygerber")
    result = run_diff(FIXTURES / "revA", FIXTURES / "revA", dpmm=20)
    assert not result.any_changes


def test_run_diff_pdf_mode(tmp_path: Path):
    pytest.importorskip("pypdfium2")
    from PIL import Image, ImageDraw

    def make(path: Path, extra: bool) -> None:
        image = Image.new("1", (300, 200), 1)
        draw = ImageDraw.Draw(image)
        draw.rectangle([40, 40, 200, 140], outline=0, width=4)
        if extra:
            draw.line([210, 40, 270, 120], fill=0, width=5)
        image.save(str(path))

    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    make(a, extra=False)
    make(b, extra=True)
    result = run_diff(a, b, dpi=100)
    assert result.subject == "page"
    assert result.resolution == "100 dpi"
    assert result.any_changes


def test_run_diff_reports_progress():
    pytest.importorskip("pygerber")
    calls: list[tuple[int, int, str]] = []
    run_diff(
        FIXTURES / "revA",
        FIXTURES / "revB",
        dpmm=20,
        progress=lambda i, t, lbl: calls.append((i, t, lbl)),
    )
    assert calls
    assert all(total == len(calls) for (_i, total, _lbl) in calls)


def test_run_diff_rejects_mismatched_inputs(tmp_path: Path):
    folder = tmp_path / "d"
    folder.mkdir()
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert is_pdf(pdf)
    with pytest.raises(ValueError):
        run_diff(folder, pdf)


def _zip_of(folder: Path, dest: Path, *, root: str | None = None) -> Path:
    import zipfile

    with zipfile.ZipFile(dest, "w") as archive:
        for file in folder.iterdir():
            arcname = f"{root}/{file.name}" if root else file.name
            archive.write(file, arcname)
    return dest


def test_run_diff_zip_inputs(tmp_path: Path):
    pytest.importorskip("pygerber")
    zip_a = _zip_of(FIXTURES / "revA", tmp_path / "a.zip")
    zip_b = _zip_of(FIXTURES / "revB", tmp_path / "b.zip")
    result = run_diff(zip_a, zip_b, dpmm=20)
    assert result.subject == "layer"
    assert result.any_changes
    assert result.dir_a == zip_a  # report shows the zip, not the temp dir


def test_run_diff_mixed_zip_and_dir(tmp_path: Path):
    pytest.importorskip("pygerber")
    zip_a = _zip_of(FIXTURES / "revA", tmp_path / "a.zip")
    result = run_diff(zip_a, FIXTURES / "revB", dpmm=20)
    assert result.any_changes


def test_run_diff_zip_with_single_root_folder(tmp_path: Path):
    pytest.importorskip("pygerber")
    zip_a = _zip_of(FIXTURES / "revA", tmp_path / "a.zip", root="gerbers")
    zip_b = _zip_of(FIXTURES / "revB", tmp_path / "b.zip", root="gerbers")
    result = run_diff(zip_a, zip_b, dpmm=20)
    assert result.any_changes  # descended into the single top-level folder


def test_parallel_matches_serial(tmp_path: Path):
    """jobs>1 fans layers across processes; results must equal the serial run."""
    pytest.importorskip("pygerber")
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    src_a = (FIXTURES / "revA" / "fixture-F_Cu.gbr").read_text()
    src_b = (FIXTURES / "revB" / "fixture-F_Cu.gbr").read_text()
    layers = ["F_Cu", "B_Cu", "F_Mask", "B_Mask", "F_Silkscreen", "B_Silkscreen"]
    for name in layers:  # 6 layers -> crosses the >=4 parallel threshold
        (a / f"brd-{name}.gbr").write_text(src_a)
        (b / f"brd-{name}.gbr").write_text(src_b if name == "F_Cu" else src_a)

    serial = run_diff(a, b, dpmm=20, jobs=1)
    parallel = run_diff(a, b, dpmm=20, jobs=2)
    assert [lyr.pair.key for lyr in parallel.layers] == [lyr.pair.key for lyr in serial.layers]
    assert [lyr.changed_pixels for lyr in parallel.layers] == [
        lyr.changed_pixels for lyr in serial.layers
    ]
    assert [lyr.overlay_png for lyr in parallel.layers] == [
        lyr.overlay_png for lyr in serial.layers
    ]


def test_run_diff_bad_gerber_becomes_error_layer(tmp_path: Path):
    pytest.importorskip("pygerber")
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "junk.gbr").write_text("this is not a gerber file")
    (b / "junk.gbr").write_text("this is not a gerber file")
    result = run_diff(a, b, dpmm=20)
    assert len(result.layers) == 1
    assert result.layers[0].error is not None
