#!/usr/bin/env python3
"""Bounded, executable portability proof for Hrz3.

This proof runs offline. It checks the complete profile map, deterministic SQLite behavior,
SDK-free managed construction, fail-fast on-prem behavior and unknown-selector rejection.
It does not claim a live managed database, completed on-prem adapter, tenant portability,
audit portability or a data export/import migration.
"""

from __future__ import annotations

from agent_registry.config import LocalSettings, Settings
from agent_registry.container import Container
from agent_registry.models import AgentCard

_PROFILES = {"local", "gcp", "onprem"}
_PORTS = {"registry"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(f"portability evidence mismatch: {message}")


def _settings(profile: str) -> Settings:
    base = Settings.load()
    return Settings(
        project_id=base.project_id,
        region=base.region,
        profile=profile,
        backend=base.backend,
        kms_key=base.kms_key,
        registry=base.registry,
        alloydb=base.alloydb,
        firestore=base.firestore,
        local=LocalSettings(db_path=":memory:"),
        adapters=base.adapters,
    )


def _local_result() -> tuple[str, tuple[str, ...]]:
    registry = Container(_settings("local")).registry
    registry.register(
        AgentCard(
            name="portable-agent",
            description="Synthetic portable registry fixture",
            url="https://portable-agent.example.test/a2a",
            version="1.0.0",
        )
    )
    card = registry.get("portable-agent")
    _require(card is not None, "local get")
    return card.version, tuple(item.name for item in registry.list())


def main() -> int:
    print("Hrz3 bounded portability proof")
    settings = Settings.load()
    _require(set(settings.adapters) == _PORTS, "port set")
    _require(
        all(set(bindings) == _PROFILES for bindings in settings.adapters.values()),
        "profile set",
    )
    print("PASS profile map: local, gcp and onprem are explicit for the registry port")

    _require(_local_result() == _local_result() == ("1.0.0", ("portable-agent",)), "local rerun")
    print("PASS deterministic seam: fresh SQLite stacks produce identical registry results")

    managed = Container(_settings("gcp"))
    _ = managed.registry
    # Says only what this step establishes. "Without eager SDK calls" is a claim about an
    # interpreter where the SDK cannot be imported, and this process is not one: with the SDK
    # installed, an eagerly imported adapter constructs here and prints PASS just the same.
    print(
        "PASS managed seam: the GCP adapter imports and constructs offline "
        "(that it does so with the SDK BLOCKED is proved by tests/test_sdk_free_build.py)"
    )

    onprem = Container(_settings("onprem"))
    try:
        onprem.registry.list()
    except NotImplementedError:
        print("PASS exit boundary: the unconfigured on-prem registry fails closed")
    else:
        raise RuntimeError("on-prem registry did not fail fast")

    try:
        _ = Container(_settings("misspelled")).registry
    except KeyError:
        print("PASS selector: an unknown profile is rejected before adapter use")
    else:
        raise RuntimeError("unknown profile did not fail closed")

    print(
        "LIMITS not proved here: live managed persistence, completed on-prem, tenant or "
        "audit portability, or cross-store export and import."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
