"""Shared diff runner used by both the CLI and the GUI.

Keeps mode-detection and report-writing in one place so the two front-ends can't
drift apart. Inputs may be folders of Gerbers, schematic PDFs, or **zip
archives** of Gerbers (fab packages) — zips are extracted to a temp dir for the
duration of the run, while reports keep showing the original zip path. Heavy
renderer imports are deferred into the functions. An optional *progress*
callback is invoked as ``progress(index, total, label)`` before each layer/page.
"""

from __future__ import annotations

import tempfile
import zipfile
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path

from .diff import diff_layer
from .models import DiffResult, LayerDiff
from .pairing import pair_layers

ProgressFn = Callable[[int, int, str], None]


def is_pdf(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".pdf"


def is_zip(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".zip"


def _materialize(path: Path, stack: ExitStack) -> Path:
    """Return a directory for *path*, extracting zip archives to a temp dir.

    The temp dir is registered on *stack*, so it lives until the diff completes
    (rendered images are in memory by then). A zip whose contents sit inside a
    single top-level folder is descended into automatically.
    """
    if not is_zip(path):
        return path
    dest = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="gdiff-zip-")))
    with zipfile.ZipFile(path) as archive:
        archive.extractall(dest)  # extract() sanitises absolute/illegal member paths
    entries = list(dest.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return dest


def run_diff(
    old: Path,
    new: Path,
    *,
    dpmm: int = 20,
    dpi: int = 150,
    threshold: int = 10,
    progress: ProgressFn | None = None,
) -> DiffResult:
    """Diff two inputs, auto-detecting Gerber-folder / zip / PDF mode.

    Raises ``ValueError`` if the inputs aren't two Gerber sources (folder or
    zip, mixable) or two PDFs.
    """
    old = Path(old)
    new = Path(new)

    if is_pdf(old) and is_pdf(new):
        from .pdfdiff import diff_pdfs

        layers = diff_pdfs(old, new, dpi=dpi, threshold=threshold, progress=progress)
        return DiffResult(
            dir_a=old, dir_b=new, resolution=f"{dpi} dpi", subject="page", layers=layers
        )

    with ExitStack() as stack:
        old_dir = _materialize(old, stack)
        new_dir = _materialize(new, stack)

        if old_dir.is_dir() and new_dir.is_dir():
            from .render import render_aligned_pair

            pairs = pair_layers(old_dir, new_dir)
            layers: list[LayerDiff] = []
            for index, pair in enumerate(pairs):
                if progress is not None:
                    progress(index, len(pairs), pair.layer_type)
                try:
                    aligned = render_aligned_pair(pair.path_a, pair.path_b, dpmm=dpmm)
                    layer = diff_layer(
                        pair, aligned.image_a, aligned.image_b, threshold=threshold, dpmm=dpmm
                    )
                    if not aligned.co_registered:
                        layer.warning = (
                            "inputs not co-registered (different extents) — diff may be offset"
                        )
                    layers.append(layer)
                except Exception as exc:  # noqa: BLE001 - one bad layer must not abort
                    layers.append(LayerDiff(pair=pair, error=f"{type(exc).__name__}: {exc}"))
            # Reports show the inputs as given (the zip path, not the temp dir).
            return DiffResult(
                dir_a=old, dir_b=new, resolution=f"{dpmm} dpmm", subject="layer", layers=layers
            )

    raise ValueError(
        "inputs must both be Gerber sources (a folder or a .zip), or both be .pdf files"
    )


def write_report(result: DiffResult, output: Path, *, generated_at: str | None = None) -> Path:
    """Render *result* to a self-contained HTML report at *output*."""
    from .report import render_html

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(result, generated_at=generated_at), encoding="utf-8")
    return output
