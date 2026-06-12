"""``gdiff`` — command-line entry point for the diff engine.

    gdiff OLD NEW -o report.html [options]

OLD and NEW are either two folders of Gerber/drill files, or two schematic PDF
files; the mode is auto-detected (see :mod:`gerberdiff.runner`).
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
import tempfile
import warnings
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
        "old",
        type=Path,
        metavar="OLD",
        help="revision A: a folder or .zip of Gerber/drill files, a schematic .pdf, "
        "or a git ref when --git is given",
    )
    parser.add_argument(
        "new",
        type=Path,
        metavar="NEW",
        help="revision B: a folder or .zip of Gerber/drill files, a schematic .pdf, "
        "or a git ref when --git is given",
    )
    parser.add_argument(
        "--git",
        metavar="SUBDIR",
        default=None,
        dest="git_subdir",
        help="treat OLD and NEW as git refs and diff SUBDIR (a directory of Gerbers "
        "inside the repo) as it exists at each ref, e.g. gdiff v1.0 HEAD --git gerbers/",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("gerber-diff-report.html"),
        help="path to write the HTML report (default: %(default)s)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        metavar="PATH",
        dest="json_path",
        help="also write a machine-readable JSON summary to PATH (for CI/automation)",
    )
    parser.add_argument(
        "--summary-md",
        type=Path,
        default=None,
        metavar="PATH",
        dest="summary_md",
        help="also write a Markdown summary to PATH (for PR comments / CI step summaries)",
    )
    parser.add_argument(
        "--dpmm",
        type=int,
        default=20,
        help="gerber render resolution, dots per millimetre (default: %(default)s)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="PDF render resolution, dots per inch (default: %(default)s)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=10,
        help="luminance threshold (0-255) for counting a pixel as ink (default: %(default)s)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=0,
        help="parallel render workers for gerber layers; 0 = auto, 1 = serial "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--max-pixels",
        type=int,
        default=None,
        metavar="N",
        dest="max_pixels",
        help="cap each rendered layer at N pixels, lowering dpmm for very large "
        "boards (default: 16000000; 0 = uncapped)",
    )
    parser.add_argument(
        "--fail-on-diff",
        action="store_true",
        help="exit with code 1 if anything differs (useful in CI)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="suppress renderer warnings (e.g. pygerber's parser notices)",
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

    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
        warnings.simplefilter("ignore")

    if args.dpmm <= 0 or args.dpi <= 0 or not (0 <= args.threshold <= 255) or args.jobs < 0:
        print(
            "error: --dpmm and --dpi must be > 0, --threshold in 0-255, --jobs >= 0",
            file=sys.stderr,
        )
        return 2

    try:
        if args.git_subdir:
            from .gitrefs import materialize_ref

            # Extract both refs into a temp dir owned by this block; diffing and
            # report rendering finish before it is cleaned up (images live in
            # memory once run_diff returns).
            with tempfile.TemporaryDirectory(prefix="gdiff-git-") as tmp:
                old_dir = materialize_ref(str(args.old), args.git_subdir, Path(tmp) / "a")
                new_dir = materialize_ref(str(args.new), args.git_subdir, Path(tmp) / "b")
                result = run_diff(
                    old_dir,
                    new_dir,
                    dpmm=args.dpmm,
                    dpi=args.dpi,
                    threshold=args.threshold,
                    jobs=args.jobs,
                    max_pixels=args.max_pixels,
                )
            # Display the refs, not the temp paths, in reports and summaries.
            result.dir_a = Path(f"{args.old}:{args.git_subdir}")
            result.dir_b = Path(f"{args.new}:{args.git_subdir}")
        else:
            result = run_diff(
                args.old,
                args.new,
                dpmm=args.dpmm,
                dpi=args.dpi,
                threshold=args.threshold,
                jobs=args.jobs,
                max_pixels=args.max_pixels,
            )
    except ValueError as exc:  # includes GitRefError
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not result.layers:
        print(
            "error: nothing to compare (no Gerber/drill files or PDF pages found)", file=sys.stderr
        )
        return 2

    generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    write_report(result, args.output, generated_at=generated)
    if args.json_path is not None:
        from .report import render_json

        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(render_json(result), encoding="utf-8")
    if args.summary_md is not None:
        from .summary import render_markdown

        args.summary_md.parent.mkdir(parents=True, exist_ok=True)
        args.summary_md.write_text(render_markdown(result), encoding="utf-8")

    print(
        f"Compared {len(result.layers)} {result.subject}s ({len(result.changed_layers)} changed):"
    )
    _print_summary(result)
    print(f"\nReport written to {args.output}")
    if args.json_path is not None:
        print(f"JSON summary written to {args.json_path}")

    if args.fail_on_diff and result.any_changes:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
