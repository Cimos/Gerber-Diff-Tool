"""Materialize a directory from a git ref so two revisions can be diffed.

``gdiff v1.0 HEAD --git gerbers/`` extracts ``gerbers/`` as it exists at each
ref into a temporary directory using ``git archive`` (read-only — no worktree
or checkout juggling) and diffs the two extractions.
"""

from __future__ import annotations

import subprocess
import tarfile
from io import BytesIO
from pathlib import Path


class GitRefError(ValueError):
    """A git ref could not be materialized; the message is user-actionable."""


def materialize_ref(ref: str, subdir: str, dest: Path, *, repo_root: Path | None = None) -> Path:
    """Extract *subdir* as it exists at *ref* into *dest*; return the subdir path.

    *dest* is caller-owned (typically a ``TemporaryDirectory``), so cleanup
    stays with the caller. Raises :class:`GitRefError` when git is missing, the
    ref is unknown, or the path doesn't exist at that ref.
    """
    subdir = subdir.replace("\\", "/").strip("/") or "."
    cwd = Path(repo_root) if repo_root else Path.cwd()
    try:
        proc = subprocess.run(
            ["git", "archive", "--format=tar", ref, "--", subdir],
            cwd=cwd,
            capture_output=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise GitRefError("git is not installed or not on PATH") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="replace").strip()
        raise GitRefError(f"git archive failed for {ref!r}: {detail}")

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=BytesIO(proc.stdout)) as tar:
        tar.extractall(dest, filter="data")  # "data" blocks links/devices/abs paths

    out = (dest / subdir).resolve() if subdir != "." else dest
    if not out.is_dir():
        raise GitRefError(f"{subdir!r} does not exist at {ref!r} (nothing was extracted)")
    return out
