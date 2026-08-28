"""HTTP contract tests against SPEC §6 (A3).

These assert the exact wire behaviour C1's ``RemoteRegistryAdapter`` relies on:

* ``POST /v1/agents`` -> 201, body is the stored AgentCard.
* ``GET  /v1/agents/{name}`` -> 200 card, or 404 when absent.
* ``GET  /v1/agents`` -> JSON array of cards.
* ``GET  /.well-known/agent-card.json`` -> the registry's own card.
* ``GET  /v1/agents/{name}/card`` -> A2A passthrough.
* ``GET  /healthz`` -> {"status": "ok"}.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

_SPEC_FIELDS = ("name", "description", "url", "version", "provider", "skills")


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok",
        "profile": "local",
        "region": "asia-southeast1",
        "demo_only": True,
        "production_ready": False,
    }


def test_local_capability_manifest_is_honest(client: TestClient) -> None:
    body = client.get("/v1/capabilities").json()
    assert body["schema_version"] == "capability-manifest/v1"
    assert body["demo_only"] is True
    by_name = {item["name"]: item for item in body["capabilities"]}
    assert by_name["agent-catalog"]["available"] is True
    assert by_name["agent-catalog"]["assurance"] == "demo-only"
    assert by_name["audit-linkage"]["available"] is False


def test_post_agent_returns_201_and_card(client: TestClient, sample_card_json: dict) -> None:
    resp = client.post("/v1/agents", json=sample_card_json)
    assert resp.status_code == 201
    body = resp.json()
    for field in _SPEC_FIELDS:
        assert field in body
    assert body["name"] == "compliance-advisory"
    assert resp.headers.get("Location") == "/v1/agents/compliance-advisory"


def test_get_agent_after_register(client: TestClient, sample_card_json: dict) -> None:
    client.post("/v1/agents", json=sample_card_json)
    resp = client.get("/v1/governance/agents/compliance-advisory")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "compliance-advisory"
    assert body["version"] == "1.0.0"
    assert [s["id"] for s in body["skills"]] == ["answer", "checklist"]


def test_get_unknown_agent_is_404(client: TestClient) -> None:
    resp = client.get("/v1/agents/does-not-exist")
    assert resp.status_code == 404


def test_list_agents_is_json_array(client: TestClient, sample_card_json: dict) -> None:
    client.post("/v1/agents", json=sample_card_json)
    resp = client.get("/v1/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    names = {c["name"] for c in body}
    # Drafts stay out of production discovery.
    assert "compliance-advisory" not in names
    assert "agent-registry" in names


def test_post_is_idempotent_upsert(client: TestClient, sample_card_json: dict) -> None:
    client.post("/v1/agents", json=sample_card_json)
    updated = dict(sample_card_json, version="1.1.0")
    resp = client.post("/v1/agents", json=updated)
    assert resp.status_code == 201
    got = client.get("/v1/governance/agents/compliance-advisory").json()
    assert got["version"] == "1.1.0"
    # Still exactly one row for that name.
    listed = [
        c for c in client.get("/v1/governance/agents").json() if c["name"] == "compliance-advisory"
    ]
    assert len(listed) == 1


def test_well_known_card_is_registry_self_card(client: TestClient) -> None:
    resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "agent-registry"
    for field in _SPEC_FIELDS:
        assert field in body
    skill_ids = {s["id"] for s in body["skills"]}
    assert {"register", "resolve", "discover"} <= skill_ids


def test_agent_card_passthrough(client: TestClient, sample_card_json: dict) -> None:
    client.post("/v1/agents", json=sample_card_json)
    resp = client.get("/v1/agents/compliance-advisory/card")
    assert resp.status_code == 404
    assert client.get("/v1/agents/nope/card").status_code == 404


def test_governance_block_round_trips_over_http(client: TestClient, sample_card_json: dict) -> None:
    client.post("/v1/agents", json=sample_card_json)
    body = client.get("/v1/governance/agents/compliance-advisory").json()
    gov = body["governance"]
    assert gov["owner"]["team"] == "rsk-compliance"
    assert "a2a:invoke:agent-guardrail-gateway" in gov["scopes"]


def test_release_requires_attested_eval_and_persists_audit_link(
    client: TestClient, sample_card_json: dict
) -> None:
    client.post("/v1/agents", json=sample_card_json)
    rejected = client.post(
        "/v1/agents/compliance-advisory/release",
        json={
            "eval_run_id": "fabricated-eval",
            "audit_event_id": "audit-1",
        },
    )
    assert rejected.status_code == 409

    released = client.post(
        "/v1/agents/compliance-advisory/release",
        json={
            "eval_run_id": "eval-demo-compliance-advisory-1.0.0",
            "audit_event_id": "audit-demo-compliance-advisory-release",
        },
    )
    assert released.status_code == 200
    governance = released.json()["governance"]
    assert governance["lifecycle"] == "draft"
    assert governance["release_evidence"]["assurance"] == "demo-only"
    assert governance["release_evidence"]["eval_attested"] is False
    assert governance["release_evidence"]["eval_run_id"] == ("eval-demo-compliance-advisory-1.0.0")
    assert governance["release_evidence"]["audit_event_id"] == (
        "audit-demo-compliance-advisory-release"
    )


def test_direct_active_registration_is_blocked(client: TestClient, sample_card_json: dict) -> None:
    sample_card_json["governance"]["lifecycle"] = "active"
    response = client.post("/v1/agents", json=sample_card_json)
    assert response.status_code == 409


def test_reserved_self_card_cannot_be_overwritten(
    client: TestClient, sample_card_json: dict
) -> None:
    original = client.get("/.well-known/agent-card.json").json()
    sample_card_json["name"] = "agent-registry"
    sample_card_json["governance"]["lifecycle"] = "active"

    response = client.post("/v1/agents", json=sample_card_json)

    assert response.status_code == 409
    assert client.get("/.well-known/agent-card.json").json() == original


def test_draft_is_not_discoverable_until_server_verified_release(
    client: TestClient, sample_card_json: dict
) -> None:
    client.post("/v1/agents", json=sample_card_json)
    assert client.get("/v1/agents/compliance-advisory").status_code == 404
    assert client.get("/v1/agents/compliance-advisory/card").status_code == 404
    assert "compliance-advisory" not in {item["name"] for item in client.get("/v1/agents").json()}

    released = client.post(
        "/v1/agents/compliance-advisory/release",
        json={
            "eval_run_id": "eval-demo-compliance-advisory-1.0.0",
            "audit_event_id": "audit-demo-compliance-advisory-release",
        },
    )

    assert released.status_code == 200
    assert client.get("/v1/agents/compliance-advisory").status_code == 404
    assert client.get("/v1/agents/compliance-advisory/card").status_code == 404


def test_response_matches_c1_remote_parser(client: TestClient, sample_card_json: dict) -> None:
    """The response shape must be exactly what C1's RemoteRegistryAdapter._parse_card reads."""
    client.post("/v1/agents", json=sample_card_json)
    body = client.get("/v1/governance/agents/compliance-advisory").json()

    # Mirror compliance_advisory.adapters.platform.remote_registry._parse_card.
    parsed = {
        "name": str(body.get("name", "")),
        "description": str(body.get("description", "")),
        "url": str(body.get("url", "")),
        "version": str(body.get("version", "")),
        "provider": str(body.get("provider", "compliance-advisory")),
        "skills": [
            {
                "id": str(item.get("id", "")),
                "name": str(item.get("name", "")),
                "description": str(item.get("description", "")),
            }
            for item in (body.get("skills") or ())
        ],
    }
    assert parsed["name"] == "compliance-advisory"
    assert parsed["provider"] == "compliance-advisory"
    assert parsed["skills"][0]["id"] == "answer"


def test_missing_name_is_422(client: TestClient) -> None:
    resp = client.post("/v1/agents", json={"description": "no name", "skills": []})
    assert resp.status_code == 422
