"""Diff two PDFs (e.g. schematics) page-by-page.

Pages are paired by **text content**, not blindly by index: each page's
extracted text is aligned across the two documents with a sequence matcher, so
inserting or removing a sheet no longer offsets every later comparison. Pages
without extractable text (scanned/rasterised PDFs) degrade gracefully to
order-based pairing. Each paired page is rendered with pypdfium2 (PDFium — a
pip wheel, no system libraries), inverted so dark ink becomes bright-on-dark
(the diff engine's convention), and run through :mod:`gerberdiff.diff`.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageOps

from .diff import diff_layer
from .models import LayerDiff, LayerPair, PairStatus

ProgressFn = Callable[[int, int, str], None]

# (index_in_a | None, index_in_b | None) — None marks a removed/added page.
PagePair = tuple[int | None, int | None]


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


def extract_page_texts(path: Path) -> list[str]:
    """Whitespace-normalised text of every page (empty string when no text layer)."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    try:
        texts: list[str] = []
        for index in range(len(document)):
            textpage = document[index].get_textpage()
            try:
                raw = textpage.get_text_range() or ""
            finally:
                textpage.close()
            texts.append(" ".join(raw.split()))
        return texts
    finally:
        document.close()


def pair_pages(texts_a: list[str], texts_b: list[str]) -> list[PagePair]:
    """Align two page-text sequences into (a_index, b_index) pairs.

    Equal text pairs directly; replaced blocks pair positionally (a changed page
    still meets its counterpart); inserted/removed pages become one-sided pairs.
    All-empty texts (no text layer) reduce to order-based pairing.
    """
    matcher = difflib.SequenceMatcher(a=texts_a, b=texts_b, autojunk=False)
    pairs: list[PagePair] = []
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag == "equal":
            pairs.extend((a0 + k, b0 + k) for k in range(a1 - a0))
        elif tag == "replace":
            span = min(a1 - a0, b1 - b0)
            pairs.extend((a0 + k, b0 + k) for k in range(span))
            pairs.extend((a0 + k, None) for k in range(span, a1 - a0))
            pairs.extend((None, b0 + k) for k in range(span, b1 - b0))
        elif tag == "delete":
            pairs.extend((a0 + k, None) for k in range(a1 - a0))
        elif tag == "insert":
            pairs.extend((None, b0 + k) for k in range(b1 - b0))
    return pairs


def _pair_label(a_index: int | None, b_index: int | None) -> tuple[str, str]:
    """(key, human label) for a page pair; shows a shift like ``Page 3 → 4``."""
    if a_index is not None and b_index is not None:
        if a_index == b_index:
            return f"page-{b_index + 1}", f"Page {b_index + 1}"
        return f"page-{a_index + 1}-{b_index + 1}", f"Page {a_index + 1} → {b_index + 1}"
    if b_index is not None:
        return f"page-b{b_index + 1}", f"Page {b_index + 1} (new)"
    return f"page-a{a_index + 1}", f"Page {a_index + 1} (old)"


def diff_pdfs(
    pdf_a: Path | None,
    pdf_b: Path | None,
    *,
    dpi: int = 150,
    threshold: int = 10,
    progress: ProgressFn | None = None,
) -> list[LayerDiff]:
    """Diff two PDFs; returns one :class:`LayerDiff` per aligned page pair."""
    pages_a = render_pdf_pages(pdf_a, dpi=dpi) if pdf_a else []
    pages_b = render_pdf_pages(pdf_b, dpi=dpi) if pdf_b else []
    texts_a = extract_page_texts(pdf_a) if pdf_a else []
    texts_b = extract_page_texts(pdf_b) if pdf_b else []

    pairs = pair_pages(texts_a, texts_b)
    diffs: list[LayerDiff] = []
    for position, (a_index, b_index) in enumerate(pairs):
        key, label = _pair_label(a_index, b_index)
        if progress is not None:
            progress(position, len(pairs), label)
        image_a = pages_a[a_index] if a_index is not None else None
        image_b = pages_b[b_index] if b_index is not None else None
        if image_a is not None and image_b is not None:
            status = PairStatus.MATCHED
        elif image_b is not None:
            status = PairStatus.ADDED
        else:
            status = PairStatus.REMOVED
        pair = LayerPair(
            key=key,
            layer_type=label,
            status=status,
            path_a=pdf_a if image_a is not None else None,
            path_b=pdf_b if image_b is not None else None,
        )
        diffs.append(diff_layer(pair, image_a, image_b, threshold=threshold))
    return diffs
