"""Contract tests: the ``local`` and ``onprem`` adapters are structural parity of the port.

For the one port this catalog declares (``registry``), this iterates the adapter map and,
for both the ``local`` and ``onprem`` profiles, imports + constructs the bound class (which
must build cleanly with **no Google Cloud SDK** installed), then asserts:

  1. the constructed instance satisfies its ``runtime_checkable`` Protocol (isinstance), and
  2. every method the Protocol declares actually exists on the instance.

It additionally proves the two profiles' distinct contracts:

* ``local`` is a WORKING offline stack: the registry constructs and answers in-process, and
* ``onprem`` is the fail-fast Google Distributed Cloud migration target: every method raises
  ``NotImplementedError``.

It also confirms the ``gcp`` adapter modules import + construct with no Google Cloud SDKs
installed (the lazy-import contract). This is the proof of the ports-and-adapters /
no-lock-in promise: the on-prem migration target and the offline local stack implement the
exact same interface as the managed GCP stack.
"""

from __future__ import annotations

import importlib
from typing import Protocol

import pytest

from agent_registry.config import LocalSettings, Settings
from agent_registry.ports import AgentRegistryPort

CONFIG_PATH = "config/settings.yaml"

# Every port name in settings.adapters mapped to its Protocol.
PORT_PROTOCOLS: dict[str, type] = {
    "registry": AgentRegistryPort,
}

# Profiles whose adapters must construct + satisfy the Protocols with no GCP SDK.
SDK_FREE_PROFILES = ("local", "onprem")


def _settings(profile: str) -> Settings:
    base = Settings.load(CONFIG_PATH)
    # Point the local store at in-memory SQLite so the contract test stays ephemeral.
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


def _instantiate(dotted: str, settings: Settings) -> object:
    module_path, _, class_name = dotted.partition(":")
    cls = getattr(importlib.import_module(module_path), class_name)
    return cls(settings)


def _protocol_members(protocol: type) -> set[str]:
    """The attribute names a Protocol declares (methods + properties), no dunders."""
    members = set(getattr(protocol, "__protocol_attrs__", set()))
    return {m for m in members if not m.startswith("_")}


def test_every_port_has_exact_profile_bindings() -> None:
    settings = Settings.load(CONFIG_PATH)
    assert set(settings.adapters) == set(PORT_PROTOCOLS)
    for port_name, binding in settings.adapters.items():
        assert set(binding) == {"local", "gcp", "onprem"}, (
            f"port '{port_name}' must bind exactly local, gcp and onprem"
        )


def test_gcp_region_is_configurable_from_one_selector(monkeypatch) -> None:
    # Region and residency allowlist move together: a new region is approved, not assumed.
    monkeypatch.setenv("GCP_REGION", "europe-west4")
    monkeypatch.setenv("HRZ_REGISTRY_ALLOWED_REGIONS", "asia-southeast1,europe-west4")
    settings = Settings.load(CONFIG_PATH)
    assert settings.region == "europe-west4"
    assert settings.registry.public_url == "https://agent-registry.europe-west4.run.app"


def test_unknown_profile_fails_closed() -> None:
    from agent_registry.container import Container

    with pytest.raises(KeyError, match="profile 'misspelled'"):
        _ = Container(_settings("misspelled")).registry


@pytest.mark.parametrize("profile", SDK_FREE_PROFILES)
@pytest.mark.parametrize("port_name", sorted(PORT_PROTOCOLS))
def test_adapter_satisfies_protocol(profile: str, port_name: str) -> None:
    settings = _settings(profile)
    protocol = PORT_PROTOCOLS[port_name]
    dotted = settings.adapters[port_name][profile]

    # Import + construct with only Settings (the adapter convention), no GCP SDK.
    adapter = _instantiate(dotted, settings)

    # 1. Structural conformance via runtime_checkable Protocol.
    assert isinstance(adapter, protocol), (
        f"{dotted} does not structurally satisfy {protocol.__name__}"
    )

    # 2. Every declared Protocol member exists. Check on the *class* (via the MRO), not the
    #    instance: a placeholder getter may raise, so ``hasattr`` would wrongly report it
    #    missing. Looking the name up on the type tests for declaration without invoking it.
    members = _protocol_members(protocol)
    declared = set().union(*(vars(klass) for klass in type(adapter).__mro__))
    for member in members:
        assert member in declared, (
            f"{dotted} is missing port method '{member}' of {protocol.__name__}"
        )


