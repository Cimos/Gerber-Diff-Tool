# gerber-diff

**Free, offline, scriptable visual diff for PCB Gerber files — and schematic PDFs.**

`gerber-diff` compares two revisions of a board's fabrication data and shows you
exactly what changed: per layer, with a red/green overlay, in a self-contained
HTML report you can attach to a review or archive. It runs entirely on your
machine — nothing is uploaded — and the same engine drives a command line you can
wire into CI.

> Status: **early alpha (v0.1).** The Gerber diff path is the first milestone.
> Schematic-PDF diff and a desktop GUI are on the roadmap below.

## Why

Good Gerber diff tools exist but are either closed/paid
([gerbdiff.com](https://gerbdiff.com/)), tied to one EDA tool
([KiRi](https://github.com/leoheck/kiri) for KiCad), or thin wrappers around a
native viewer ([GrbDiff](https://github.com/dennevi/GrbDiff) over `gerbv`).
None of them are FOSS *and* cover **Gerber + schematic** in one lightweight,
cross-platform, scriptable package. That's the gap this fills.

## Features (v0.1)

- Compare two folders of Gerber/drill files.
- Automatic layer pairing by file name, with friendly layer-type labels.
- Native raster rendering via [`pygerber`](https://github.com/Argmaster/pygerber)
  — **no cairo / no system libraries**, so it behaves the same on Windows,
  macOS and Linux.
- Red = removed, green = added, grey = unchanged colour overlay.
- Self-contained single-file HTML report with embedded images.
- `--fail-on-diff` exit code for use in CI / GitHub Actions.

### Roadmap

- Schematic / PDF diff (render pages → pixel diff → highlight).
- Layer pairing across renamed exports (match by detected layer type).
- Desktop GUI (synchronised pan/zoom, side-by-side + overlay).
- Reusable GitHub Action that comments diffs on pull requests.

## Install

The project uses [`uv`](https://docs.astral.sh/uv/) for development, but it is a
standard `pyproject.toml` project, so plain `pip` works too.

```bash
# with uv (installs the right Python automatically)
uv sync
uv run gdiff --help

# or with pip, into a virtualenv
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
gdiff --help
```

## Usage

```bash
# Compare two revisions and write a report
gdiff path/to/rev-old path/to/rev-new -o diff-report.html

# Higher resolution (dots per millimetre), and fail the command if anything changed
gdiff rev-old rev-new -o report.html --dpmm 40 --fail-on-diff
```

The HTML report is self-contained — open it in any browser, no assets folder
required.

## How it works

```
two folders ─▶ pairing ─▶ render each layer ─▶ align ─▶ pixel diff ─▶ HTML report
              (by name)   (pygerber → PNG)   (by bbox)  (numpy XOR)
```

The diff *engine* (`gerberdiff.pairing`, `.diff`, `.report`) has no GUI and no
renderer baked in — it is plain functions over dataclasses, which is what keeps
it testable and scriptable. The renderer lives behind `gerberdiff.render` so it
can be swapped without touching the diff logic.

## Development

```bash
uv sync --extra dev
uv run pytest
```

CI runs the test suite on every push (see `.github/workflows/ci.yml`).

## License

[MIT](LICENSE) © 2026 Simon Maddison
