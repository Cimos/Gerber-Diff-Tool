# Contributing to gerber-diff

Thanks for considering a contribution — this project is deliberately structured
so new capabilities slot in without touching the core.

## Dev setup

```bash
git clone https://github.com/Cimos/Gerber-Diff-Tool
cd Gerber-Diff-Tool
uv sync --extra dev          # or: pip install -e ".[dev]"
uv run pytest                # full suite, a few seconds
uv run ruff check . && uv run ruff format .
```

CI (lint + tests with a 90% coverage gate + an action self-test) runs on
Ubuntu/Windows/macOS × Python 3.12/3.13 — green CI is the merge bar.

## How the code is shaped

```
pairing  ─▶  render  ─▶  align  ─▶  diff  ─▶  report / summary
(what to     (file →     (shared    (numpy     (HTML viewer, JSON, Markdown)
 compare)     raster)     frame)     masks)
```

- `models.py` — plain dataclasses; everything else passes these around.
- `pairing.py` — matches files across two revisions (gerbonara semantic
  identity first, filename fallback).
- `render.py` — file → `Rendered(image, bbox_mm)`. pygerber for Gerber,
  gerbonara-based circle rasteriser for Excellon. **Add new formats here**: any
  function returning a `Rendered` joins the pipeline; nothing downstream changes.
- `diff.py` — renderer-agnostic pixel diff; colour-blind-safe overlay encoding
  (blue added / hatched-orange removed). Pure functions over PIL images.
- `runner.py` — the one orchestration path shared by CLI, GUI, and Action
  (zip extraction, parallel fan-out, progress callbacks).
- `report.py` / `summary.py` — self-contained HTML viewer / Markdown for CI.
- `cli.py` / `gui.py` / `action.yml` — thin shells over `runner.py`. Don't put
  logic in a shell that the other shells would then lack.

## Ground rules

- **Engine stays headless.** `pairing`/`diff`/`report` must import and run with
  no renderer and no GUI present (tests rely on it).
- **No new system-library dependencies.** Everything installs from wheels on
  all three OSes — that's a core promise of the tool (no cairo, no gerbv).
- **No silent gaps.** If your code skips geometry it can't handle, surface a
  layer warning (see the Excellon slot handling) — a diff tool that quietly
  drops features misleads reviewers.
- **Meaning never rides on colour alone.** The overlay encodes removed with a
  hatch as well as a hue; keep any new visuals colour-blind-safe.
- **Tests accompany features.** Synthetic fixtures live in `tests/fixtures/`;
  pure-logic tests shouldn't need the renderer (use `pytest.importorskip`).

## Good first contributions

- New layer-name classification rules (`pairing.py`, `_LAYER_RULES`).
- Routed-slot rendering for Excellon (`render.py::render_excellon` — currently
  warned about, not drawn).
- A new renderer (e.g. ODB++, IPC-2581) returning `Rendered`.
- Report viewer niceties (the HTML/JS lives entirely in `report.py`).

## Releases

Versions bump in `pyproject.toml` + `src/gerberdiff/__init__.py` together;
README status/Features headings track the minor version.