@pytest.mark.parametrize("profile", SDK_FREE_PROFILES)
@pytest.mark.parametrize("port_name", sorted(PORT_PROTOCOLS))
def test_adapter_constructs_with_single_settings_arg(profile: str, port_name: str) -> None:
    """The build contract: every adapter is ``Adapter(settings: Settings)``."""
    settings = _settings(profile)
    dotted = settings.adapters[port_name][profile]
    instance = _instantiate(dotted, settings)
    assert instance is not None


def test_local_registry_works_offline() -> None:
    """The local stack is WORKING: register / get / list answer in-process offline."""
    settings = _settings("local")
    adapter = _instantiate(settings.adapters["registry"]["local"], settings)
    from agent_registry.models import AgentCard

    card = AgentCard(name="x", description="d", url="u", version="1.0.0")
    adapter.register(card)  # type: ignore[attr-defined]
    got = adapter.get("x")  # type: ignore[attr-defined]
    assert got is not None and got.name == "x"
    assert [c.name for c in adapter.list()] == ["x"]  # type: ignore[attr-defined]


def test_onprem_registry_fails_fast() -> None:
    """The on-prem stubs are fail-fast: every method raises NotImplementedError."""
    settings = _settings("onprem")
    adapter = _instantiate(settings.adapters["registry"]["onprem"], settings)
    from agent_registry.models import AgentCard

    with pytest.raises(NotImplementedError):
        adapter.list()  # type: ignore[attr-defined]
    with pytest.raises(NotImplementedError):
        adapter.get("x")  # type: ignore[attr-defined]
    with pytest.raises(NotImplementedError):
        adapter.register(  # type: ignore[attr-defined]
            AgentCard(name="x", description="d", url="u", version="v")
        )


def test_gcp_adapter_modules_import_without_google_sdks() -> None:
    # Module import must not pull google-cloud-* / sqlalchemy (lazy-import contract).
    alloydb = importlib.import_module("agent_registry.adapters.gcp.alloydb_registry")
    firestore = importlib.import_module("agent_registry.adapters.gcp.firestore_registry")
    assert hasattr(alloydb, "AlloyDBRegistryAdapter")
    assert hasattr(firestore, "FirestoreRegistryAdapter")


def test_gcp_adapters_construct_cleanly_without_sdks() -> None:
    settings = _settings("local")  # any Settings; gcp ctors must not touch the SDK
    from agent_registry.adapters.gcp.alloydb_registry import AlloyDBRegistryAdapter
    from agent_registry.adapters.gcp.firestore_registry import FirestoreRegistryAdapter

    assert isinstance(AlloyDBRegistryAdapter(settings), AgentRegistryPort)
    assert isinstance(FirestoreRegistryAdapter(settings), AgentRegistryPort)


def test_container_resolves_local_binding(settings: Settings) -> None:
    from agent_registry.container import Container

    registry = Container(settings).registry
    assert isinstance(registry, AgentRegistryPort)
    assert type(registry).__name__ == "SqliteRegistryAdapter"


def test_protocol_is_runtime_checkable() -> None:
    for protocol in PORT_PROTOCOLS.values():
        assert issubclass(protocol, Protocol)  # type: ignore[arg-type]
        assert getattr(protocol, "_is_runtime_protocol", False), (
            f"{protocol.__name__} must be @runtime_checkable"
        )
