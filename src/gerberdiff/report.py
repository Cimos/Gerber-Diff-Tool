"""Render a self-contained HTML diff report (all images embedded as base64).

One file, no external assets: a header with summary stat cards, a colour legend,
a changed-first per-item table (with an "only changed" filter and jump links),
and one interactive card per changed layer/page — an A / B / Swipe / Onion /
Overlay comparator with pan-zoom and keyboard support. Light and dark themes
(OS preference + manual toggle). The diff encoding is colour-blind-safe
(blue added / orange-hatched removed), matching gerberdiff.diff.
"""

from __future__ import annotations

import base64
import html
import json

from .models import DiffResult, LayerDiff, PairStatus

_CSS = """
:root {
  --bg:#f6f7f9; --panel:#fff; --fg:#1b2024; --muted:#687078; --border:#e3e6ea;
  --row:#fafbfc; --hover:rgba(47,111,224,.07);
  --added:#1668d6; --removed:#b35a00; --ok:#1f9d3a; --accent:#2f6fe0;
  --shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.05);
}
:root[data-theme="dark"] { --bg:#121317; --panel:#1b1e24; --fg:#e7e9ee; --muted:#9aa0aa;
  --border:#2a2e36; --row:#20242b; --hover:rgba(91,155,255,.12);
  --added:#5b9bff; --removed:#ff9e3d; --ok:#3fb950; --accent:#5b9bff;
  --shadow:0 1px 2px rgba(0,0,0,.4); }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#121317; --panel:#1b1e24; --fg:#e7e9ee; --muted:#9aa0aa;
  --border:#2a2e36; --row:#20242b; --hover:rgba(91,155,255,.12);
  --added:#5b9bff; --removed:#ff9e3d; --ok:#3fb950; --accent:#5b9bff;
  --shadow:0 1px 2px rgba(0,0,0,.4); } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
.wrap { max-width:1120px; margin:0 auto; padding:30px 28px 64px; }
header { display:flex; align-items:baseline; gap:10px; }
header h1 { font-size:20px; font-weight:700; margin:0; letter-spacing:-.01em; }
header .word { color:var(--muted); font-size:14px; }
button#theme-toggle { margin-left:auto; background:var(--panel); color:var(--fg);
  border:1px solid var(--border); border-radius:8px; padding:7px 12px; cursor:pointer; font-size:13px; box-shadow:var(--shadow); }
button#theme-toggle:hover { border-color:var(--accent); }
:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.summary { color:var(--muted); font-size:13px; margin:6px 0 18px; }
.banner { background:var(--panel); border:1px solid var(--removed); border-left-width:4px;
  border-radius:8px; padding:10px 14px; margin-bottom:18px; font-size:13px; }
.stats { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:18px; }
.stat { background:var(--panel); border:1px solid var(--border); border-radius:12px;
  padding:12px 18px; box-shadow:var(--shadow); min-width:92px; }
.stat .num { font-size:24px; font-weight:700; line-height:1.1; }
.stat .num.changed { color:var(--removed); } .stat .num.clean { color:var(--ok); }
.stat .lbl { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; margin-top:2px; }
.paths { color:var(--muted); font-size:13px; margin-bottom:14px; }
code { font-family:ui-monospace,"Cascadia Code",Consolas,monospace; font-size:12.5px; }
.controls { display:flex; align-items:center; gap:14px; margin-bottom:10px; flex-wrap:wrap; }
.legend { display:flex; gap:16px; flex-wrap:wrap; font-size:13px; color:var(--muted); }
.filter { font-size:13px; color:var(--fg); cursor:pointer; user-select:none; }
.swatch { display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:6px; vertical-align:middle; }
.swatch.added { background:var(--added); }
.swatch.removed { background-color:var(--removed);
  background-image:repeating-linear-gradient(45deg,rgba(0,0,0,.5) 0 2px,transparent 2px 4px); }
.swatch.common { background:#6e6e6e; }
table { width:100%; border-collapse:separate; border-spacing:0; background:var(--panel);
  border:1px solid var(--border); border-radius:12px; overflow:hidden; box-shadow:var(--shadow); margin-bottom:28px; }
th, td { padding:10px 14px; text-align:left; border-bottom:1px solid var(--border); font-weight:400; }
thead th { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); background:var(--row); font-weight:600; }
tbody tr:nth-child(even) { background:var(--row); }
tbody tr:hover { background:var(--hover); }
tbody tr.changed th[scope="row"] { box-shadow:inset 3px 0 0 var(--removed); }
tbody tr:last-child td, tbody tr:last-child th { border-bottom:none; }
td.num { font-variant-numeric:tabular-nums; }
th[scope="row"] a { color:var(--accent); text-decoration:none; }
th[scope="row"] a:hover { text-decoration:underline; }
table.hide-unchanged tr.unchanged { display:none; }
.card { background:var(--panel); border:1px solid var(--border); border-radius:14px;
  padding:18px; margin-bottom:18px; box-shadow:var(--shadow); }
.card h3 { margin:0 0 4px; font-size:15px; display:flex; align-items:center; gap:8px; }
.card .sub { color:var(--muted); font-size:12.5px; margin-bottom:10px; }
.warn { color:var(--removed); font-size:12.5px; margin-bottom:10px; }
.err { color:var(--removed); }
.viewer .vtoolbar { display:flex; gap:6px; align-items:center; flex-wrap:wrap; margin-bottom:8px; }
.viewer .vtoolbar button { font-size:12px; padding:5px 10px; border:1px solid var(--border);
  border-radius:7px; background:var(--panel); color:var(--fg); cursor:pointer; }
.viewer .vtoolbar button[aria-pressed="true"] { background:var(--accent); color:#fff; border-color:var(--accent); }
.viewer .slider { flex:1; min-width:120px; max-width:300px; accent-color:var(--accent); }
.viewer .hint { color:var(--muted); font-size:11.5px; }
.stages { display:flex; gap:8px; }
.stages .stage { flex:1; min-width:0; }
.stage { position:relative; overflow:hidden; background:#0c0d10; border:1px solid var(--border);
  border-radius:8px; cursor:grab; }
.stage.grabbing { cursor:grabbing; }
.stage[hidden] { display:none; }
.stage.s2 .pan img.ib { position:static; }
.stage[data-label]::after { content:attr(data-label); position:absolute; top:6px; left:6px;
  background:rgba(12,13,16,.78); color:#e7e9ee; font-size:11px; padding:2px 8px;
  border-radius:6px; pointer-events:none; z-index:1; }
.pan { transform-origin:0 0; }
.pan img { display:block; width:100%; height:auto; image-rendering:pixelated; }
.pan img.ia, .pan img.ib { position:absolute; top:0; left:0; }
footer { color:var(--muted); font-size:12px; margin-top:8px; }
"""

