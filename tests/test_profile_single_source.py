"""The profile has ONE source of truth, and it fails closed on an unset variable.

Mirrors Hrz7 (``human-review-console/tests/test_profile_single_source.py``) as the
standing gate for the absence-read-as-consent class.

The defect this guards: reading ``HRZ_REGISTRY_PROFILE`` as a two-state value with ``local``
as the default, whether in ``config/settings.yaml`` interpolation, in ``Settings.from_dict``,
or in ``__main__.py``. ``local`` is exactly the profile the S2S rule grants an opening to when
``HRZ_REGISTRY_S2S_TOKEN`` is unset, so a deployment whose configuration never arrived would
accept catalog writes from any caller with no credential at all. A drift guard is part of the
defence, because any module that re-derives the profile with its own permissive default can
reintroduce the whole class in one line.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from hex_service_kit.netdefaults import ConfiguredEmptyError

from agent_registry.api.app import create_app
from agent_registry.config import (
    RUNTIME_PROFILES,
    UNCONSENTED_PROFILE,
    ProfileError,
    Settings,
    _interpolate,
    resolve_profile,
)
from conftest import LOOPBACK_PEER

_SRC = Path(__file__).resolve().parents[1] / "src" / "agent_registry"
_CONFIG = _SRC / "config.py"
_SETTINGS_YAML = _SRC.parents[1] / "config" / "settings.yaml"
_ENV_EXAMPLE = _SRC.parents[1] / ".env.example"


def _python_sources() -> list[Path]:
    return sorted(p for p in _SRC.rglob("*.py") if p != _CONFIG)


def test_only_the_resolver_reads_the_profile_variable_from_the_environment() -> None:
    offenders = []
    for path in _python_sources():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if re.search(r"(os\.environ|os\.getenv)[^\n]*PROFILE", line):
                offenders.append(f"{path.relative_to(_SRC)}:{number}: {line.strip()}")
    assert not offenders, (
        "these modules re-derive the profile instead of calling config.resolve_profile, "
        "so an unset HRZ_REGISTRY_PROFILE can again be read as consent:\n" + "\n".join(offenders)
    )


def test_the_settings_file_declares_no_permissive_profile_default() -> None:
    """``${HRZ_REGISTRY_PROFILE:-local}`` in the YAML is the same fail-open, one layer down."""
    match = re.search(
        r"^profile:\s*(\S+)", _SETTINGS_YAML.read_text(encoding="utf-8"), flags=re.MULTILINE
    )
    assert match is not None, "config/settings.yaml must still declare a profile key"
    assert match.group(1) == "${HRZ_REGISTRY_PROFILE:-}", (
        "the settings file supplies a default for the profile, so an unset variable is "
        f"indistinguishable from a chosen one: {match.group(1)}"
    )


def test_the_resolver_treats_an_absent_variable_as_no_choice() -> None:
    choice = resolve_profile(environ={})
    assert choice.explicit is False
    assert choice.service_auth_configured is False


@pytest.mark.parametrize("blank", ["", "   "])
def test_the_resolver_refuses_a_configured_empty_profile(blank: str) -> None:
    with pytest.raises(ProfileError, match="HRZ_REGISTRY_PROFILE"):
        resolve_profile(environ={"HRZ_REGISTRY_PROFILE": blank})


def test_interpolation_defaults_only_when_the_variable_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "HRZ_REGISTRY_THREE_STATE_PROBE"
    monkeypatch.delenv(name, raising=False)
    assert _interpolate(f"${{{name}:-documented}}") == "documented"
    monkeypatch.setenv(name, "")
    # ConfiguredEmptyError is a RuntimeError, not a ValueError: the loader now delegates the
    # refusal to the one canonical `setting_or_default` instead of raising its own ValueError.
    with pytest.raises(ConfiguredEmptyError, match=name):
        _interpolate(f"${{{name}:-documented}}")
    monkeypatch.setenv(name, "reviewed")
    assert _interpolate(f"${{{name}:-documented}}") == "reviewed"


def test_example_file_does_not_export_optional_values_as_configured_empty() -> None:
    active_blanks = [
        line
        for line in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if re.fullmatch(r"[A-Z][A-Z0-9_]*=\s*(?:#.*)?", line)
    ]
    assert active_blanks == [], (
        "comment optional example values out: loading NAME= configures an empty runtime value "
        f"and must refuse, it does not mean unset: {active_blanks}"
    )


def test_an_unconsented_run_is_not_the_local_profile_for_any_relaxation() -> None:
    choice = resolve_profile(environ={})
    assert choice.exposure_profile == UNCONSENTED_PROFILE
    assert choice.exposure_profile != "local"
    assert UNCONSENTED_PROFILE not in RUNTIME_PROFILES


def test_an_unconsented_run_still_binds_loopback() -> None:
    """The bind guard fails closed in the opposite direction: local is the restrictive case."""
    assert resolve_profile(environ={}).bind_profile == "local"


def test_a_deliberate_profile_is_carried_through_unchanged() -> None:
    choice = resolve_profile(environ={"HRZ_REGISTRY_PROFILE": "gcp"})
    assert (choice.profile, choice.explicit) == ("gcp", True)
    assert choice.exposure_profile == "gcp"
    assert choice.bind_profile == "gcp"
    assert choice.service_auth_configured is True


def test_a_profile_named_only_in_the_settings_file_is_still_deliberate() -> None:
    choice = resolve_profile("onprem", environ={})
    assert (choice.profile, choice.explicit) == ("onprem", True)
    assert choice.exposure_profile == "onprem"


@pytest.mark.parametrize("value", ["bogus", "Local", "GCP", "LOCAL", "local,gcp"])
def test_an_unknown_or_mis_capitalised_profile_refuses_to_load(value: str) -> None:
    with pytest.raises(ProfileError) as excinfo:
        resolve_profile(environ={"HRZ_REGISTRY_PROFILE": value})
    assert "HRZ_REGISTRY_PROFILE" in str(excinfo.value)


def test_surrounding_whitespace_is_stripped_rather_than_treated_as_a_typo() -> None:
    """A transport artifact is not a mis-capitalisation: strip, then match exactly."""
    assert resolve_profile(environ={"HRZ_REGISTRY_PROFILE": " gcp "}).profile == "gcp"


def _unconsented(settings: Settings) -> Settings:
    """``settings`` as an unconsented run: local adapters bound, but nobody chose them."""
    fields = {
        name: getattr(settings, name)
        for name in Settings.__dataclass_fields__
        if name != "profile_explicit"
    }
    return Settings(**fields, profile_explicit=False)


def test_an_unconsented_run_refuses_the_catalog_routes_with_no_token_configured(
    settings: Settings, sample_card_json: dict
) -> None:
    """The defect itself, end to end: no profile chosen and no secret set must NOT serve."""
    client = TestClient(create_app(_unconsented(settings)), client=LOOPBACK_PEER)
    assert client.post("/v1/agents", json=sample_card_json).status_code == 503
    assert client.get("/v1/agents").status_code == 503
    # Liveness and public A2A discovery stay outside the guard, so an operator can still
    # reach the service to see that it is refusing.
    assert client.get("/healthz").status_code == 200


def test_a_deliberate_local_run_keeps_the_zero_secret_opening_the_offline_gate_needs(
    settings: Settings, sample_card_json: dict
) -> None:
    client = TestClient(create_app(settings), client=LOOPBACK_PEER)
    assert client.post("/v1/agents", json=sample_card_json).status_code == 201


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
