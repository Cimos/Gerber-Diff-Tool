"""Tests for the PDF (schematic) diff path."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pypdfium2")

from PIL import Image, ImageDraw  # noqa: E402

from gerberdiff.models import PairStatus  # noqa: E402
from gerberdiff.pdfdiff import diff_pdfs, render_pdf_pages  # noqa: E402


def _page(label: str, *, extra_box: bool = False) -> Image.Image:
    # 1-bit mode -> CCITT encoding, never the JPEG codec (not always in the wheel).
    image = Image.new("1", (300, 200), 1)
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 40, 200, 140], outline=0, width=4)
    draw.text((50, 160), label, fill=0)
    if extra_box:
        draw.rectangle([210, 40, 280, 90], outline=0, width=4)
    return image


def _make_pdf(path: Path, label: str, *, extra_box: bool = False) -> None:
    _page(label, extra_box=extra_box).save(str(path))


def _make_multipage_pdf(path: Path, n: int) -> None:
    pages = [_page(f"page {i}") for i in range(n)]
    pages[0].save(str(path), save_all=True, append_images=pages[1:])


def test_render_pages_returns_inverted_grayscale(tmp_path: Path):
    pdf = tmp_path / "a.pdf"
    _make_pdf(pdf, "X")
    pages = render_pdf_pages(pdf, dpi=100)
    assert len(pages) == 1
    assert pages[0].mode == "L"


def test_render_multipage(tmp_path: Path):
    pdf = tmp_path / "m.pdf"
    _make_multipage_pdf(pdf, 3)
    assert len(render_pdf_pages(pdf, dpi=72)) == 3


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
    assert diffs[0].common_pixels > 0


def test_added_page_when_b_has_more_pages(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    _make_multipage_pdf(a, 1)
    _make_multipage_pdf(b, 2)
    diffs = diff_pdfs(a, b, dpi=72)
    assert len(diffs) == 2
    assert diffs[1].pair.status is PairStatus.ADDED
    assert diffs[1].pair.key == "page-2"


def test_removed_page_when_a_has_more_pages(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    _make_multipage_pdf(a, 2)
    _make_multipage_pdf(b, 1)
    diffs = diff_pdfs(a, b, dpi=72)
    assert len(diffs) == 2
    assert diffs[1].pair.status is PairStatus.REMOVED


def test_threshold_affects_pdf_diff(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    _make_pdf(a, "REV", extra_box=False)
    _make_pdf(b, "REV", extra_box=True)
    lenient = diff_pdfs(a, b, dpi=100, threshold=5)[0]
    strict = diff_pdfs(a, b, dpi=100, threshold=250)[0]
    assert lenient.added_pixels >= strict.added_pixels
