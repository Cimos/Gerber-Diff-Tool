"""Render a self-contained HTML diff report (all images embedded as base64).

The output is a single file with no external assets, a colour legend, a summary
table, and one card per layer (or PDF page). It supports light and dark themes:
it follows the OS preference by default and offers a manual toggle.
"""

from __future__ import annotations

import base64
import html

from .models import DiffResult, LayerDiff, PairStatus

_CSS = """
:root {
  --bg: #ffffff; --fg: #1c1c1e; --muted: #6b6b70; --card: #f5f5f7;
  --border: #d9d9de; --added: #1f9d3a; --removed: #d12f2f; --accent: #3b6ea5;
}
:root[data-theme="dark"] {
  --bg: #121214; --fg: #e6e6e8; --muted: #9a9aa0; --card: #1d1d20;
  --border: #2c2c31; --added: #36c759; --removed: #ff5b52; --accent: #5b9bd5;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #121214; --fg: #e6e6e8; --muted: #9a9aa0; --card: #1d1d20;
    --border: #2c2c31; --added: #36c759; --removed: #ff5b52; --accent: #5b9bd5;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 15px/1.5 -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }
header { padding: 24px 28px; border-bottom: 1px solid var(--border);
  display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }
h1 { font-size: 20px; margin: 0; }
.meta { color: var(--muted); font-size: 13px; }
main { padding: 24px 28px; max-width: 1100px; }
.legend { display: flex; gap: 18px; margin: 8px 0 20px; flex-wrap: wrap; font-size: 13px; }
.swatch { display: inline-block; width: 12px; height: 12px; border-radius: 3px;
  margin-right: 6px; vertical-align: middle; }
table { border-collapse: collapse; width: 100%; margin-bottom: 28px; font-size: 14px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }
th { color: var(--muted); font-weight: 600; }
.tag { font-size: 12px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border); }
.tag.changed { color: var(--removed); border-color: var(--removed); }
.tag.same { color: var(--muted); }
.tag.added { color: var(--added); border-color: var(--added); }
.tag.removed { color: var(--removed); border-color: var(--removed); }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 10px;
  padding: 16px; margin-bottom: 18px; }
.card h3 { margin: 0 0 6px; font-size: 16px; }
.card .sub { color: var(--muted); font-size: 13px; margin-bottom: 12px; }
.card img { max-width: 100%; height: auto; background: #000; border-radius: 6px;
  image-rendering: pixelated; }
.err { color: var(--removed); }
button { background: var(--card); color: var(--fg); border: 1px solid var(--border);
  border-radius: 8px; padding: 6px 12px; cursor: pointer; font-size: 13px; margin-left: auto; }
"""

_TOGGLE_JS = """
(function () {
  var btn = document.getElementById('theme-toggle');
  var root = document.documentElement;
  function current() {
    if (root.dataset.theme) return root.dataset.theme;
    return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  btn.addEventListener('click', function () {
    var next = current() === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    btn.textContent = next === 'dark' ? 'Light mode' : 'Dark mode';
  });
})();
"""


def _esc(text: str) -> str:
    return html.escape(str(text))


def _b64_png(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _status_tag(layer: LayerDiff) -> str:
    status = layer.pair.status
    if status is PairStatus.ADDED:
        return '<span class="tag added">added</span>'
    if status is PairStatus.REMOVED:
        return '<span class="tag removed">removed</span>'
    if layer.error:
        return '<span class="tag changed">error</span>'
    if layer.changed:
        return '<span class="tag changed">changed</span>'
    return '<span class="tag same">unchanged</span>'


def _summary_row(layer: LayerDiff) -> str:
    total = max(1, layer.width * layer.height)
    pct = 100.0 * layer.changed_pixels / total
    return (
        "<tr>"
        f"<td>{_esc(layer.pair.layer_type)}</td>"
        f"<td><code>{_esc(layer.pair.key)}</code></td>"
        f"<td>{_status_tag(layer)}</td>"
        f"<td>{layer.added_pixels:,}</td>"
        f"<td>{layer.removed_pixels:,}</td>"
        f"<td>{pct:.3f}%</td>"
        "</tr>"
    )


def _layer_card(layer: LayerDiff) -> str:
    if layer.error:
        body = f'<p class="err">Could not render this item: {_esc(layer.error)}</p>'
    elif layer.overlay_png is not None:
        body = f'<img alt="diff overlay" src="data:image/png;base64,{_b64_png(layer.overlay_png)}">'
    else:
        body = '<p class="sub">No overlay available.</p>'
    return (
        '<div class="card">'
        f"<h3>{_esc(layer.pair.layer_type)} {_status_tag(layer)}</h3>"
        f'<div class="sub"><code>{_esc(layer.pair.key)}</code> &middot; '
        f"+{layer.added_pixels:,} / &minus;{layer.removed_pixels:,} px</div>"
        f"{body}"
        "</div>"
    )


def render_html(
    result: DiffResult, *, title: str = "Gerber Diff Report", generated_at: str | None = None
) -> str:
    changed = result.changed_layers
    subject = result.subject
    summary = (
        f"{len(changed)} of {len(result.layers)} {subject}s differ"
        if result.layers
        else f"no {subject}s found"
    )
    rows = "\n".join(_summary_row(layer) for layer in result.layers)
    cards = "\n".join(
        _layer_card(layer) for layer in result.layers if layer.changed or layer.error
    )
    if not cards:
        cards = f'<p class="sub">No differences to show — every matched {subject} is identical.</p>'

    meta_when = f" &middot; generated {_esc(generated_at)}" if generated_at else ""
    resolution = f" &middot; {_esc(result.resolution)}" if result.resolution else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <h1>{_esc(title)}</h1>
  <span class="meta">{_esc(summary)}{resolution}{meta_when}</span>
  <button id="theme-toggle">Toggle theme</button>
</header>
<main>
  <div class="meta">A (old): <code>{_esc(result.dir_a)}</code> &nbsp; &rarr; &nbsp;
    B (new): <code>{_esc(result.dir_b)}</code></div>
  <div class="legend">
    <span><span class="swatch" style="background:var(--removed)"></span>removed (in A, not B)</span>
    <span><span class="swatch" style="background:var(--added)"></span>added (in B, not A)</span>
    <span><span class="swatch" style="background:#6e6e6e"></span>unchanged</span>
  </div>
  <table>
    <thead><tr><th>{_esc(subject.title())}</th><th>Source</th><th>Status</th>
      <th>Added px</th><th>Removed px</th><th>Changed area</th></tr></thead>
    <tbody>
{rows}
    </tbody>
  </table>
  {cards}
</main>
<script>{_TOGGLE_JS}</script>
</body>
</html>
"""
