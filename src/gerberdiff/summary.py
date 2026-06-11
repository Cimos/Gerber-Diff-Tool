"""Render a compact Markdown summary of a diff — for PR comments / CI step summaries.

Plain GitHub-flavoured Markdown, no images: the verdict line, a table of the
changed layers/pages, warnings, and a pointer to the full HTML report artifact.
"""

from __future__ import annotations

from .models import DiffResult, LayerDiff, PairStatus


def _status_word(layer: LayerDiff) -> str:
    if layer.error:
        return "error"
    if layer.pair.status is PairStatus.ADDED:
        return "added"
    if layer.pair.status is PairStatus.REMOVED:
        return "removed"
    return "changed"


def render_markdown(result: DiffResult, *, report_hint: str | None = None) -> str:
    """Markdown summary of *result*. ``report_hint`` names where the full report lives."""
    subject = result.subject
    total = len(result.layers)
    changed = result.changed_layers

    lines: list[str] = []
    if not changed:
        lines.append(
            f"### ✅ gerber-diff: no changes across {total} {subject}{'s' if total != 1 else ''}"
        )
    else:
        lines.append(f"### ⚠️ gerber-diff: {len(changed)} of {total} {subject}s differ")
        lines.append("")
        lines.append(f"| {subject.title()} | Status | Added px | Removed px |")
        lines.append("|---|---|---:|---:|")
        for layer in changed:
            detail = ""
            if layer.error:
                detail = f" — `{layer.error}`"
            lines.append(
                f"| {layer.pair.layer_type}{detail} | {_status_word(layer)} "
                f"| {layer.added_pixels:,} | {layer.removed_pixels:,} |"
            )
        unchanged = total - len(changed)
        if unchanged:
            lines.append("")
            lines.append(
                f"{unchanged} unchanged {subject}{'s' if unchanged != 1 else ''} not shown."
            )

    warnings = [layer for layer in result.layers if layer.warning]
    if warnings:
        lines.append("")
        lines.append(
            f"> ⚠️ {len(warnings)} {subject}(s) may not be co-registered "
            "(different export origins) — the diff may overstate changes."
        )

    if result.resolution:
        lines.append("")
        lines.append(f"<sub>{result.resolution} · A: `{result.dir_a}` → B: `{result.dir_b}`</sub>")
    if report_hint:
        lines.append("")
        lines.append(f"Full visual report: {report_hint}")
    return "\n".join(lines) + "\n"
