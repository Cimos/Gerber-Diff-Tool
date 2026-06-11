# gerber-diff — UI/UX Audit & Improvement Roadmap

- Date: 2026-06-11 · Against: v0.3.0
- Surfaces audited: desktop GUI (`gui.py`), HTML report (`report.py`), CLI (`cli.py`), diff overlay (`diff.py`).

## Method

- **Peer-review panel** — three independent expert passes over the actual code + rendered
  screenshots, each through a distinct lens: (a) accessibility / inclusive design,
  (b) visual & interaction design, (c) PCB-reviewer job-to-be-done.
- **Prior-art research** — gerbdiff.com, KiRi, Altium Gerber Compare, GitHub image view
  modes (2-up / swipe / onion-skin), and colour-blind data-visualisation guidance.
- **WCAG 2.2 AA contrast** — computed on the real palettes (sRGB relative luminance,
  `(L1+0.05)/(L2+0.05)`); colour-blindness via a dichromat simulation.

## Executive summary — the five that matter most

1. **The red/green diff overlay excludes ~8% of the target audience and is low-contrast for
   everyone (P0, correctness of the core feature).** Meaning is carried by hue alone.
2. **Alignment registers from the top-left union corner, not a board datum (P0, trust).** A
   benign origin/extent shift between exports can paint a whole layer as changed — false positives.
3. **The primary "Compare" button fails AA and isn't keyboard-operable (P0).**
4. **The report buries the answer and can't show *where* the change is (P1).** 17 "unchanged"
   rows hide the one that matters; a real change is a 1–2px speck on a fit-to-width image with no zoom.
5. **No loading/progress affordance (P1).** The multi-second diff looks frozen.

---

## P0 — Critical

### 1. Diff overlay is colour-blind-hostile (and near-isoluminant for everyone)
Meaning is encoded purely as red (`COLOR_REMOVED 220,50,50`) vs green (`COLOR_ADDED 40,200,60`)
vs grey (`COLOR_COMMON 110,110,110`), with no redundant channel. Computed perceived contrast:

| Pair | Normal vision | Deuteranopia | Protanopia |
|---|---|---|---|
| removed vs unchanged | 1.10:1 | 1.46:1 | **1.09:1** |
| added vs removed | 2.07:1 | 1.45:1 | — |

Under protanopia, a **deleted trace** (the most safety-critical signal) is indistinguishable from
unchanged copper. This fails WCAG 1.4.1 (Use of Colour, Level A) outright, on the feature the whole
tool exists for, for an audience (electronics engineers) that skews heavily toward the ~8% of men
with red-green CVD.

**Fix (do both):**
- **Redundant, non-colour encoding** — the robust win. Either render removed as a hatch/cross-hatch
  and added as solid, or emit **added-only / removed-only** sub-overlays toggled in the report
  (a "blink/onion" style), so the signal survives in greyscale.
- **CVD-safe palette** — blue/orange is the most universally distinguishable diverging pair across
  all CVD types (research consensus). Suggested: added `#1f77ff`, removed `#ff7f0e`, with a darker
  unchanged grey (`#3a3a3a`) so each separates in luminance too.

### 2. Alignment is top-left, not a common datum → false "everything changed"
`render._compose_on` clamps the paste offset with `max(0, offset)` and `diff._pad_to` anchors
top-left. If rev B's Gerber origin or extents differ (common across EDA-tool/version changes), the
two layers align by their union corner, not a board datum — a pure coordinate shift then paints the
entire layer red+green. **Minimum fix:** detect `bbox_a != bbox_b` for a matched layer (data is in
`Rendered.bbox_mm`) and surface a "inputs not co-registered — diff may be offset" warning on that
card. **Better:** register on the board-outline bbox (or fiducials).

