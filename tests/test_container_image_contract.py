"""D4: the shipped image is multi-stage, non-root, healthchecked and secure by default.

These assertions are on the Dockerfile text rather than a built image so they run in the
offline gate. They encode the four properties D4 names: a runtime stage that carries no build
toolchain, a dedicated non-root uid, a HEALTHCHECK against the API's own liveness route, and
the SECURE profile selected explicitly in the image (an image that defaults to the no-auth
SQLite laptop profile would silently start unauthenticated if a deployment env var is missed).
"""

from __future__ import annotations

import re
from pathlib import Path

DOCKERFILE = Path(__file__).parents[1] / "Dockerfile"
TEXT = DOCKERFILE.read_text(encoding="utf-8")


def _runtime_stage() -> str:
    """Everything from the last FROM onwards, i.e. the stage that actually ships."""
    return TEXT[TEXT.rindex("\nFROM ") :]


def test_build_is_multi_stage_and_runtime_copies_only_the_venv() -> None:
    stages = re.findall(r"^FROM .+ AS (\w+)$", TEXT, flags=re.MULTILINE)
    assert stages == ["builder", "runtime"]
    assert "COPY --from=builder /opt/venv /opt/venv" in _runtime_stage()


def test_runtime_stage_carries_no_build_toolchain() -> None:
    runtime = _runtime_stage()
    for tool in ("apt-get install", "git", "build-essential", "gcc"):
        assert tool not in runtime, f"runtime stage must not carry {tool}"


def test_container_runs_as_a_dedicated_non_root_uid() -> None:
    runtime = _runtime_stage()
    assert "USER 10001" in runtime
    assert "--uid 10001" in runtime
    assert "USER root" not in runtime


def test_image_declares_a_healthcheck_against_healthz() -> None:
    assert "HEALTHCHECK" in TEXT
    healthcheck = TEXT[TEXT.index("HEALTHCHECK") :]
    assert "/healthz" in healthcheck.split('\nCMD ["sh"')[0]


def test_image_selects_the_secure_profile_explicitly() -> None:
    runtime = _runtime_stage()
    assert "AGENT_REGISTRY_PROFILE=gcp" in runtime
    assert "AGENT_REGISTRY_PROFILE=local" not in runtime


def test_base_image_stays_digest_pinned() -> None:
    froms = re.findall(r"^FROM (\S+)", TEXT, flags=re.MULTILINE)
    assert froms, "expected at least one FROM"
    for image in froms:
        assert "@sha256:" in image, f"{image} must be digest-pinned"
