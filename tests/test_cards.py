"""Round-trip and tolerance tests for the AgentCard <-> JSON mapping."""

from __future__ import annotations

from agent_registry.cards import card_from_dict, card_to_dict
from agent_registry.models import AgentCard, InteropProtocol, Lifecycle


def test_round_trip_preserves_spec_fields(sample_card_json: dict) -> None:
    card = card_from_dict(sample_card_json)
    body = card_to_dict(card)
    # The six SPEC §6 fields survive untouched.
    for field in ("name", "description", "url", "version", "provider"):
        assert body[field] == sample_card_json[field]
    assert body["skills"] == sample_card_json["skills"]


def test_round_trip_preserves_governance(sample_card_json: dict) -> None:
    card = card_from_dict(sample_card_json)
    body = card_to_dict(card)
    assert body["governance"]["owner"]["team"] == "rsk-compliance"
    assert body["governance"]["lifecycle"] == "draft"
    assert "mcp:tool:agent_search.query" in body["governance"]["scopes"]
    assert body["governance"]["protocols"] == ["a2a", "mcp"]


def test_plain_a2a_card_without_governance_gets_safe_defaults() -> None:
    # A vanilla A2A client may POST only the six discovery fields.
    minimal = {
        "name": "peer-agent",
        "description": "external",
        "url": "https://peer.example/a2a",
        "version": "2.0.0",
        "provider": "acme",
        "skills": [],
    }
    card = card_from_dict(minimal)
    assert card.lifecycle is Lifecycle.DRAFT
    assert card.scopes == ()
    assert card.protocols == (InteropProtocol.A2A, InteropProtocol.MCP)
    assert card.owner.team == ""


def test_enums_serialise_to_value() -> None:
    card = AgentCard(
        name="x",
        description="d",
        url="u",
        version="v",
        lifecycle=Lifecycle.DEPRECATED,
        protocols=(InteropProtocol.MCP,),
    )
    body = card_to_dict(card)
    assert body["governance"]["lifecycle"] == "deprecated"
    assert body["governance"]["protocols"] == ["mcp"]


def test_unknown_lifecycle_falls_back_to_draft() -> None:
    body = {
        "name": "n",
        "description": "",
        "url": "",
        "version": "",
        "governance": {"lifecycle": "bogus"},
    }
    card = card_from_dict(body)
    assert card.lifecycle is Lifecycle.DRAFT


def test_discoverable_flag() -> None:
    assert (
        AgentCard(
            "n",
            "d",
            "u",
            "v",
            provider="external",
            lifecycle=Lifecycle.ACTIVE,
        ).discoverable
        is False
    )
    assert (
        AgentCard("n", "d", "u", "v", provider="external", lifecycle=Lifecycle.RETIRED).discoverable
        is False
    )
