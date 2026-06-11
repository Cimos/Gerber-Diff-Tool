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
    assert diffs[1].pair.key == "page-b2"
    assert "(new)" in diffs[1].pair.layer_type


def test_removed_page_when_a_has_more_pages(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    _make_multipage_pdf(a, 2)
    _make_multipage_pdf(b, 1)
    diffs = diff_pdfs(a, b, dpi=72)
    assert len(diffs) == 2
    assert diffs[1].pair.status is PairStatus.REMOVED
    assert "(old)" in diffs[1].pair.layer_type


def test_pair_pages_insertion_does_not_offset_later_pages():
    """The audit's failure case: a sheet inserted at the front must not make
    every later page report as changed."""
    from gerberdiff.pdfdiff import pair_pages

    a = ["sheet power", "sheet mcu", "sheet io"]
    b = ["sheet new cover", "sheet power", "sheet mcu", "sheet io"]
    assert pair_pages(a, b) == [(None, 0), (0, 1), (1, 2), (2, 3)]


def test_pair_pages_removal_and_changed_page():
    from gerberdiff.pdfdiff import pair_pages

    # page 1 edited (still pairs), page 2 removed
    a = ["alpha rev1", "beta"]
    b = ["alpha rev2"]
    assert pair_pages(a, b) == [(0, 0), (1, None)]


def test_pair_pages_textless_falls_back_to_order():
    from gerberdiff.pdfdiff import pair_pages

    assert pair_pages(["", ""], ["", "", ""]) == [(0, 0), (1, 1), (None, 2)]


def test_pair_pages_shift_label():
    from gerberdiff.pdfdiff import _pair_label

    assert _pair_label(2, 3) == ("page-3-4", "Page 3 → 4")
    assert _pair_label(1, 1) == ("page-2", "Page 2")


def test_diff_pdfs_reports_progress(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    _make_pdf(a, "X")
    _make_pdf(b, "X")
    seen: list[str] = []
    diff_pdfs(a, b, dpi=72, progress=lambda _i, _t, label: seen.append(label))
    assert seen == ["Page 1"]


def test_threshold_affects_pdf_diff(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    _make_pdf(a, "REV", extra_box=False)
    _make_pdf(b, "REV", extra_box=True)
    lenient = diff_pdfs(a, b, dpi=100, threshold=5)[0]
    strict = diff_pdfs(a, b, dpi=100, threshold=250)[0]
    assert lenient.added_pixels >= strict.added_pixels
