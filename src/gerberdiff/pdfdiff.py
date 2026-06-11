"""Diff two PDFs (e.g. schematics) page-by-page.

Each page is rendered with pypdfium2 (PDFium — a pip wheel, no system libraries)
then *inverted* so that dark ink becomes bright-on-dark, matching the
light-on-dark convention the diff engine already uses for gerbers. Pages are
paired by index, and the existing :mod:`gerberdiff.diff` and
:mod:`gerberdiff.report` machinery is reused unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageOps

from .diff import diff_layer
from .models import LayerDiff, LayerPair, PairStatus

ProgressFn = Callable[[int, int, str], None]


def render_pdf_pages(path: Path, *, dpi: int = 150) -> list[Image.Image]:
    """Render every page of *path* to an inverted grayscale image."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    try:
        pages: list[Image.Image] = []
        for index in range(len(document)):
            bitmap = document[index].render(scale=dpi / 72.0)
            page = bitmap.to_pil().convert("L")
            pages.append(ImageOps.invert(page))  # dark ink -> bright on dark bg
        return pages
    finally:
        document.close()


def diff_pdfs(
    pdf_a: Path | None,
    pdf_b: Path | None,
    *,
    dpi: int = 150,
    threshold: int = 10,
    progress: ProgressFn | None = None,
) -> list[LayerDiff]:
    """Diff two PDFs page-by-page; returns one :class:`LayerDiff` per page."""
    pages_a = render_pdf_pages(pdf_a, dpi=dpi) if pdf_a else []
    pages_b = render_pdf_pages(pdf_b, dpi=dpi) if pdf_b else []

    total = max(len(pages_a), len(pages_b))
    diffs: list[LayerDiff] = []
    for index in range(total):
        if progress is not None:
            progress(index, total, f"Page {index + 1}")
        image_a = pages_a[index] if index < len(pages_a) else None
        image_b = pages_b[index] if index < len(pages_b) else None
        if image_a is not None and image_b is not None:
            status = PairStatus.MATCHED
        elif image_b is not None:
            status = PairStatus.ADDED
        else:
            status = PairStatus.REMOVED
        pair = LayerPair(
            key=f"page-{index + 1}",
            layer_type=f"Page {index + 1}",
            status=status,
            path_a=pdf_a if image_a is not None else None,
            path_b=pdf_b if image_b is not None else None,
        )
        diffs.append(diff_layer(pair, image_a, image_b, threshold=threshold))
    return diffs