### 3. "Compare" button fails AA + no keyboard operability
White `#ffffff` on accent `#4f8cff` = **3.22:1** (fails AA 4.5:1 for the bold-11pt label); on hover
`#6ba0ff` it drops to **2.59:1** — the primary action gets *less* legible on interaction. Buttons
set `highlightthickness=0` so keyboard focus is invisible, hover is mouse-only (`<Enter>`/`<Leave>`),
and there is no `<Return>`-to-Compare binding. **Fix:** darken accent to `#2f6fe0` (white → **4.7:1**)
and make hover *darker*, not lighter; restore a visible focus ring on buttons and bind `<FocusIn>`;
`root.bind("<Return>", …)` + `default="active"` on Compare; `.focus_set()` the first field on launch.

---

## P1 — High (workflow & perceived quality)

### 4. Lead with the answer; let the reviewer see *both sides*
The report renders all layers in source order, so the one `changed` row sits among ~17
"unchanged / 0 / 0.000%" rows. And the only view is a single fixed three-colour blend — there's no
way to see what A vs B actually look like, or whether a red+green cluster is a *moved* trace or a
delete+add. **Fix:** sort changed/added/removed/error rows first (or a default "only changed"
toggle); make each changed row anchor-link to its overlay card; and embed the **A and B source
rasters** (they already exist transiently in `render_pair_aligned`, currently discarded) with a
per-card **swipe slider / onion-skin / A·B·overlay** toggle. All three benchmarks beat us here;
GitHub's 2-up/swipe/onion-skin is the proven pattern, doable in the existing static HTML.

### 5. Locate the change: zoom/pan + a changed-region marker
A 100 mm board at 20 dpmm is ~2000 px crushed into a ~1060 px column; a via move is a 1–2px speck
that's present but unfindable, and there's no zoom/pan. **Fix:** compute the changed-pixel bounding
box (trivial from the numpy masks in `diff_layer`) and draw a marker rectangle and/or a cropped
"detail" inset — "here is the change"; add client-side pan/zoom on the report image. gerbdiff.com's
synchronised pan/zoom exists for exactly this.

### 6. Loading/progress affordance
A diff is multi-second; the only feedback is the button greying (it loses its accent and visually
vanishes into the row above) and "Comparing…". **Fix:** keep the button present-but-busy (dimmed
accent, label "Comparing…"), feed per-layer progress from `run_diff` ("Rendering layer 6 of 18…"),
set a `watch` cursor.

### 7. First-run empty state & error UX
First launch is a near-blank form; the helpful orientation copy is buried as the mid-card mode hint
while the prominent status slot says only "Ready." Errors render the raw exception class
(`ValueError: …`) as one bare red line with no recovery step. **Fix:** move orientation copy into the
empty results area; (ideally) accept folder drag-drop; strip exception-class names from user-facing
copy and append an actionable hint; add a state glyph.

---

## P2 — Medium

