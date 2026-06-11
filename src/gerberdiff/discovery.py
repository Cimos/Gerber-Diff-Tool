"""Resolve a user-supplied Gerber source to the directory holding the layer set.

Real fab "data packs" rarely match the naive "a folder whose Gerbers sit right
at the top" shape: KiCad/JLCPCB zips wrap everything in a sub-folder, Altium
splits copper and ``NC Drill`` into sibling folders, packs carry README/BOM
clutter, and some are zip-in-zip. This module turns any of those — a flat
folder, a folder with Gerbers nested a few levels down, or a ``.zip`` — into the
single directory that actually holds the layer set, which is exactly what
``pair_layers`` expects. Stdlib ``zipfile`` only.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from .pairing import GERBER_EXTS

# .txt is an Excellon alias *and* the extension of every README/notes file in a
# pack, so counting it as Gerber evidence wrecks the heuristic. Excluded from
# scoring (still diffed if it lands in the chosen dir).
_SCORE_EXTS = GERBER_EXTS - {".txt"}
_DRILL_EXTS = {".drl", ".xln", ".nc", ".tap", ".exc"}
_MIN_NESTED_LAYERS = 2  # a board is >=2 Gerbers; the ambiguity guard handles multi-board packs
_MAX_ZIP_DEPTH = 3


class GerberSourceError(ValueError):
    """Input could not be resolved to a single Gerber/drill directory."""


def _score(directory: Path) -> int:
    """Count Gerber/drill files directly in *directory* (``.txt`` excluded)."""
    return sum(1 for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _SCORE_EXTS)


def _sibling_drill_dir(chosen: Path) -> Path | None:
    """A sibling folder that is *only* drill files (Altium's split ``NC Drill``)."""
    parent = chosen.parent
    if parent == chosen or not parent.exists():
        return None
    for sib in sorted(parent.iterdir()):
        if sib.is_dir() and sib != chosen:
            files = [p for p in sib.iterdir() if p.is_file()]
            if files and all(p.suffix.lower() in _DRILL_EXTS for p in files):
                return sib
    return None


def extract_flat(zip_path: Path, dest: Path, _depth: int = 0) -> None:
    """Extract *zip_path* into *dest*, recursively unpacking nested zips (capped).

    ``ZipFile.extractall`` already strips absolute paths and ``..`` components, so
    this is safe against path traversal.
    """
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(dest)
    if _depth >= _MAX_ZIP_DEPTH:
        return
    for inner in list(dest.rglob("*.zip")):
        sub = inner.with_suffix("")
        sub.mkdir(exist_ok=True)
        extract_flat(inner, sub, _depth + 1)
        inner.unlink()  # remove the consumed zip so it isn't re-scored


def locate_gerber_dir(root: Path) -> tuple[Path, Path | None]:
    """Find the directory under *root* holding the Gerber/drill set.

    Returns ``(gerber_dir, sibling_drill_dir_or_None)``. If *root* itself holds
    Gerbers it is used directly (the flat-folder / flat-zip case, any file
    count). Otherwise the descendant directory with the most Gerber/drill files
    (``.txt`` excluded, at least ``_MIN_NESTED_LAYERS``) wins; ties break by
    shallowest then lexical, so the result is deterministic. Raises
    :class:`GerberSourceError` when nothing qualifies or two distinct boards tie.
    """
    root = Path(root)
    if _score(root) >= 1:
        return root, None  # flat folder / flat zip — backward compatible

    candidates: list[tuple[int, int, str, Path]] = []
    for d in (p for p in root.rglob("*") if p.is_dir()):
        score = _score(d)
        if score >= _MIN_NESTED_LAYERS:
            depth = len(d.relative_to(root).parts)
            candidates.append((-score, depth, str(d).lower(), d))

    if not candidates:
        any_gerber = any(p.is_file() and p.suffix.lower() in _SCORE_EXTS for p in root.rglob("*"))
        raise GerberSourceError(
            "no Gerber/drill layer set found inside the input"
            + (
                f" — fewer than {_MIN_NESTED_LAYERS} Gerber files in any one folder "
                "(a partial export?)"
                if any_gerber
                else " (no .gbr / .gtl / .drl / … files found in the folder or zip)"
            )
        )

    candidates.sort()
    best_score = -candidates[0][0]
    chosen = candidates[0][3]
    rivals = [
        c[3]
        for c in candidates
        if -c[0] >= best_score - 1
        and c[3] != chosen
        and chosen not in c[3].parents
        and c[3] not in chosen.parents
    ]
    if rivals:
        names = ", ".join(p.name for p in [chosen, *rivals][:4])
        raise GerberSourceError(
            f"this input holds more than one board's Gerber set ({names}) — "
            "point the tool at a single board's folder or zip"
        )
    return chosen, _sibling_drill_dir(chosen)


def merge_into_tempdir(gerber_dir: Path, drill_dir: Path, dest: Path) -> Path:
    """Copy *gerber_dir*'s files plus *drill_dir*'s drills into *dest* (never
    mutating the user's input). Returns *dest*."""
    dest = Path(dest)
    for p in gerber_dir.iterdir():
        if p.is_file():
            shutil.copy2(p, dest / p.name)
    for p in drill_dir.iterdir():
        if p.is_file() and not (dest / p.name).exists():
            shutil.copy2(p, dest / p.name)
    return dest
