"""Security guard: the builder must not bootstrap floating pip/uv. Build tooling
is pinned by copying uv from a digest-pinned image so builds stay reproducible
and cannot drift outside the lockfile/base-image digest (F-19).
Research use only; not clinical decision support."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # tests/unit/ -> repo root

_UV_PIN = (
    "ghcr.io/astral-sh/uv:0.8.7@sha256:"
    "1e26f9a868360eeb32500a35e05787ffff3402f01a8dc8168ef6aee44aef0aab"
)


def test_dockerfile_pins_uv_and_has_no_floating_pip_upgrade() -> None:
    text = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    assert "pip install --upgrade" not in text, "floating pip/uv upgrade must be removed"
    assert _UV_PIN in text, "uv must be copied from a digest-pinned image"


def test_prepared_stage_applies_current_debian_security_upgrades() -> None:
    """Fixable base-image vulnerabilities must be remediated before release."""
    text = (ROOT / "docker" / "Dockerfile").read_text(encoding="utf-8")
    prepared = text.split("FROM scratch AS production", 1)[0]

    assert "apt-get upgrade -y --no-install-recommends" in prepared
