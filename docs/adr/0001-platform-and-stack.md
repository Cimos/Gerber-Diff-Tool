# ADR 0001 — Platform and stack

- Status: **Accepted**
- Date: 2026-06-11

## Context

We want a tool that visually diffs two revisions of a PCB's **Gerber** data and
its **schematic PDFs**. Hard requirements: free, fully offline, cross-platform,
lightweight, bug-free visuals, automated tests in CI, scriptable (for a GitHub
Action), light/dark report output, and — importantly — **easy for outside
contributors to extend**.

Reference points surveyed: gerbdiff.com (closed-source, freemium, Gerber-only),
KiRi (KiCad-only, wraps `kicad-cli`), GrbDiff (Python + Tkinter wrapper around
`gerbv`), and Altium's Gerber compare (closed).

## Decision

Build in **Python**, structured as a headless engine wrapped by thin shells.

| Concern | Choice | Why |
|---|---|---|
| Gerber render + bbox | **pygerber** | MIT, actively maintained, **native Pillow raster — no cairo / no system libraries**, so it behaves identically on Windows/macOS/Linux. `get_info()` also yields each file's mm bounding box, used to align two revisions on a shared frame. |
| Layer detect / pair | **gerbonara** | Its `LayerStack` auto-detects each layer's `(side, function)`, so two revisions pair on layer *identity* and survive a board rename. It is finicky (raises on minimal/odd sets), so it is wrapped with a filename fallback. Used for detection only — **not** its SVG/cairo renderer. |
| Schematic / PDF render | **pypdfium2** | PDFium via a pip wheel — no system libraries. **Apache-2.0 / BSD licensed**, unlike AGPL PyMuPDF, so it is safe for an MIT project. Pages are rendered, inverted to match the gerber light-on-dark convention, and diffed by the same engine. |
| Diff | **numpy** | Presence-mask XOR → added / removed / common. |
| Report | self-contained **HTML** | One file, images embedded as base64, light/dark via `prefers-color-scheme` + toggle. |
| CLI | **argparse** | Zero extra deps; the CLI is also the scripting/CI surface (`--fail-on-diff`). |
| Toolchain | **uv** + standard `pyproject.toml` | Reproducible, fetches its own Python, exact CI parity. Still `pip install -e .`-compatible for contributors. |
| Tests/CI | **pytest** + GitHub Actions matrix | ubuntu/windows/macos × py3.10/3.12. |

Architecture: `pairing → render → align → diff → report` (gerbers) and
`pages → render → invert → diff → report` (PDFs). The engine (`pairing`, `diff`,
`report`) is plain functions over dataclasses with **no GUI and no renderer
imported at module load**, which is what makes it testable and scriptable.
Renderers are isolated in `render.py` (Gerber) and `pdfdiff.py` (PDF).

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
- **gerbonara's renderer** — gerbonara *is* a dependency (for layer detection,
  above), but we deliberately do **not** use its rendering path: it is SVG-only
  and needs cairo to rasterize — the fragile native dependency on Windows we
  avoid by rendering with pygerber.
- **PyMuPDF (fitz) for PDF** — excellent and fast, but **AGPL / commercial**,
  which is incompatible with an MIT project's permissive intent. pypdfium2 gives
  us PDFium under a permissive licence instead.

## Consequences

- **+** Mature, EDA-grade Gerber handling; a stack the PCB/maker community
  already knows; native-dependency-free rasterization for both Gerber and PDF;
  rename-tolerant, identity-based layer pairing.
- **−** Dependency footprint is not tiny: gerbonara pulls `quart` (an async web
  framework) transitively. It is an **install-time dependency only** — never
  imported at runtime for our use — so it costs install size, not speed.
- **−** A standalone single-file executable is heavier here than with a native
  stack. Deferred: package later with PyInstaller (or ship via `uv tool` /
  `pipx`). Python startup is also slower than a native binary — acceptable for a
  batch/report tool.
```