_JS = """
(function () {
  var root = document.documentElement, tbtn = document.getElementById('theme-toggle');
  function curTheme() {
    return root.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  }
  function syncToggle() {
    if (!tbtn) return;
    var dark = curTheme() === 'dark';
    tbtn.textContent = dark ? 'Light mode' : 'Dark mode';
    tbtn.setAttribute('aria-pressed', String(dark));
  }
  if (tbtn) { tbtn.addEventListener('click', function () {
    root.dataset.theme = curTheme() === 'dark' ? 'light' : 'dark'; syncToggle();
  }); syncToggle(); }

  var flt = document.getElementById('only-changed'), tbl = document.getElementById('layers');
  function applyFilter() { if (tbl) tbl.classList.toggle('hide-unchanged', !!(flt && flt.checked)); }
  if (flt) { flt.addEventListener('change', applyFilter); applyFilter(); }

  document.querySelectorAll('.viewer').forEach(function (v) {
    var stages = Array.prototype.slice.call(v.querySelectorAll('.stage'));
    var pans = stages.map(function (s) { return s.querySelector('.pan'); });
    var stageB = v.querySelector('.stage.s2');
    var panB = stageB ? stageB.querySelector('.pan') : null;
    var slider = v.querySelector('.slider');
    var ov = v.querySelector('.ov'), a = v.querySelector('.ia'), b = v.querySelector('.ib');
    var mode = 'overlay', scale = 1, tx = 0, ty = 0;
    function render() {
      var s = +slider.value;
      var split = mode === 'split';
      if (stageB) {
        stageB.hidden = !split;
        // Split reuses the embedded B image by moving the node — no duplication.
        if (split && b && panB && b.parentNode !== panB) panB.appendChild(b);
        if (!split && b && b.parentNode !== pans[0]) pans[0].appendChild(b);
        if (split) { stages[0].dataset.label = 'A (old)'; stageB.dataset.label = 'B (new)'; }
        else { delete stages[0].dataset.label; delete stageB.dataset.label; }
      }
      if (ov) ov.style.opacity = mode === 'overlay' ? 1 : 0;
      if (b) b.style.opacity = (mode === 'b' || mode === 'swipe' || mode === 'onion' || split) ? 1 : 0;
      if (a) {
        if (mode === 'a' || split) { a.style.opacity = 1; a.style.clipPath = 'none'; }
        else if (mode === 'swipe') { a.style.opacity = 1; a.style.clipPath = 'inset(0 ' + (100 - s) + '% 0 0)'; }
        else if (mode === 'onion') { a.style.opacity = s / 100; a.style.clipPath = 'none'; }
        else { a.style.opacity = 0; a.style.clipPath = 'none'; }
      }
      slider.style.display = (mode === 'swipe' || mode === 'onion') ? '' : 'none';
      var t = 'translate(' + tx + 'px,' + ty + 'px) scale(' + scale + ')';
      pans.forEach(function (p) { if (p) p.style.transform = t; });  // stages stay in sync
    }
    v.querySelectorAll('[data-mode]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        mode = btn.dataset.mode;
        v.querySelectorAll('[data-mode]').forEach(function (o) { o.setAttribute('aria-pressed', String(o === btn)); });
        render();
      });
    });
    slider.addEventListener('input', render);
    stages.forEach(function (stage) {
      stage.addEventListener('wheel', function (e) {
        e.preventDefault();
        scale = Math.min(20, Math.max(1, scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
        if (scale === 1) { tx = 0; ty = 0; }
        render();
      }, { passive: false });
      var drag = false, lx = 0, ly = 0;
      stage.addEventListener('mousedown', function (e) { drag = true; lx = e.clientX; ly = e.clientY; stage.classList.add('grabbing'); });
      window.addEventListener('mousemove', function (e) { if (!drag) return; tx += e.clientX - lx; ty += e.clientY - ly; lx = e.clientX; ly = e.clientY; render(); });
      window.addEventListener('mouseup', function () { drag = false; stage.classList.remove('grabbing'); });
      stage.addEventListener('dblclick', function () { scale = 1; tx = 0; ty = 0; render(); });
      stage.addEventListener('keydown', function (e) {
        var step = 30 / scale;
        if (e.key === '+' || e.key === '=') scale = Math.min(20, scale * 1.15);
        else if (e.key === '-') scale = Math.max(1, scale / 1.15);
        else if (e.key === 'ArrowLeft') tx += step; else if (e.key === 'ArrowRight') tx -= step;
        else if (e.key === 'ArrowUp') ty += step; else if (e.key === 'ArrowDown') ty -= step;
        else if (e.key === '0') { scale = 1; tx = 0; ty = 0; }
        else return;
        e.preventDefault(); render();
      });
    });
    render();
  });
})();
"""


