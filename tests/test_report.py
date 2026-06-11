"""Tests for HTML and JSON report rendering (no renderer needed)."""

from __future__ import annotations

import json
from pathlib import Path

from gerberdiff.models import DiffResult, LayerDiff, LayerPair, PairStatus
from gerberdiff.report import render_html, render_json


def _layer(
    key: str,
    *,
    status: PairStatus = PairStatus.MATCHED,
    added: int = 0,
    removed: int = 0,
    common: int = 0,
    error: str | None = None,
    overlay: bytes | None = b"PNGDATA",
    layer_type: str = "Top Copper",
    image_a: bytes | None = None,
    image_b: bytes | None = None,
) -> LayerDiff:
    return LayerDiff(
        pair=LayerPair(
            key=key, layer_type=layer_type, status=status, path_a=Path("a"), path_b=Path("b")
        ),
        width=10,
        height=10,
        added_pixels=added,
        removed_pixels=removed,
        common_pixels=common,
        overlay_png=overlay,
        image_a_png=image_a,
        image_b_png=image_b,
        error=error,
    )


def _result(
    layers: list[LayerDiff], *, subject: str = "layer", resolution: str = "20 dpmm"
) -> DiffResult:
    return DiffResult(
        dir_a=Path("A"), dir_b=Path("B"), resolution=resolution, subject=subject, layers=layers
    )


def test_render_json_structure_and_values():
    data = json.loads(render_json(_result([_layer("f_cu", added=5, removed=2, common=10)])))
    assert data["subject"] == "layer"
    assert data["resolution"] == "20 dpmm"
    assert data["any_changes"] is True
    assert data["summary"] == {"total": 1, "changed": 1}
    layer = data["layers"][0]
    assert layer["key"] == "f_cu"
    assert layer["status"] == "matched"
    assert layer["added_pixels"] == 5
    assert layer["removed_pixels"] == 2
    assert layer["common_pixels"] == 10
    assert layer["changed"] is True


def test_render_json_no_changes():
    data = json.loads(render_json(_result([_layer("f_cu")])))
    assert data["any_changes"] is False
    assert data["summary"]["changed"] == 0


def test_render_json_reports_errors():
    data = json.loads(render_json(_result([_layer("f_cu", error="ParseException: boom")])))
    assert data["layers"][0]["error"] == "ParseException: boom"
    assert data["layers"][0]["changed"] is True


def test_render_html_core_structure():
    html = render_html(_result([_layer("f_cu", added=5)]), generated_at="2026-01-01 00:00")
    assert "<!DOCTYPE html>" in html
    assert "Gerber Diff Report" in html
    assert "theme-toggle" in html  # dark/light toggle present
    assert "prefers-color-scheme" in html  # OS theme support
    assert "1 of 1 layers differ" in html
    assert "20 dpmm" in html
    assert "data:image/png;base64," in html  # overlay embedded for the changed layer


def test_render_html_subject_page_wording():
    html = render_html(_result([_layer("page-1", layer_type="Page 1", added=1)], subject="page"))
    assert "pages differ" in html
    assert "layers differ" not in html


def test_render_html_escapes_html_in_keys():
    html = render_html(_result([_layer("<script>&", added=1)]))
    assert "<script>&" not in html
    assert "&lt;script&gt;" in html


def test_render_html_no_changes_message():
    html = render_html(_result([_layer("f_cu")]))
    assert "No differences to show" in html


def test_render_html_error_layer_surfaced():
    html = render_html(_result([_layer("f_cu", error="ParseException: boom")]))
    assert "Could not render this item" in html
    assert "ParseException: boom" in html


def test_render_html_added_removed_tags_and_no_overlay():
    html = render_html(
        _result(
            [
                _layer("added-layer", status=PairStatus.ADDED, overlay=None),
                _layer("removed-layer", status=PairStatus.REMOVED, overlay=None),
            ]
        )
    )
    assert ">added</span>" in html
    assert ">removed</span>" in html
    assert "No overlay available" in html


def test_viewer_split_and_swipe_require_both_sides():
    html = render_html(_result([_layer("f_cu", added=1, image_a=b"A", image_b=b"B")]))
    assert 'data-mode="split"' in html
    assert 'data-mode="swipe"' in html
    assert 'class="stage s2"' in html  # second synchronized stage for Split


def test_viewer_one_sided_layer_has_no_split():
    html = render_html(_result([_layer("f_mask", status=PairStatus.ADDED, added=1, image_b=b"B")]))
    assert 'data-mode="split"' not in html
    assert 'data-mode="swipe"' not in html
    assert 'class="stage s2"' not in html
    assert 'data-mode="b"' in html  # B-only view still offered


def test_pdf_mode_shows_pairing_note():
    html_pdf = render_html(_result([_layer("page-1", layer_type="Page 1")], subject="page"))
    html_gerber = render_html(_result([_layer("f_cu")]))
    assert "paired by text content" in html_pdf
    assert "paired by text content" not in html_gerber


def test_render_html_is_well_formed():
    from html.parser import HTMLParser

    seen: list[tuple[str, str]] = []

    class _P(HTMLParser):
        def handle_starttag(self, tag, attrs):
            seen.append(("start", tag))

        def handle_endtag(self, tag):
            seen.append(("end", tag))

    _P().feed(render_html(_result([_layer("f_cu", added=5)])))  # must not raise
    for tag in ("html", "head", "body", "table", "div", "footer"):
        starts = sum(1 for kind, t in seen if kind == "start" and t == tag)
        ends = sum(1 for kind, t in seen if kind == "end" and t == tag)
        assert starts == ends, f"unbalanced <{tag}>: {starts} open vs {ends} close"


def test_render_html_stats_and_no_footer_without_timestamp():
    html = render_html(_result([_layer("f_cu", added=5)]))  # no generated_at
    assert 'class="stat"' in html
    assert "1 of 1 layers differ" in html
    assert "Generated" not in html


def test_render_json_layer_has_all_keys():
    data = json.loads(render_json(_result([_layer("f_cu", added=1)])))
    expected = {
        "key",
        "type",
        "status",
        "changed",
        "added_pixels",
        "removed_pixels",
        "common_pixels",
        "width",
        "height",
        "warning",
        "error",
    }
    assert set(data["layers"][0]) == expected
