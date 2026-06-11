"""Match Gerber/drill files between two revision folders and label layer types.

Two strategies, best-first:

1. **Semantic (gerbonara).** ``gerbonara.layers.LayerStack`` auto-detects each
   graphic layer's ``(side, function)`` — e.g. ``('top', 'copper')`` — across
   many EDA naming conventions. Pairing on that identity survives a board being
   renamed between revisions. gerbonara is finicky (it raises on minimal or
   unusual file sets), so this is attempted defensively.
2. **Filename (catch-all / fallback).** Files gerbonara doesn't recognise — drill
   files, unusual layers, or *everything* if gerbonara can't map the folder at
   all — are paired by normalised file name. This always works.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

from .models import LayerPair, PairStatus

# Extensions we treat as Gerber or drill data. Deliberately broad: KiCad emits
# ``.gbr``/``.drl`` while Protel-style exports use per-layer extensions.
GERBER_EXTS: frozenset[str] = frozenset(
    {
        ".gbr",
        ".ger",
        ".gb",
        ".art",
        ".pho",
        ".gerber",
        # Protel / Altium per-layer copper, mask, paste, silk, outline
        ".gtl",
        ".gbl",
        ".gto",
        ".gbo",
        ".gts",
        ".gbs",
        ".gtp",
        ".gbp",
        ".gko",
        ".gm1",
        ".gm2",
        ".gml",
        ".gpt",
        ".gpb",
        ".g1",
        ".g2",
        ".g3",
        ".g4",
        ".g5",
        ".g6",
        # Drill / Excellon
        ".drl",
        ".xln",
        ".txt",
        ".nc",
        ".tap",
        ".exc",
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
    (re.compile(r"(f[._-]?fab|fabrication.*top)", re.I), "Top Fab"),
    (re.compile(r"(b[._-]?fab|fabrication.*bot)", re.I), "Bottom Fab"),
    (re.compile(r"courtyard", re.I), "Courtyard"),
    (re.compile(r"(adhesive|glue)", re.I), "Adhesive"),
    (
        re.compile(r"(user[._-]?(comments|drawings|eco)|\beco\d?\b|margin|cmts|drawings?)", re.I),
        "Documentation",
    ),
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


def _status(a: Path | None, b: Path | None) -> PairStatus:
    if a and b:
        return PairStatus.MATCHED
    return PairStatus.ADDED if b else PairStatus.REMOVED


def _gerbonara_graphic_map(folder: Path) -> dict[str, Path]:
    """Map ``{"top copper": path, ...}`` via gerbonara, or ``{}`` if it can't.

    Only graphic layers are taken from gerbonara; drills and anything it ignores
    are left for the filename pass. Any failure (gerbonara not installed, an
    unmappable folder) degrades silently to an empty map.
    """
    try:
        from gerbonara.layers import LayerStack

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            stack = LayerStack.open(str(folder))
    except Exception:
        return {}

    mapping: dict[str, Path] = {}
    for (side, function), layer in getattr(stack, "graphic_layers", {}).items():
        path = getattr(layer, "original_path", None)
        if path:
            mapping[f"{side} {function}"] = Path(path)
    return mapping


def pair_layers(dir_a: Path, dir_b: Path) -> list[LayerPair]:
    """Pair files in *dir_a* (old) and *dir_b* (new).

    Layers gerbonara recognises are paired on semantic identity (rename-tolerant);
    everything else is paired by normalised file name.
    """
    files_a = {p.name.lower(): p for p in iter_gerber_files(dir_a)}
    files_b = {p.name.lower(): p for p in iter_gerber_files(dir_b)}

    semantic_a = _gerbonara_graphic_map(dir_a)
    semantic_b = _gerbonara_graphic_map(dir_b)

    pairs: list[LayerPair] = []

    # 1. Semantic pairs (rename-tolerant) for layers gerbonara recognised.
    for key in sorted(set(semantic_a) | set(semantic_b)):
        a = semantic_a.get(key)
        b = semantic_b.get(key)
        pairs.append(
            LayerPair(
                key=key,
                layer_type=key.title(),
                status=_status(a, b),
                path_a=a,
                path_b=b,
            )
        )

    # 2. Filename pairs for everything gerbonara didn't account for.
    mapped_a = {p.name.lower() for p in semantic_a.values()}
    mapped_b = {p.name.lower() for p in semantic_b.values()}
    leftover_a = {n: p for n, p in files_a.items() if n not in mapped_a}
    leftover_b = {n: p for n, p in files_b.items() if n not in mapped_b}
    for name in sorted(set(leftover_a) | set(leftover_b)):
        a = leftover_a.get(name)
        b = leftover_b.get(name)
        pairs.append(
            LayerPair(
                key=name,
                layer_type=classify_layer(name),
                status=_status(a, b),
                path_a=a,
                path_b=b,
            )
        )

    return pairs