def _esc(text: object) -> str:
    return html.escape(str(text))


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _status_pill(layer: LayerDiff) -> str:
    status = layer.pair.status
    if status is PairStatus.ADDED:
        return '<span class="pill added">added</span>'
    if status is PairStatus.REMOVED:
        return '<span class="pill removed">removed</span>'
    if layer.error:
        return '<span class="pill changed">error</span>'
    if layer.changed:
        return '<span class="pill changed">changed</span>'
    return '<span class="pill same">unchanged</span>'


def _summary_row(layer: LayerDiff, idx: int) -> str:
    inked = max(1, layer.added_pixels + layer.removed_pixels + layer.common_pixels)
    pct = 100.0 * layer.changed_pixels / inked
    name = _esc(layer.pair.layer_type)
    if layer.changed and not layer.error and layer.overlay_png is not None:
        name = f'<a href="#card-{idx}">{name}</a>'
    row_cls = "" if layer.changed else "unchanged"
    return (
        f'<tr class="{row_cls}">'
        f'<th scope="row">{name}</th>'
        f"<td><code>{_esc(layer.pair.key)}</code></td>"
        f"<td>{_status_pill(layer)}</td>"
        f'<td class="num">{layer.added_pixels:,}</td>'
        f'<td class="num">{layer.removed_pixels:,}</td>'
        f'<td class="num">{pct:.2f}%</td>'
        "</tr>"
    )


