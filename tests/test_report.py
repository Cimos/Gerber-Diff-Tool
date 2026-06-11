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
