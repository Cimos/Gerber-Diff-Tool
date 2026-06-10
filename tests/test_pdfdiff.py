"""Tests for the PDF (schematic) diff path."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pypdfium2")

from PIL import Image, ImageDraw  # noqa: E402

from gerberdiff.pdfdiff import diff_pdfs, render_pdf_pages  # noqa: E402


def _make_pdf(path: Path, label: str, *, extra_box: bool = False) -> None:
    """Write a one-page PDF. 1-bit mode → CCITT encoding, never the JPEG codec
    (whose availability in the Pillow wheel is not guaranteed)."""
    image = Image.new("1", (300, 200), 1)  # white page
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 40, 200, 140], outline=0, width=4)
    draw.text((50, 160), label, fill=0)
    if extra_box:
        draw.rectangle([210, 40, 280, 90], outline=0, width=4)
    image.save(str(path))


def test_render_pages_returns_inverted_grayscale(tmp_path: Path):
    pdf = tmp_path / "a.pdf"
    _make_pdf(pdf, "X")
    pages = render_pdf_pages(pdf, dpi=100)
    assert len(pages) == 1
    assert pages[0].mode == "L"


def test_identical_pdfs_have_no_change(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    _make_pdf(a, "REV")
    _make_pdf(b, "REV")
    diffs = diff_pdfs(a, b, dpi=100)
    assert len(diffs) == 1
    assert diffs[0].changed_pixels == 0
    assert diffs[0].common_pixels > 0


def test_added_geometry_detected(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    _make_pdf(a, "REV", extra_box=False)
    _make_pdf(b, "REV", extra_box=True)  # extra box only in B
    diffs = diff_pdfs(a, b, dpi=100)
    assert diffs[0].added_pixels > 0
    assert diffs[0].common_pixels > 0  # shared geometry stayed aligned
