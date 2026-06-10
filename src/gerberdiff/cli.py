"""``gdiff`` — command-line entry point for the diff engine.

    gdiff OLD NEW -o report.html [options]

OLD and NEW are either two folders of Gerber/drill files, or two schematic PDF
files; the mode is auto-detected (see :mod:`gerberdiff.runner`).
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

from . import __version__
from .models import DiffResult, PairStatus
from .runner import run_diff, write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gdiff",
        description="Free, offline visual diff for PCB Gerber files and schematic PDFs.",
    )
    parser.add_argument(
        "old", type=Path, metavar="OLD",
        help="revision A: a folder of Gerber/drill files, or a schematic .pdf",
    )
    parser.add_argument(
        "new", type=Path, metavar="NEW",
        help="revision B: a folder of Gerber/drill files, or a schematic .pdf",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("gerber-diff-report.html"),
        help="path to write the HTML report (default: %(default)s)",
    )
    parser.add_argument(
        "--dpmm", type=int, default=20,
        help="gerber render resolution, dots per millimetre (default: %(default)s)",
    )
    parser.add_argument(
        "--dpi", type=int, default=150,
        help="PDF render resolution, dots per inch (default: %(default)s)",
    )
    parser.add_argument(
        "--threshold", type=int, default=10,
        help="luminance threshold (0-255) for counting a pixel as ink (default: %(default)s)",
    )
    parser.add_argument(
        "--fail-on-diff", action="store_true",
        help="exit with code 1 if anything differs (useful in CI)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _print_summary(result: DiffResult) -> None:
    for layer in result.layers:
        if layer.error:
            mark, detail = "!", f"error: {layer.error}"
        elif layer.pair.status is PairStatus.ADDED:
            mark, detail = "+", f"added {result.subject}"
        elif layer.pair.status is PairStatus.REMOVED:
            mark, detail = "-", f"removed {result.subject}"
        elif layer.changed:
            mark, detail = "~", f"+{layer.added_pixels} / -{layer.removed_pixels} px"
        else:
            mark, detail = " ", "unchanged"
        print(f"  [{mark}] {layer.pair.layer_type:<16} {layer.pair.key:<28} {detail}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        result = run_diff(
            args.old, args.new, dpmm=args.dpmm, dpi=args.dpi, threshold=args.threshold
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not result.layers:
        print("error: nothing to compare (no Gerber/drill files or PDF pages found)", file=sys.stderr)
        return 2

    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    write_report(result, args.output, generated_at=generated)

    print(f"Compared {len(result.layers)} {result.subject}s ({len(result.changed_layers)} changed):")
    _print_summary(result)
    print(f"\nReport written to {args.output}")

    if args.fail_on_diff and result.any_changes:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
