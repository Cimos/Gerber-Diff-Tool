"""Tests for git-ref inputs: a real two-commit repo, materialized and diffed."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from gerberdiff.gitrefs import GitRefError, materialize_ref

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")

FIXTURES = Path(__file__).parent / "fixtures"


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


@pytest.fixture()
def gerber_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """A git repo whose ``fab/`` dir changes between two commits."""
    repo = tmp_path / "repo"
    fab = repo / "fab"
    fab.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    shutil.copy(FIXTURES / "revA" / "fixture-F_Cu.gbr", fab / "board-F_Cu.gbr")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "rev A")
    sha_a = _git(repo, "rev-parse", "HEAD")
    shutil.copy(FIXTURES / "revB" / "fixture-F_Cu.gbr", fab / "board-F_Cu.gbr")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "rev B")
    sha_b = _git(repo, "rev-parse", "HEAD")
    return repo, sha_a, sha_b


def test_materialize_ref_extracts_subdir(gerber_repo, tmp_path: Path):
    repo, sha_a, _sha_b = gerber_repo
    out = materialize_ref(sha_a, "fab", tmp_path / "x", repo_root=repo)
    assert (out / "board-F_Cu.gbr").is_file()


def test_materialize_unknown_ref_raises(gerber_repo, tmp_path: Path):
    repo, _a, _b = gerber_repo
    with pytest.raises(GitRefError, match="git archive failed"):
        materialize_ref("no-such-ref", "fab", tmp_path / "x", repo_root=repo)


def test_materialize_missing_subdir_raises(gerber_repo, tmp_path: Path):
    repo, sha_a, _b = gerber_repo
    with pytest.raises(GitRefError):
        materialize_ref(sha_a, "nonexistent", tmp_path / "x", repo_root=repo)


def test_cli_git_mode_end_to_end(gerber_repo, tmp_path: Path, monkeypatch):
    pytest.importorskip("pygerber")
    import json

    from gerberdiff.cli import main

    repo, sha_a, sha_b = gerber_repo
    monkeypatch.chdir(repo)  # gdiff resolves refs against the cwd repo
    out = tmp_path / "r.html"
    js = tmp_path / "r.json"
    code = main([sha_a, sha_b, "--git", "fab", "-o", str(out), "--json", str(js), "-q"])
    assert code == 0
    data = json.loads(js.read_text())
    assert data["any_changes"] is True  # the pad moved between commits
    assert data["old"].startswith(sha_a)  # report shows the ref, not a temp path
    assert "fab" in data["old"]
