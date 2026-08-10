"""Contract for the one-shot HGNC Link v2.1.3 GHCR alias recovery."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "recover-v2.1.3-alias.yml"
SOURCE_REVISION = "0f318f20ba6ecf81682919718a416e018f84fe98"
ACCEPTED_DIGEST = "sha256:1b9f67c4d072dc84071fa65e72bebb8449df9935504bc4e7e9c398719eb6f31a"
GH_SHA256 = "83d5c2ccad5498f58bf6368acb1ab32588cf43ab3a4b1c301bf36328b1c8bd60"
ORAS_SHA256 = "9ce999f8d2de03fc03968b29d743077a58783e545e5eaa53917ca177352d0e59"


def test_v213_alias_recovery_is_manual_digest_locked_and_non_deploying() -> None:
    assert WORKFLOW.is_file(), "the approved one-shot recovery workflow must exist"
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)

    # PyYAML 1.1 parses the unquoted key `on` as True; accept either spelling.
    trigger = workflow.get("on", workflow.get(True))
    assert trigger == {"workflow_dispatch": {}}
    assert workflow["permissions"] == {"contents": "read", "packages": "write"}

    assert set(workflow["jobs"]) == {"recover"}
    job = workflow["jobs"]["recover"]
    assert job["environment"] == "release"
    assert job["runs-on"] == "ubuntu-latest"
    assert job["timeout-minutes"] == 10

    script = "\n".join(step.get("run", "") for step in job["steps"])
    for required in (
        "ghcr.io/berntpopp/hgnc-link",
        "v2.1.3",
        "2.1.3",
        SOURCE_REVISION,
        f"sha-{SOURCE_REVISION}",
        ACCEPTED_DIGEST,
        "gh_version=2.96.0",
        "gh_${gh_version}_linux_amd64.tar.gz",
        GH_SHA256,
        "oras_version=1.3.3",
        "oras_${oras_version}_linux_amd64.tar.gz",
        ORAS_SHA256,
        'release verify "$release_tag"',
        'manifest fetch --descriptor "$image:$source_alias"',
        'blob fetch --output - "$image@$config_digest"',
        'Labels["org.opencontainers.image.revision"]',
        'cp "$image:$source_alias" "$image:$version_alias"',
        'test "$version_digest" = "$accepted_digest"',
    ):
        assert required in script

    lowered = text.lower()
    for forbidden in (
        "docker build",
        "docker compose",
        "docker push",
        "kubectl",
        "ansible",
        "gh release delete",
        "git tag",
        "workflow_call",
    ):
        assert forbidden not in lowered
