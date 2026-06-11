"""Tests for the Markdown summary (PR comments / CI step summaries) and action.yml."""

from __future__ import annotations

from pathlib import Path

from gerberdiff.models import DiffResult, LayerDiff, LayerPair, PairStatus
from gerberdiff.summary import render_markdown

ROOT = Path(__file__).parent.parent


def _layer(key: str, *, added: int = 0, removed: int = 0, warning: str | None = None) -> LayerDiff:
    return LayerDiff(
        pair=LayerPair(
            key=key,
            layer_type=key.title(),
            status=PairStatus.MATCHED,
            path_a=Path("a"),
            path_b=Path("b"),
        ),
        width=10,
        height=10,
        added_pixels=added,
        removed_pixels=removed,
        common_pixels=5,
        warning=warning,
    )


def _result(layers: list[LayerDiff]) -> DiffResult:
    return DiffResult(
        dir_a=Path("A"), dir_b=Path("B"), resolution="20 dpmm", subject="layer", layers=layers
    )


def test_markdown_no_changes():
    md = render_markdown(_result([_layer("top copper")]))
    assert "✅" in md
    assert "no changes" in md
    assert "|" not in md  # no table when nothing changed


def test_markdown_changed_table():
    md = render_markdown(_result([_layer("top copper", removed=33704), _layer("top mask")]))
    assert "⚠️" in md and "1 of 2 layers differ" in md
    assert "| Top Copper" in md
    assert "33,704" in md
    assert "1 unchanged layer not shown" in md


def test_markdown_warning_and_hint():
    md = render_markdown(
        _result([_layer("top copper", added=1, warning="inputs not co-registered")]),
        report_hint="see the artifact",
    )
    assert "co-registered" in md
    assert "see the artifact" in md


def test_action_yml_is_valid_composite_action():
    yaml = __import__("yaml")
    data = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    assert data["runs"]["using"] == "composite"
    assert {"old", "new", "fail-on-diff", "comment"} <= set(data["inputs"])
    steps = data["runs"]["steps"]
    joined = str(steps)
    assert "github.action_path" in joined  # installs the package from the action checkout
    assert "GITHUB_STEP_SUMMARY" in joined
    assert "upload-artifact" in joined
    # every `run:` step in a composite action must declare a shell
    for step in steps:
        if "run" in step:
            assert "shell" in step, f"composite run step missing shell: {step.get('name')}"
