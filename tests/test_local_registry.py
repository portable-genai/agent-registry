"""Unit tests for the local SQLite registry adapter (the offline catalog).

These drive the **real** ``local`` adapter (``SqliteRegistryAdapter``) against an in-memory
store, so the offline implementation is exercised directly rather than through a bespoke
fake. Determinism comes from ``db_path=":memory:"`` (provided by the ``settings`` fixture).
"""

from __future__ import annotations

from agent_registry.adapters.local.sqlite_registry import SqliteRegistryAdapter
from agent_registry.config import LocalSettings, Settings
from agent_registry.models import AgentCard, InteropProtocol, Lifecycle, Ownership


def _card(name: str, version: str = "1.0.0") -> AgentCard:
    return AgentCard(name=name, description="d", url=f"https://{name}.example", version=version)


def test_register_get_list(registry: SqliteRegistryAdapter) -> None:
    assert registry.get("a") is None
    assert registry.list() == []

    registry.register(_card("a"))
    registry.register(_card("b"))

    assert registry.get("a") is not None
    assert {c.name for c in registry.list()} == {"a", "b"}


def test_register_is_idempotent_upsert(registry: SqliteRegistryAdapter) -> None:
    registry.register(_card("a", "1.0.0"))
    registry.register(_card("a", "2.0.0"))
    got = registry.get("a")
    assert got is not None
    assert got.version == "2.0.0"
    assert len(registry.list()) == 1


def test_lifecycle_survives_round_trip(registry: SqliteRegistryAdapter) -> None:
    card = AgentCard("a", "d", "u", "v", lifecycle=Lifecycle.DEPRECATED)
    registry.register(card)
    got = registry.get("a")
    assert got is not None
    assert got.lifecycle is Lifecycle.DEPRECATED


def test_full_governance_survives_round_trip(registry: SqliteRegistryAdapter) -> None:
    card = AgentCard(
        name="gov",
        description="d",
        url="u",
        version="1.0.0",
        owner=Ownership(team="t", contact="c@x.example", organization="o"),
        lifecycle=Lifecycle.ACTIVE,
        scopes=("a2a:invoke:peer", "mcp:tool:x.query"),
        protocols=(InteropProtocol.MCP,),
    )
    registry.register(card)
    got = registry.get("gov")
    assert got is not None
    assert got.owner == card.owner
    assert got.scopes == card.scopes
    assert got.protocols == (InteropProtocol.MCP,)


def test_list_is_sorted_by_name(registry: SqliteRegistryAdapter) -> None:
    for name in ("c", "a", "b"):
        registry.register(_card(name))
    assert [c.name for c in registry.list()] == ["a", "b", "c"]


def test_default_db_path_is_under_home(monkeypatch, tmp_path) -> None:
    # An empty db_path selects the per-package default; point HOME at a temp dir so the
    # test does not touch the developer's real ~/.agent_registry.
    monkeypatch.setenv("HOME", str(tmp_path))
    adapter = SqliteRegistryAdapter(Settings(profile="local", local=LocalSettings(db_path="")))
    adapter.register(_card("persisted"))
    assert (tmp_path / ".agent_registry" / "local.db").exists()
    assert adapter.get("persisted") is not None
