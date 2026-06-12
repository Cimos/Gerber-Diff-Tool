# Changelog

All notable changes to gerber-diff are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Desktop viewer keyboard shortcuts: `←`/`→` step layers, `1`–`6` pick a mode,
  `+`/`-` zoom, `Home`/`0`/`f` fit, `Esc` close.
- The launcher window title shows the version, so testers can report their build.
- Structured GitHub issue forms (bug report / feature request) and a README
  feedback link.

### Changed
- All GitHub Actions bumped to their Node-24 majors ahead of the 2026-06-16
  Node-20 deprecation (`setup-uv` pinned to `v8.2.0`, which has no floating tag).

### Tested
- The portable one-file exe is now self-tested in the release workflow, not just
  the installer build.
- Direct coverage of the Altium split copper/`NC Drill` merge path
  (`discovery.py` 77% → 95%).

## [0.10.0] - 2026-06-12

First public release with a standalone Windows download.

### Added
- **Native layer-by-layer desktop viewer** (`gdiff-gui`): changed-first layer
  list, Overlay / A / B / Split / Swipe / Onion modes, pan-zoom-fit.
- **Robust fab-pack input** — resolves flat folders, wrapped/nested folders,
  Altium split copper + drill, and `.zip` archives (including zip-in-zip) to the
  one directory holding the layer set, with a clear error when an input holds
  more than one board.
- **Standalone Windows app** — PyInstaller one-folder installer
  (`GerberDiffSetup.exe`) and a portable one-file build, published by a tagged
  release workflow. `gdiff --selftest` verifies a build end to end.
- **Branding** — overlay logo mark, app/window icons, and a logo on the README
  and HTML report, all regenerable from `branding/`.
- A "buy me a coffee" support link.

### Fixed
- Coverage gate restored to 90%+ by splitting the viewer's pure compositing
  logic into a unit-tested `compose.py` (the Tk shell is UI-only).

## Earlier development — 2026-06-11 (untagged)

Rapid initial build, by milestone:

- **0.9** — native Excellon drill diffing (holes as true circles; routed slots flagged).
- **0.8** — parallel layer rendering (~2.6× faster on an 18-layer board).
- **0.7** — zip inputs and content-based PDF page pairing; smaller reports.
- **0.6** — GitHub Action, git-ref inputs (`--git`), and a Markdown CI summary.
- **0.5** — split side-by-side view with synchronized pan/zoom.
- **0.4** — colour-blind-safe diff palette, interactive report viewer, accessibility pass.
- **0.3** — GUI overhaul and a broader test suite.
- **0.2** — report + GUI screenshots, README.
- **0.1** — Gerber diff engine + CLI.

[Unreleased]: https://github.com/Cimos/Gerber-Diff-Tool/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/Cimos/Gerber-Diff-Tool/releases/tag/v0.10.0
