"""Unit tests for the dataclasses and derived properties (stdlib only)."""

from __future__ import annotations

from pathlib import Path

from gerberdiff.models import DiffResult, LayerDiff, LayerPair, PairStatus


def _pair(status: PairStatus = PairStatus.MATCHED, key: str = "x") -> LayerPair:
    return LayerPair(key=key, layer_type="T", status=status, path_a=Path("a"), path_b=Path("b"))


def test_pairstatus_is_str_enum():
    assert PairStatus.MATCHED == "matched"
    assert PairStatus.ADDED.value == "added"
    assert PairStatus.REMOVED.value == "removed"


def test_layerdiff_changed_pixels_sum():
    diff = LayerDiff(pair=_pair(), added_pixels=3, removed_pixels=2)
    assert diff.changed_pixels == 5


def test_layerdiff_matched_unchanged_is_not_changed():
    diff = LayerDiff(pair=_pair())
    assert diff.changed_pixels == 0
    assert diff.changed is False


def test_layerdiff_matched_with_pixels_is_changed():
    assert LayerDiff(pair=_pair(), added_pixels=1).changed is True


def test_layerdiff_added_removed_always_changed_even_with_zero_pixels():
    assert LayerDiff(pair=_pair(PairStatus.ADDED)).changed is True
    assert LayerDiff(pair=_pair(PairStatus.REMOVED)).changed is True


def test_layerdiff_error_counts_as_changed():
    assert LayerDiff(pair=_pair(), error="boom").changed is True


def test_diffresult_changed_layers_and_any_changes():
    unchanged = LayerDiff(pair=_pair(PairStatus.MATCHED, "s"))
    changed = LayerDiff(pair=_pair(PairStatus.MATCHED, "c"), added_pixels=1)
    added = LayerDiff(pair=_pair(PairStatus.ADDED, "a"))
    result = DiffResult(
        dir_a=Path("A"),
        dir_b=Path("B"),
        resolution="20 dpmm",
        subject="layer",
        layers=[unchanged, changed, added],
    )
    assert result.any_changes is True
    assert {layer.pair.key for layer in result.changed_layers} == {"c", "a"}


def test_diffresult_defaults_and_empty():
    result = DiffResult(dir_a=Path("A"), dir_b=Path("B"))
    assert result.resolution == ""
    assert result.subject == "layer"
    assert result.layers == []
    assert result.any_changes is False
    assert result.changed_layers == []
