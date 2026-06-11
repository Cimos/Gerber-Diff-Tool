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


def _diff_one_layer(pair, dpmm: int, threshold: int) -> LayerDiff:
    """Render + diff a single layer pair; errors become error-layers.

    Module-level and picklable so it runs identically in the serial loop and in
    :class:`~concurrent.futures.ProcessPoolExecutor` workers.
    """
    from .render import render_aligned_pair

    try:
        aligned = render_aligned_pair(pair.path_a, pair.path_b, dpmm=dpmm)
        layer = diff_layer(pair, aligned.image_a, aligned.image_b, threshold=threshold, dpmm=dpmm)
        warnings = []
        if not aligned.co_registered:
            warnings.append("inputs not co-registered (different extents) — diff may be offset")
        if aligned.note:
            warnings.append(aligned.note)
        if warnings:
            layer.warning = "; ".join(warnings)
        return layer
    except Exception as exc:  # noqa: BLE001 - one bad layer must not abort the run
        return LayerDiff(pair=pair, error=f"{type(exc).__name__}: {exc}")


def _diff_layers_parallel(
    pairs: list, dpmm: int, threshold: int, jobs: int, progress: ProgressFn | None
) -> list[LayerDiff]:
    """Fan the per-layer work across processes; results keep input order."""
    from concurrent.futures import ProcessPoolExecutor, as_completed

    results: list[LayerDiff | None] = [None] * len(pairs)
    with ProcessPoolExecutor(max_workers=min(jobs, len(pairs), 8)) as pool:
        futures = {
            pool.submit(_diff_one_layer, pair, dpmm, threshold): index
            for index, pair in enumerate(pairs)
        }
        for done, future in enumerate(as_completed(futures)):
            index = futures[future]
            results[index] = future.result()
            if progress is not None:
                progress(done, len(pairs), pairs[index].layer_type)
    return [layer for layer in results if layer is not None]


def _materialize(path: Path, stack: ExitStack) -> Path:
    """Resolve *path* (folder or .zip) to the directory holding the Gerber set.

    Zips are extracted to a temp dir (registered on *stack*, so it lives until
    the diff completes); the Gerber set is then located even when it's wrapped or
    nested, and an Altium-style sibling drill folder is merged in — into a temp
    dir, never mutating the user's input. Non-folder, non-zip paths are returned
    unchanged for ``run_diff`` to reject. Raises ``GerberSourceError`` (a
    ``ValueError``) when no single Gerber set can be found.
    """
    from .discovery import extract_flat, locate_gerber_dir, merge_into_tempdir

    if is_zip(path):
        dest = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="gdiff-zip-")))
        extract_flat(path, dest)
        gerber_dir, drill_dir = locate_gerber_dir(dest)
    elif path.is_dir():
        gerber_dir, drill_dir = locate_gerber_dir(path)
    else:
        return path

    if drill_dir is not None:
        merged = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="gdiff-merge-")))
        return merge_into_tempdir(gerber_dir, drill_dir, merged)
    return gerber_dir


def run_diff(
    old: Path,
    new: Path,
    *,
    dpmm: int = 20,
    dpi: int = 150,
    threshold: int = 10,
    jobs: int = 0,
    progress: ProgressFn | None = None,
) -> DiffResult:
    """Diff two inputs, auto-detecting Gerber-folder / zip / PDF mode.

    ``jobs`` controls gerber-layer parallelism: 0 = auto (CPU count), 1 = serial.
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
            import os

            pairs = pair_layers(old_dir, new_dir)
            resolved_jobs = jobs if jobs > 0 else (os.cpu_count() or 1)
            layers: list[LayerDiff] | None = None
            if resolved_jobs > 1 and len(pairs) >= 4:
                try:
                    layers = _diff_layers_parallel(pairs, dpmm, threshold, resolved_jobs, progress)
                except (OSError, RuntimeError):  # pool unavailable -> serial fallback
                    layers = None
            if layers is None:
                layers = []
                for index, pair in enumerate(pairs):
                    if progress is not None:
                        progress(index, len(pairs), pair.layer_type)
                    layers.append(_diff_one_layer(pair, dpmm, threshold))
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
