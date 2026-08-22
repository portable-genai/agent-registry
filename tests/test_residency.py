"""D5: residency is enforced by code at process start, not only by a Terraform comment.

The same allowlist appears in three places and these tests hold them together:

* ``infra/terraform/variables.tf`` validates ``region`` against ``allowed_regions`` at plan;
* ``infra/terraform/org_policy.tf`` derives the ``gcp.resourceLocations`` policy from it;
* :class:`agent_registry.config.Settings` refuses to load a region outside it.

Without the loader check, a mis-set ``GCP_REGION`` on a running service would silently point
the managed catalog at an unapproved region.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_registry.config import DEFAULT_ALLOWED_REGIONS, ResidencyError, Settings

CONFIG_PATH = Path(__file__).parents[1] / "config" / "settings.yaml"


def test_region_outside_allowlist_fails_closed_at_load() -> None:
    with pytest.raises(ResidencyError) as excinfo:
        Settings.from_dict({"region": "europe-west4", "allowed_regions": ["us-central1"]})
    message = str(excinfo.value)
    assert "europe-west4" in message
    assert "us-central1" in message


def test_env_selected_region_outside_allowlist_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("GCP_REGION", "asia-southeast1")
    monkeypatch.delenv("HRZ_REGISTRY_ALLOWED_REGIONS", raising=False)
    with pytest.raises(ResidencyError):
        Settings.load(CONFIG_PATH)


def test_region_inside_allowlist_loads() -> None:
    settings = Settings.from_dict(
        {"region": "europe-west4", "allowed_regions": "us-central1, europe-west4"}
    )
    assert settings.region == "europe-west4"
    assert settings.allowed_regions == ("us-central1", "europe-west4")


def test_allowlist_defaults_to_the_reference_region() -> None:
    settings = Settings.from_dict({})
    assert settings.allowed_regions == DEFAULT_ALLOWED_REGIONS
    assert settings.region in settings.allowed_regions


def test_shipped_settings_yaml_carries_the_allowlist() -> None:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    assert "allowed_regions: ${HRZ_REGISTRY_ALLOWED_REGIONS:-us-central1}" in text
