"""Plain data structures shared across the diff engine.

These intentionally carry no behaviour beyond trivial derived properties, so the
whole module imports with only the standard library — handy for tests that never
touch a renderer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class PairStatus(str, Enum):
    """How a layer relates between revision A (old) and revision B (new)."""

    MATCHED = "matched"  # present in both revisions
    ADDED = "added"      # present only in B (a new layer)
    REMOVED = "removed"  # present only in A (a dropped layer)


@dataclass
class LayerPair:
    """A single layer matched (or not) across the two revisions."""

    key: str               # normalised pairing key (lower-cased file name)
    layer_type: str        # human label, e.g. "Top Copper"
    status: PairStatus
    path_a: Path | None    # file in revision A, or None if ADDED
    path_b: Path | None    # file in revision B, or None if REMOVED


@dataclass
class LayerDiff:
    """Result of diffing one :class:`LayerPair`."""

    pair: LayerPair
    width: int = 0
    height: int = 0
    added_pixels: int = 0     # set in B, clear in A  (drawn green)
    removed_pixels: int = 0   # set in A, clear in B  (drawn red)
    common_pixels: int = 0    # set in both           (drawn grey)
    overlay_png: bytes | None = None  # PNG bytes of the diff overlay image
    error: str | None = None  # populated if rendering/diffing this layer failed

    @property
    def changed_pixels(self) -> int:
        return self.added_pixels + self.removed_pixels

    @property
    def changed(self) -> bool:
        """True if the geometry differs, or the layer was added/removed."""
        if self.pair.status is not PairStatus.MATCHED:
            return True
        return self.changed_pixels > 0


@dataclass
class DiffResult:
    """Top-level result for a whole comparison (gerber folders or PDFs)."""

    dir_a: Path
    dir_b: Path
    resolution: str = ""    # e.g. "20 dpmm" (gerber) or "150 dpi" (pdf)
    subject: str = "layer"  # "layer" for gerbers, "page" for PDFs
    layers: list[LayerDiff] = field(default_factory=list)

    @property
    def changed_layers(self) -> list[LayerDiff]:
        return [layer for layer in self.layers if layer.changed]

    @property
    def any_changes(self) -> bool:
        return bool(self.changed_layers)
