"""Match Gerber/drill files between two revision folders and label layer types.

v1 pairs by normalised file name (lower-cased), which is correct for the common
case of re-exporting the same project. Pairing across *renamed* exports (a
different project prefix on each side) is a planned enhancement — see the
roadmap in README.md.
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import LayerPair, PairStatus

# Extensions we treat as Gerber or drill data. Deliberately broad: KiCad emits
# ``.gbr``/``.drl`` while Protel-style exports use per-layer extensions.
GERBER_EXTS: frozenset[str] = frozenset(
    {
        ".gbr", ".ger", ".gb", ".art", ".pho", ".gerber",
        # Protel / Altium per-layer copper, mask, paste, silk, outline
        ".gtl", ".gbl", ".gto", ".gbo", ".gts", ".gbs", ".gtp", ".gbp",
        ".gko", ".gm1", ".gm2", ".gml", ".gpt", ".gpb",
        ".g1", ".g2", ".g3", ".g4", ".g5", ".g6",
        # Drill / Excellon
        ".drl", ".xln", ".txt", ".nc", ".tap", ".exc",
    }
)

# Ordered (pattern, label) rules. First match wins, so put specific before broad.
_LAYER_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(f[._-]?cu|top.?copper|copper.?top|\.gtl$)", re.I), "Top Copper"),
    (re.compile(r"(b[._-]?cu|bot.?copper|copper.?bot|\.gbl$)", re.I), "Bottom Copper"),
    (re.compile(r"(in\d+[._-]?cu|internal|\.g\d$)", re.I), "Inner Copper"),
    (re.compile(r"(f[._-]?mask|top.?mask|\.gts$)", re.I), "Top Soldermask"),
    (re.compile(r"(b[._-]?mask|bot.?mask|\.gbs$)", re.I), "Bottom Soldermask"),
    (re.compile(r"(f[._-]?silks?|top.?silk|\.gto$)", re.I), "Top Silkscreen"),
    (re.compile(r"(b[._-]?silks?|bot.?silk|\.gbo$)", re.I), "Bottom Silkscreen"),
    (re.compile(r"(f[._-]?paste|top.?paste|\.gtp$)", re.I), "Top Paste"),
    (re.compile(r"(b[._-]?paste|bot.?paste|\.gbp$)", re.I), "Bottom Paste"),
    (re.compile(r"(edge|outline|\.gko$|\.gml?$|\.gm\d$)", re.I), "Board Outline"),
    (re.compile(r"(drl|drill|excellon|\.xln$|\.nc$|\.exc$|\.tap$)", re.I), "Drill"),
]


def classify_layer(name: str) -> str:
    """Best-effort human label for a Gerber/drill file name."""
    for pattern, label in _LAYER_RULES:
        if pattern.search(name):
            return label
    return "Unknown layer"


def iter_gerber_files(folder: Path) -> list[Path]:
    """Return Gerber/drill files directly inside *folder*, sorted by name."""
    if not folder.is_dir():
        raise NotADirectoryError(f"not a directory: {folder}")
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in GERBER_EXTS),
        key=lambda p: p.name.lower(),
    )


def pair_layers(dir_a: Path, dir_b: Path) -> list[LayerPair]:
    """Pair files in *dir_a* (old) and *dir_b* (new) by normalised file name."""
    files_a = {p.name.lower(): p for p in iter_gerber_files(dir_a)}
    files_b = {p.name.lower(): p for p in iter_gerber_files(dir_b)}

    pairs: list[LayerPair] = []
    for key in sorted(set(files_a) | set(files_b)):
        a = files_a.get(key)
        b = files_b.get(key)
        if a and b:
            status = PairStatus.MATCHED
        elif b:
            status = PairStatus.ADDED
        else:
            status = PairStatus.REMOVED
        pairs.append(
            LayerPair(
                key=key,
                layer_type=classify_layer(key),
                status=status,
                path_a=a,
                path_b=b,
            )
        )
    return pairs
