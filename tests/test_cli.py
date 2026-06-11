"""End-to-end CLI tests: modes, exit codes, validation, JSON output."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gerberdiff.cli import build_parser, main

FIXTURES = Path(__file__).parent / "fixtures"


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--help"])
    assert exc.value.code == 0


def test_version_prints_and_exits(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "gdiff" in capsys.readouterr().out


def test_gerber_mode_writes_report_and_json(tmp_path: Path):
    pytest.importorskip("pygerber")
    out = tmp_path / "r.html"
    js = tmp_path / "r.json"
    code = main(
        [str(FIXTURES / "revA"), str(FIXTURES / "revB"), "-o", str(out), "--json", str(js), "-q"]
    )
    assert code == 0
    assert out.exists()
    data = json.loads(js.read_text())
    assert data["subject"] == "layer"
    assert any(layer["key"] == "fixture-f_cu.gbr" and layer["changed"] for layer in data["layers"])


def test_fail_on_diff_returns_1(tmp_path: Path):
    pytest.importorskip("pygerber")
    code = main(
        [
            str(FIXTURES / "revA"),
            str(FIXTURES / "revB"),
            "-o",
            str(tmp_path / "r.html"),
            "--fail-on-diff",
            "-q",
        ]
    )
    assert code == 1


def test_identical_dirs_exit_zero_even_with_fail_on_diff(tmp_path: Path):
    pytest.importorskip("pygerber")
    code = main(
        [
            str(FIXTURES / "revA"),
            str(FIXTURES / "revA"),
            "-o",
            str(tmp_path / "r.html"),
            "--fail-on-diff",
            "-q",
        ]
    )
    assert code == 0


def test_output_creates_parent_dirs(tmp_path: Path):
    pytest.importorskip("pygerber")
    out = tmp_path / "sub" / "deep" / "r.html"
    code = main([str(FIXTURES / "revA"), str(FIXTURES / "revB"), "-o", str(out), "-q"])
    assert code == 0
    assert out.exists()


def test_pdf_mode(tmp_path: Path):
    pytest.importorskip("pypdfium2")
    from PIL import Image, ImageDraw

    def make(path: Path, extra: bool) -> None:
        image = Image.new("1", (200, 150), 1)
        draw = ImageDraw.Draw(image)
        draw.rectangle([20, 20, 150, 100], outline=0, width=3)
        if extra:
            draw.line([160, 20, 190, 90], fill=0, width=4)
        image.save(str(path))

    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    make(a, extra=False)
    make(b, extra=True)
    js = tmp_path / "r.json"
    code = main([str(a), str(b), "-o", str(tmp_path / "r.html"), "--json", str(js), "-q"])
    assert code == 0
    assert json.loads(js.read_text())["subject"] == "page"


def test_mismatched_inputs_exit_2(tmp_path: Path, capsys):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    folder = tmp_path / "d"
    folder.mkdir()
    code = main([str(folder), str(pdf), "-o", str(tmp_path / "r.html")])
    assert code == 2
    assert "both" in capsys.readouterr().err


def test_nonexistent_paths_exit_2(tmp_path: Path):
    code = main(
        [str(tmp_path / "nope_a"), str(tmp_path / "nope_b"), "-o", str(tmp_path / "r.html")]
    )
    assert code == 2


def test_empty_dirs_exit_2(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    code = main([str(a), str(b), "-o", str(tmp_path / "r.html")])
    assert code == 2


def test_invalid_resolution_exit_2(tmp_path: Path, capsys):
    code = main(
        [
            str(FIXTURES / "revA"),
            str(FIXTURES / "revB"),
            "--dpmm",
            "0",
            "-o",
            str(tmp_path / "r.html"),
        ]
    )
    assert code == 2
    assert "dpmm" in capsys.readouterr().err


def test_invalid_threshold_exit_2(tmp_path: Path):
    code = main(
        [
            str(FIXTURES / "revA"),
            str(FIXTURES / "revB"),
            "--threshold",
            "999",
            "-o",
            str(tmp_path / "r.html"),
        ]
    )
    assert code == 2


def test_invalid_dpi_exit_2(tmp_path: Path):
    code = main(
        [
            str(FIXTURES / "revA"),
            str(FIXTURES / "revB"),
            "--dpi",
            "0",
            "-o",
            str(tmp_path / "r.html"),
        ]
    )
    assert code == 2