def _viewer(layer: LayerDiff) -> str:
    has_a = layer.image_a_png is not None
    has_b = layer.image_b_png is not None
    imgs = [
        f'<img class="ov" alt="diff overlay" src="data:image/png;base64,{_b64(layer.overlay_png)}">'
    ]
    if has_a:
        imgs.append(
            f'<img class="ia" alt="revision A" src="data:image/png;base64,{_b64(layer.image_a_png)}">'
        )
    if has_b:
        imgs.append(
            f'<img class="ib" alt="revision B" src="data:image/png;base64,{_b64(layer.image_b_png)}">'
        )
    modes = [("overlay", "Overlay")]
    if has_a and has_b:
        modes += [("split", "Split"), ("swipe", "Swipe"), ("onion", "Onion")]
    if has_a:
        modes.append(("a", "A (old)"))
    if has_b:
        modes.append(("b", "B (new)"))
    buttons = "".join(
        f'<button type="button" data-mode="{m}" aria-pressed="{"true" if m == "overlay" else "false"}">{_esc(lbl)}</button>'
        for m, lbl in modes
    )
    # Second stage for Split: empty until the JS moves the B image into it.
    second = (
        '<div class="stage s2" tabindex="0" aria-label="revision B, zoomable" hidden>'
        '<div class="pan"></div></div>'
        if has_a and has_b
        else ""
    )
    return (
        '<div class="viewer">'
        f'<div class="vtoolbar">{buttons}'
        '<input class="slider" type="range" min="0" max="100" value="50" '
        'aria-label="comparison position" style="display:none">'
        '<span class="hint">scroll = zoom, drag = pan</span></div>'
        '<div class="stages">'
        '<div class="stage" tabindex="0" aria-label="diff image, zoomable">'
        f'<div class="pan">{"".join(imgs)}</div></div>'
        f"{second}"
        "</div></div>"
    )


def _layer_card(layer: LayerDiff, idx: int) -> str:
    sub_bits = [f"<code>{_esc(layer.pair.key)}</code>"]
    if layer.changed and not layer.error:
        sub_bits.append(
            f"+{layer.added_pixels:,} added / &minus;{layer.removed_pixels:,} removed px"
        )
    if layer.changed_size_mm:
        w, h = layer.changed_size_mm
        sub_bits.append(f"change spans {w:.1f} &times; {h:.1f} mm")
    warn = f'<div class="warn">&#9888; {_esc(layer.warning)}</div>' if layer.warning else ""
    if layer.error:
        body = f'<p class="err">Could not render this item: {_esc(layer.error)}</p>'
    elif layer.overlay_png is not None:
        body = _viewer(layer)
    else:
        body = '<p class="sub">No overlay available.</p>'
    return (
        f'<div class="card" id="card-{idx}">'
        f"<h3>{_esc(layer.pair.layer_type)} {_status_pill(layer)}</h3>"
        f'<div class="sub">{" &middot; ".join(sub_bits)}</div>'
        f"{warn}{body}</div>"
    )


def _stat(num: str, label: str, cls: str = "") -> str:
    return f'<div class="stat"><div class="num {cls}">{_esc(num)}</div><div class="lbl">{_esc(label)}</div></div>'