- **Unify the GUI ↔ report design system.** Different accent blues (`#4f8cff` GUI vs `#5b9bd5`
  report), different light-theme semantic colours, and "gerber-diff" vs "Gerber Diff Report" wordmark.
  Pick one accent, one semantic red/green (→ CVD-safe pair from #1), one wordmark.
- **Report semantics.** Add `scope="col"` to `<th>`, a `<caption>`, `<th scope="row">` on layer
  names; initialise the theme-toggle's label + `aria-pressed` on load (it currently desyncs).
- **Measurement in mm.** Report each changed layer's changed-region bbox in mm (px ÷ dpmm); a
  reviewer needs millimetres, not pixels. (Full click-to-measure is a viewer feature.)
- **"Unknown layer" rows.** Add `classify_layer` rules for `*_Fab`, `*_Courtyard`, `User.*`, `*.Eco`,
  `Margin`, `Comments`; group documentation layers under a collapsible section.
- **Setup friction.** Remember last-used dirs (`initialdir`); default rev B's picker to rev A's
  parent (revisions are usually siblings); default the report next to rev B, not the temp dir.
- **Changed-area %** is divided by the full canvas (mostly empty), so it reads misleadingly tiny
  ("0.625%"). Denominate against inked area (`common+added+removed`) or drop it for absolute counts.
- **Option fields** (`dpmm`/`dpi`/`threshold`) are unlabelled jargon with silent fallback on bad
  input — add units/ranges, tooltips, and visible invalid-input feedback.
- **GUI screen-reader gap.** Tkinter exposes no accessibility tree; document the **CLI + `--json`**
  as the screen-reader-accessible path in the README rather than implying the GUI is accessible.

## P3 — Strategic

- **Ship the GitHub Action** (roadmap) — render the report, upload as artifact/Pages, post a PR
  comment with the per-layer summary (reuse `render_json`) + changed-layer thumbnails. The
  self-contained report is already the ideal CI artifact; this is where hardware-in-git review
  converges and where gerbdiff.com / KiRi currently win.
- **Git-ref inputs** — `gdiff <refA> <refB>` for repos that commit fab output.
- **PDF pairing beyond page index** — page-by-index XOR is fragile; pair by extracted sheet title
  and set expectations in the report header for PDF mode.

## Priority matrix

| # | Improvement | Impact | Effort | Tier |
|---|---|---|---|---|
| 1 | CVD-safe + redundant diff encoding | ★★★ | M | P0 |
| 2 | Co-registration warning/datum align | ★★★ | M | P0 |
| 3 | Compare button contrast + keyboard | ★★ | S | P0 |
| 4 | Lead-with-answer + A/B swipe/onion | ★★★ | M–L | P1 |
| 5 | Zoom/pan + changed-region marker | ★★★ | M | P1 |
| 6 | Loading/progress affordance | ★★ | S | P1 |
| 7 | Empty-state + error UX | ★★ | S–M | P1 |
| 8–15 | Design-system, semantics, measurement, classification, setup, % denom, SR docs, option labels | ★–★★ | S each | P2 |
| 16 | GitHub Action (PR comment) | ★★★ | L | P3 |

## Architecture verdict

Keep **Tkinter as a thin launcher** (it only needs last-dir memory, sibling-folder defaults,
tooltips, and the a11y fixes above) — do **not** build a rich pan/zoom viewer in Tkinter. The
static HTML report is at its ceiling for the core job; make **the report itself the rich viewer** —
a Canvas/pan-zoom layer inside the same self-contained file, fed the A raster, B raster, and overlay.
That keeps the killer "one file you can email for sign-off" property while delivering side-by-side,
swipe, onion-skin, zoom, and measurement.

## Accessibility appendix — key contrast computations

| Element | Colours | Ratio | AA? |
|---|---|---|---|
| GUI body text | `#e7e9ee` on `#16181d` | 14.6:1 | ✅ |
| Report body (light/dark) | `#1b2024`/`#e7e9ee` | 15.3:1 | ✅ |
| **Compare label** | `#ffffff` on `#4f8cff` | **3.22:1** | ❌ (AA text) |
| Compare label (hover) | `#ffffff` on `#6ba0ff` | 2.59:1 | ❌ |
| Compare (proposed) | `#ffffff` on `#2f6fe0` | 4.7:1 | ✅ |
| removed vs unchanged (overlay) | `#dc3232`/`#6e6e6e` | 1.10:1 | ❌ (graphic 3:1) |
| removed vs unchanged, protanopia | simulated | 1.09:1 | ❌ |

## Sources

- Colour-blind data viz: [Tableau — don't use red/green](https://www.tableau.com/blog/examining-data-viz-rules-dont-use-red-green-together),
  [colorblind-safe palettes (NCEAS)](https://www.nceas.ucsb.edu/sites/default/files/2022-06/Colorblind%20Safe%20Color%20Schemes.pdf)
- Image diff UX: [GitHub image view modes (2-up / swipe / onion-skin)](https://github.blog/news-insights/behold-image-view-modes/)
- Prior art: [gerbdiff.com](https://gerbdiff.com/), [KiRi](https://github.com/leoheck/kiri),
  [Altium Gerber Compare](https://www.altium.com/documentation/altium-365/viewers/standalone-gerber-compare)
- Toolkit: [PyQt vs Tkinter](https://www.pythonguis.com/faq/pyqt-vs-tkinter/)
