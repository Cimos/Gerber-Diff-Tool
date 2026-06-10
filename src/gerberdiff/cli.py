"""``gdiff`` — command-line entry point for the Gerber diff engine.

    gdiff OLD_DIR NEW_DIR -o report.html [--dpmm N] [--threshold T] [--fail-on-diff]

The renderer is imported lazily so ``--help`` and argument parsing work even if
the rendering dependencies are not installed.
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
        description="Free, offline visual diff for PCB Gerber files.",
    )
    parser.add_argument("old_dir", type=Path, help="folder of Gerber/drill files (revision A, old)")
    parser.add_argument("new_dir", type=Path, help="folder of Gerber/drill files (revision B, new)")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("gerber-diff-report.html"),
        help="path to write the HTML report (default: %(default)s)",
    )
    parser.add_argument(
        "--dpmm", type=int, default=20,
        help="render resolution in dots per millimetre (default: %(default)s)",
    )
    parser.add_argument(
        "--threshold", type=int, default=10,
        help="luminance threshold (0-255) for counting a pixel as ink (default: %(default)s)",
    )
    parser.add_argument(
        "--fail-on-diff", action="store_true",
        help="exit with code 1 if any layer differs (useful in CI)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def run(args: argparse.Namespace) -> DiffResult:
    # Imported here so pairing/diff tests don't require the renderer.
    from .render import render_pair_aligned

    pairs = pair_layers(args.old_dir, args.new_dir)
    layers: list[LayerDiff] = []
    for pair in pairs:
        try:
            image_a, image_b = render_pair_aligned(pair.path_a, pair.path_b, dpmm=args.dpmm)
            layers.append(diff_layer(pair, image_a, image_b, threshold=args.threshold))
        except Exception as exc:  # noqa: BLE001 - one bad layer must not abort the run
            layers.append(LayerDiff(pair=pair, error=f"{type(exc).__name__}: {exc}"))
    return DiffResult(dir_a=args.old_dir, dir_b=args.new_dir, dpmm=args.dpmm, layers=layers)


def _print_summary(result: DiffResult) -> None:
    for layer in result.layers:
        if layer.error:
            mark, detail = "!", f"error: {layer.error}"
        elif layer.pair.status is PairStatus.ADDED:
            mark, detail = "+", "added layer"
        elif layer.pair.status is PairStatus.REMOVED:
            mark, detail = "-", "removed layer"
        elif layer.changed:
            mark, detail = "~", f"+{layer.added_pixels} / -{layer.removed_pixels} px"
        else:
            mark, detail = " ", "unchanged"
        print(f"  [{mark}] {layer.pair.layer_type:<16} {layer.pair.key:<28} {detail}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    for folder in (args.old_dir, args.new_dir):
        if not folder.is_dir():
            print(f"error: not a directory: {folder}", file=sys.stderr)
            return 2

    result = run(args)
    if not result.layers:
        print("error: no Gerber/drill files found to compare", file=sys.stderr)
        return 2

    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    from .report import render_html

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_html(result, generated_at=generated), encoding="utf-8")

    print(f"Compared {len(result.layers)} layers ({len(result.changed_layers)} changed):")
    _print_summary(result)
    print(f"\nReport written to {args.output}")

    if args.fail_on_diff and result.any_changes:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
