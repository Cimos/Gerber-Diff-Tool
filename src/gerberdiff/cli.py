"""``gdiff`` — command-line entry point for the diff engine.

    gdiff OLD NEW -o report.html [options]

OLD and NEW are either two folders of Gerber/drill files, or two schematic PDF
files; the mode is auto-detected. The renderer is imported lazily so ``--help``
and argument parsing work even without the rendering dependencies.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

from . import __version__
from .diff import diff_layer
from .models import DiffResult, LayerDiff, PairStatus
from .pairing import pair_layers


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


def _is_pdf(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".pdf"


def _run_gerber(args: argparse.Namespace) -> DiffResult:
    from .render import render_pair_aligned  # lazy: pure-logic tests don't need it

    pairs = pair_layers(args.old, args.new)
    layers: list[LayerDiff] = []
    for pair in pairs:
        try:
            image_a, image_b = render_pair_aligned(pair.path_a, pair.path_b, dpmm=args.dpmm)
            layers.append(diff_layer(pair, image_a, image_b, threshold=args.threshold))
        except Exception as exc:  # noqa: BLE001 - one bad layer must not abort the run
            layers.append(LayerDiff(pair=pair, error=f"{type(exc).__name__}: {exc}"))
    return DiffResult(
        dir_a=args.old, dir_b=args.new,
        resolution=f"{args.dpmm} dpmm", subject="layer", layers=layers,
    )


def _run_pdf(args: argparse.Namespace) -> DiffResult:
    from .pdfdiff import diff_pdfs  # lazy

    layers = diff_pdfs(args.old, args.new, dpi=args.dpi, threshold=args.threshold)
    return DiffResult(
        dir_a=args.old, dir_b=args.new,
        resolution=f"{args.dpi} dpi", subject="page", layers=layers,
    )


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

    if _is_pdf(args.old) and _is_pdf(args.new):
        result = _run_pdf(args)
    elif args.old.is_dir() and args.new.is_dir():
        result = _run_gerber(args)
    else:
        print(
            "error: OLD and NEW must both be folders of Gerber files, "
            "or both be .pdf files",
            file=sys.stderr,
        )
        return 2

    if not result.layers:
        print("error: nothing to compare (no Gerber/drill files or PDF pages found)", file=sys.stderr)
        return 2

    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    from .report import render_html

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_html(result, generated_at=generated), encoding="utf-8")

    print(f"Compared {len(result.layers)} {result.subject}s ({len(result.changed_layers)} changed):")
    _print_summary(result)
    print(f"\nReport written to {args.output}")

    if args.fail_on_diff and result.any_changes:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
