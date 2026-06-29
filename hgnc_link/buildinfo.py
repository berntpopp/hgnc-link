"""Build/version stamp so a running server can report its own provenance.

Provenance is injected by the Docker image build (``HGNC_LINK_GIT_SHA`` /
``HGNC_LINK_BUILT_AT``). In a source checkout those env vars are absent, so the
git sha is resolved from ``.git`` with a dependency-free reader and ``built_at``
falls back to the package mtime — the server can always say which build answered.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from hgnc_link import __version__


def _resolve_gitdir(git: Path) -> Path | None:
    """Return the real git directory, following a worktree gitlink ``.git`` file.

    A normal checkout has ``.git`` as a directory. A ``git worktree`` (and a
    shallow CI checkout that uses one) has ``.git`` as a *file* containing
    ``gitdir: <path>`` that points at ``…/.git/worktrees/<name>``.
    """
    if git.is_dir():
        return git
    try:
        text = git.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    target = Path(text[len("gitdir:") :].strip())
    if not target.is_absolute():
        target = (git.parent / target).resolve()
    return target if target.exists() else None


def _resolve_ref(ref: str, git_dir: Path, common_dir: Path) -> str | None:
    """Resolve a ``refs/…`` name via loose then packed refs (worktree-aware).

    Per-worktree refs may live in ``git_dir``; the checked-out branch's loose
    ref and ``packed-refs`` live in the shared ``common_dir``.
    """
    for base in (git_dir, common_dir):
        loose = base / ref
        if loose.exists():
            return loose.read_text(encoding="utf-8").strip()[:12]
    packed = common_dir / "packed-refs"
    if packed.exists():
        for line in packed.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith(("#", "^")) and line.endswith(ref):
                return line.split()[0][:12]
    return None


def _git_sha_from_dotgit() -> str | None:
    """Resolve the current commit sha by reading ``.git`` (no subprocess).

    Handles a normal ``.git`` directory, a detached HEAD, and a worktree
    gitlink where HEAD lives in the per-worktree dir while refs live in the
    shared common dir (``commondir``).
    """
    git = Path(__file__).resolve().parent.parent / ".git"
    if not git.exists():
        return None
    git_dir = _resolve_gitdir(git)
    if git_dir is None:
        return None
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            return head[:12]  # detached HEAD: raw sha
        ref = head[4:].strip()
        commondir = git_dir / "commondir"
        common_dir = (
            (git_dir / commondir.read_text(encoding="utf-8").strip()).resolve()
            if commondir.exists()
            else git_dir
        )
        return _resolve_ref(ref, git_dir, common_dir)
    except OSError:
        return None


def _built_at_fallback() -> str | None:
    """ISO-8601 mtime of the package as a best-effort build timestamp."""
    try:
        mtime = Path(__file__).with_name("__init__.py").stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=UTC).isoformat()
    except OSError:
        return None


def build_info() -> dict[str, str | None]:
    """Return version + git sha + build time (env-injected, else resolved locally)."""
    return {
        "version": __version__,
        "git_sha": os.environ.get("HGNC_LINK_GIT_SHA") or _git_sha_from_dotgit() or "unknown",
        "built_at": os.environ.get("HGNC_LINK_BUILT_AT") or _built_at_fallback(),
    }
