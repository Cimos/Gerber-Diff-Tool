# ADR 0001 — Platform and stack

- Status: **Accepted**
- Date: 2026-06-11

## Context

We want a tool that visually diffs two revisions of a PCB's **Gerber** data and,
later, its **schematic PDFs**. Hard requirements: free, fully offline,
cross-platform, lightweight, bug-free visuals, automated tests in CI,
scriptable (for a GitHub Action), light/dark report output, and — importantly —
**easy for outside contributors to extend**.

Reference points surveyed: gerbdiff.com (closed-source, freemium, Gerber-only),
KiRi (KiCad-only, wraps `kicad-cli`), GrbDiff (Python + Tkinter wrapper around
`gerbv`), and Altium's Gerber compare (closed).

## Decision

Build in **Python**, structured as a headless engine wrapped by thin shells.

| Concern | Choice | Why |
|---|---|---|
| Gerber render + bbox | **pygerber** | MIT, actively maintained, **native Pillow raster — no cairo / no system libraries**, so it behaves identically on Windows/macOS/Linux. `get_info()` also yields each file's mm bounding box, used to align two revisions on a shared frame. |
| Diff | **numpy** | Presence-mask XOR → added / removed / common. |
| Report | self-contained **HTML** | One file, images embedded as base64, light/dark via `prefers-color-scheme` + toggle. |
| CLI | **argparse** | Zero extra deps; the CLI is also the scripting/CI surface (`--fail-on-diff`). |
| Toolchain | **uv** + standard `pyproject.toml` | Reproducible, fetches its own Python, exact CI parity. Still `pip install -e .`-compatible for contributors. |
| Tests/CI | **pytest** + GitHub Actions matrix | ubuntu/windows/macos × py3.10/3.12. |

Architecture: `pairing → render → align → diff → report`. The engine
(`pairing`, `diff`, `report`) is plain functions over dataclasses with **no GUI
and no renderer imported at module load**, which is what makes it testable and
scriptable. The renderer is isolated in `render.py` so it can be swapped.

## Alternatives considered and rejected

- **Tauri v2 + TypeScript** — the lightest standalone binary (~10 MB) and the
  broadest contributor pool, and our original recommendation. Rejected for v1
  because the JS Gerber renderer (tracespace) has been stalled in a pre-release
  state for ~5 years under a single maintainer, and the project owner chose to
  forgo the small-binary priority in favour of the mature Python EDA libraries.
- **Rust-native (egui/iced)** — smallest/fastest, but the Rust gerber-render
  crates do not yet cover the full spec, and the casual-contributor pool is the
  smallest of the options.
- **Electron** — ruled out on bloat (~150 MB) against the "no bloat" requirement.
- **gerbonara** — an excellent gerber/Excellon parser (it can even parse KiCad
  schematics), but its render path is SVG-only and needs cairo to rasterize —
  the fragile native dependency on Windows we want to avoid — and it pulls a
  large web-server dependency tree. Since pygerber's `get_info()` covers
  bounding boxes, gerbonara is **not a v1 dependency**; it is the likely tool for
  later layer-stack auto-detection and structural schematic diff.

## Consequences

- **+** Mature, EDA-grade Gerber handling; a stack the PCB/maker community
  already knows; native-dependency-free rasterization.
- **−** A standalone single-file executable is heavier here than with a native
  stack. Deferred: package later with PyInstaller (or ship via `uv tool` /
  `pipx`). Python startup is also slower than a native binary — acceptable for a
  batch/report tool.
