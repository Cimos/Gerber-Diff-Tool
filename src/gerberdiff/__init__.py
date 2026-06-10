"""gerber-diff: free, offline visual diff for PCB Gerber files and schematic PDFs.

The package is split so the diff *engine* is importable and testable without any
GUI or renderer present:

    gerberdiff.models   - plain dataclasses describing pairs and diff results
    gerberdiff.pairing  - match files between two revisions, classify layer type
    gerberdiff.diff     - pixel-diff two aligned images, build the colour overlay
    gerberdiff.render   - render a Gerber to a raster image (pygerber)
    gerberdiff.report   - render a self-contained HTML report
    gerberdiff.cli      - the ``gdiff`` command-line entry point
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