def render_json(result: DiffResult) -> str:
    """Machine-readable summary of a diff (no images) — for CI / automation."""
    payload = {
        "subject": result.subject,
        "resolution": result.resolution,
        "old": str(result.dir_a),
        "new": str(result.dir_b),
        "any_changes": result.any_changes,
        "summary": {"total": len(result.layers), "changed": len(result.changed_layers)},
        "layers": [
            {
                "key": layer.pair.key,
                "type": layer.pair.layer_type,
                "status": layer.pair.status.value,
                "changed": layer.changed,
                "added_pixels": layer.added_pixels,
                "removed_pixels": layer.removed_pixels,
                "common_pixels": layer.common_pixels,
                "width": layer.width,
                "height": layer.height,
                "warning": layer.warning,
                "error": layer.error,
            }
            for layer in result.layers
        ],
    }
    return json.dumps(payload, indent=2)


def render_html(
    result: DiffResult, *, title: str = "Gerber Diff Report", generated_at: str | None = None
) -> str:
    ordered = sorted(result.layers, key=lambda lyr: not lyr.changed)  # changed first (stable)
    changed = result.changed_layers
    total = len(result.layers)
    subject = result.subject
    summary = (
        f"{len(changed)} of {total} {subject}s differ" if result.layers else f"no {subject}s found"
    )
    rows = "\n".join(_summary_row(layer, i) for i, layer in enumerate(ordered))
    cards = "\n".join(
        _layer_card(layer, i) for i, layer in enumerate(ordered) if layer.changed or layer.error
    )
    if not cards:
        cards = f'<p class="sub">No differences to show — every matched {subject} is identical.</p>'

    n_unchanged = total - len(changed)
    filter_html = ""
    if n_unchanged:
        checked = "checked" if (changed and n_unchanged) else ""
        filter_html = (
            f'<label class="filter"><input type="checkbox" id="only-changed" {checked}> '
            f"Only changed</label>"
        )

    stats = (
        _stat(str(len(changed)), "changed", "changed" if changed else "clean")
        + _stat(str(total), subject + ("s" if total != 1 else ""))
        + (_stat(result.resolution, "resolution") if result.resolution else "")
    )
    pairing_note = (
        "<br><span>Note: PDF pages are paired by index — an inserted or removed page "
        "offsets every later comparison.</span>"
        if subject == "page"
        else ""
    )
    n_warn = sum(1 for lyr in result.layers if lyr.warning)
    banner = (
        f'<div class="banner">&#9888; {n_warn} {subject}(s) may not be co-registered '
        "— a coordinate shift can look like a full-layer change. See the notes below.</div>"
        if n_warn
        else ""
    )
    footer = f"Generated {_esc(generated_at)}" if generated_at else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>gerber-diff</h1><span class="word">report</span>
    <button id="theme-toggle" aria-pressed="false">Toggle theme</button>
  </header>
  <div class="summary">{_esc(summary)}</div>
  {banner}
  <div class="stats">{stats}</div>
  <div class="paths">A (old): <code>{_esc(result.dir_a)}</code> &nbsp;&rarr;&nbsp;
    B (new): <code>{_esc(result.dir_b)}</code>{pairing_note}</div>
  <div class="controls">
    {filter_html}
    <div class="legend">
      <span><span class="swatch removed"></span>removed (in A, not B)</span>
      <span><span class="swatch added"></span>added (in B, not A)</span>
      <span><span class="swatch common"></span>unchanged</span>
    </div>
  </div>
  <table id="layers">
    <caption class="sr-only" style="position:absolute;left:-9999px">Per-layer diff summary</caption>
    <thead><tr><th scope="col">{_esc(subject.title())}</th><th scope="col">Source</th>
      <th scope="col">Status</th><th scope="col">Added px</th><th scope="col">Removed px</th>
      <th scope="col">Changed area</th></tr></thead>
    <tbody>
{rows}
    </tbody>
  </table>
  {cards}
  <footer>{footer}</footer>
</div>
<script>{_JS}</script>
</body>
</html>
"""
