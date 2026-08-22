"""Three-state contract for optional local emulator selection."""

from __future__ import annotations

import pytest
from hex_service_kit.netdefaults import ConfiguredEmptyError

from agent_registry.adapters.local._emulator import firestore_emulator_host


def test_firestore_emulator_host_falls_back_only_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)

    assert firestore_emulator_host() is None


@pytest.mark.parametrize("value", ["", " \t "])
def test_firestore_emulator_host_refuses_configured_empty(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", value)

    with pytest.raises(ConfiguredEmptyError, match="FIRESTORE_EMULATOR_HOST"):
        firestore_emulator_host()


def test_firestore_emulator_host_returns_trimmed_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", " 127.0.0.1:8080 ")

    assert firestore_emulator_host() == "127.0.0.1:8080"
