"""Render a self-contained HTML diff report (all images embedded as base64).

The output is a single file with no external assets: a header with summary
stat cards, a colour legend, a per-item table, and one card per changed layer
(or PDF page). It supports light and dark themes — it follows the OS preference
by default and offers a manual toggle.
"""

from __future__ import annotations

import base64
import html
import json

from .models import DiffResult, LayerDiff, PairStatus

_CSS = """
:root {
  --bg: #f6f7f9; --panel: #ffffff; --fg: #1b2024; --muted: #687078;
  --border: #e3e6ea; --row: #fafbfc; --hover: rgba(59,110,165,.08);
  --added: #1f9d3a; --removed: #d12f2f; --accent: #3b6ea5;
  --shadow: 0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.05);
}
:root[data-theme="dark"] {
  --bg: #121317; --panel: #1b1e24; --fg: #e7e9ee; --muted: #9aa0aa;
  --border: #2a2e36; --row: #20242b; --hover: rgba(91,155,213,.12);
  --added: #37c95a; --removed: #ff5b52; --accent: #5b9bd5;
  --shadow: 0 1px 2px rgba(0,0,0,.4);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #121317; --panel: #1b1e24; --fg: #e7e9ee; --muted: #9aa0aa;
    --border: #2a2e36; --row: #20242b; --hover: rgba(91,155,213,.12);
    --added: #37c95a; --removed: #ff5b52; --accent: #5b9bd5;
    --shadow: 0 1px 2px rgba(0,0,0,.4);
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
.wrap { max-width: 1120px; margin: 0 auto; padding: 30px 28px 64px; }
header { display: flex; align-items: center; gap: 12px; }
header h1 { font-size: 20px; font-weight: 700; margin: 0; letter-spacing: -.01em; }
.summary { color: var(--muted); font-size: 13px; margin: 4px 0 20px; }
button#theme-toggle { margin-left: auto; background: var(--panel); color: var(--fg);
  border: 1px solid var(--border); border-radius: 8px; padding: 7px 12px; cursor: pointer;
  font-size: 13px; box-shadow: var(--shadow); }
button#theme-toggle:hover { border-color: var(--accent); }
.stats { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 18px; }
.stat { background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
  padding: 12px 18px; box-shadow: var(--shadow); min-width: 92px; }
.stat .num { font-size: 24px; font-weight: 700; line-height: 1.1; }
.stat .num.changed { color: var(--removed); }
.stat .num.clean { color: var(--added); }
.stat .lbl { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .05em; margin-top: 2px; }
.paths { color: var(--muted); font-size: 13px; margin-bottom: 16px; }
code { font-family: ui-monospace, "SF Mono", "Cascadia Code", Consolas, monospace; font-size: 12.5px; }
.legend { display: flex; gap: 18px; margin-bottom: 18px; flex-wrap: wrap; font-size: 13px; color: var(--muted); }
.swatch { display: inline-block; width: 11px; height: 11px; border-radius: 3px; margin-right: 6px; vertical-align: middle; }
table { width: 100%; border-collapse: separate; border-spacing: 0; background: var(--panel);
  border: 1px solid var(--border); border-radius: 12px; overflow: hidden; box-shadow: var(--shadow); margin-bottom: 28px; }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border); }
thead th { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); background: var(--row); font-weight: 600; }
tbody tr:nth-child(even) { background: var(--row); }
tbody tr:hover { background: var(--hover); }
tbody tr:last-child td { border-bottom: none; }
td.num { font-variant-numeric: tabular-nums; }
.pill { font-size: 11.5px; font-weight: 600; padding: 2px 9px; border-radius: 999px;
  border: 1px solid var(--border); white-space: nowrap; }
.pill.changed { color: var(--removed); border-color: var(--removed); }
.pill.same { color: var(--muted); }
.pill.added { color: var(--added); border-color: var(--added); }
.pill.removed { color: var(--removed); border-color: var(--removed); }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 14px;
  padding: 18px; margin-bottom: 18px; box-shadow: var(--shadow); }
.card h3 { margin: 0 0 4px; font-size: 15px; display: flex; align-items: center; gap: 8px; }
.card .sub { color: var(--muted); font-size: 12.5px; margin-bottom: 12px; }
.card img { max-width: 100%; height: auto; background: #0c0d10; border: 1px solid var(--border);
  border-radius: 8px; image-rendering: pixelated; display: block; }
.err { color: var(--removed); }
footer { color: var(--muted); font-size: 12px; margin-top: 8px; }
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


def _esc(text: object) -> str:
    return html.escape(str(text))


def _b64_png(data: bytes) -> str:
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


def _summary_row(layer: LayerDiff) -> str:
    total = max(1, layer.width * layer.height)
    pct = 100.0 * layer.changed_pixels / total
    return (
        "<tr>"
        f"<td>{_esc(layer.pair.layer_type)}</td>"
        f"<td><code>{_esc(layer.pair.key)}</code></td>"
        f"<td>{_status_pill(layer)}</td>"
        f'<td class="num">{layer.added_pixels:,}</td>'
        f'<td class="num">{layer.removed_pixels:,}</td>'
        f'<td class="num">{pct:.3f}%</td>'
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
        f"<h3>{_esc(layer.pair.layer_type)} {_status_pill(layer)}</h3>"
        f'<div class="sub"><code>{_esc(layer.pair.key)}</code> &middot; '
        f"+{layer.added_pixels:,} added / &minus;{layer.removed_pixels:,} removed px</div>"
        f"{body}"
        "</div>"
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
                "error": layer.error,
            }
            for layer in result.layers
        ],
    }
    return json.dumps(payload, indent=2)


def render_html(
    result: DiffResult, *, title: str = "Gerber Diff Report", generated_at: str | None = None
) -> str:
    changed = result.changed_layers
    total = len(result.layers)
    subject = result.subject
    summary = (
        f"{len(changed)} of {total} {subject}s differ" if result.layers else f"no {subject}s found"
    )
    rows = "\n".join(_summary_row(layer) for layer in result.layers)
    cards = "\n".join(_layer_card(layer) for layer in result.layers if layer.changed or layer.error)
    if not cards:
        cards = f'<p class="sub">No differences to show — every matched {subject} is identical.</p>'

    stats = (
        _stat(str(len(changed)), "changed", "changed" if changed else "clean")
        + _stat(str(total), subject + ("s" if total != 1 else ""))
        + (_stat(result.resolution, "resolution") if result.resolution else "")
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
    <h1>{_esc(title)}</h1>
    <button id="theme-toggle">Toggle theme</button>
  </header>
  <div class="summary">{_esc(summary)}</div>
  <div class="stats">{stats}</div>
  <div class="paths">A (old): <code>{_esc(result.dir_a)}</code> &nbsp;&rarr;&nbsp;
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
  <footer>{footer}</footer>
</div>
<script>{_TOGGLE_JS}</script>
</body>
</html>
"""
