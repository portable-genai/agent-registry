"""S2S auth tests for the A3 registry API (plan-hrz-s2s-auth, decision CD1).

The ``local`` profile is fail-open when ``AGENT_REGISTRY_S2S_TOKEN`` is UNSET (so the offline
gate runs with zero secrets) and fail-closed when it is set. Unset and set-to-blank are
different states: the zero-secret opening belongs to the unset one alone. ``/healthz``
(liveness) and ``GET /.well-known/agent-card.json`` (public A2A discovery of the registry's
own card) stay open in every state; the catalog CRUD and per-agent resolution routes are
guarded.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from agent_registry.api.app import create_app
from agent_registry.api.security import _TOKEN_ENV
from agent_registry.config import Settings
from conftest import LOOPBACK_PEER


def _client(settings: Settings) -> TestClient:
    """A raw TestClient with no self-card seeding (seeding would itself need the token)."""
    return TestClient(create_app(settings), client=LOOPBACK_PEER)


@pytest.fixture
def token_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv(_TOKEN_ENV, "s3cret-service-token")
    yield "s3cret-service-token"


def test_no_token_configured_is_open_loopback_dev(
    settings: Settings, sample_card_json: dict
) -> None:
    # AGENT_REGISTRY_S2S_TOKEN unset: the offline default, catalog still writable (zero-secret CI).
    resp = _client(settings).post("/v1/agents", json=sample_card_json)
    assert resp.status_code == 201


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_a_blank_token_never_inherits_the_zero_secret_opening(
    settings: Settings, sample_card_json: dict, monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    """A DELIBERATELY emptied AGENT_REGISTRY_S2S_TOKEN refuses, even under the local profile.

    Red before the three-state read: the secret was read in two states
    (``os.environ.get(name, "")`` then ``if secret:``), so a variable an operator set to an
    empty value was indistinguishable from one nobody configured and inherited the unset
    zero-secret opening. This registry is the governed catalog every vertical resolves peers
    through, so a deployment whose template rendered the secret empty accepted catalog WRITES
    from any caller with no credential at all: an attacker could publish an AgentCard pointing
    a peer's traffic at a URL of their choosing. An empty secret authenticates nobody, so it is
    now a 503 under every profile.
    """
    monkeypatch.setenv(_TOKEN_ENV, blank)
    client = _client(settings)
    assert client.post("/v1/agents", json=sample_card_json).status_code == 503
    assert client.get("/v1/agents").status_code == 503
    # Not even the right-looking credential rescues it: there is no secret to match against.
    headers = {"Authorization": f"Bearer {blank}"}
    assert client.post("/v1/agents", json=sample_card_json, headers=headers).status_code == 503


def test_the_open_routes_stay_open_when_the_token_is_blank(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal is scoped to the guarded routes: liveness and A2A discovery are unchanged."""
    monkeypatch.setenv(_TOKEN_ENV, "")
    client = _client(settings)
    assert client.get("/healthz").status_code == 200
    assert client.get("/.well-known/agent-card.json").status_code == 200


def test_a_blank_bind_host_is_refused_rather_than_defaulted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``API_HOST=""`` is not a host to bind, and must not inherit the profile default.

    Red before the three-state read: an empty API_HOST fell through to the profile default,
    so a secure profile bound every interface on a value nobody chose. ``python -m
    agent_registry`` resolves the bind through the same helper, so the refusal reaches this
    repo's entrypoint.
    """
    from hex_service_kit import ConfiguredEmptyError, resolve_bind_host

    monkeypatch.setenv("API_HOST", "  ")
    with pytest.raises(ConfiguredEmptyError):
        resolve_bind_host(
            "gcp", host_env="API_HOST", insecure_demo_env="AGENT_REGISTRY_ALLOW_INSECURE_DEMO"
        )


def test_healthz_never_requires_a_token(settings: Settings, token_env: str) -> None:
    assert _client(settings).get("/healthz").status_code == 200


def test_well_known_discovery_stays_open(settings: Settings, token_env: str) -> None:
    # Public A2A discovery of the registry's own card is unauthenticated by design.
    resp = _client(settings).get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    assert resp.json()["name"] == "agent-registry"


def test_missing_token_is_401_when_enforced(
    settings: Settings, sample_card_json: dict, token_env: str
) -> None:
    resp = _client(settings).post("/v1/agents", json=sample_card_json)
    assert resp.status_code == 401


def test_wrong_token_is_401_when_enforced(
    settings: Settings, sample_card_json: dict, token_env: str
) -> None:
    resp = _client(settings).post(
        "/v1/agents", json=sample_card_json, headers={"Authorization": "Bearer nope"}
    )
    assert resp.status_code == 401


def test_correct_token_is_accepted(
    settings: Settings, sample_card_json: dict, token_env: str
) -> None:
    resp = _client(settings).post(
        "/v1/agents", json=sample_card_json, headers={"Authorization": f"Bearer {token_env}"}
    )
    assert resp.status_code == 201


def test_read_is_also_guarded(settings: Settings, token_env: str) -> None:
    assert _client(settings).get("/v1/agents").status_code == 401
    ok = _client(settings).get("/v1/agents", headers={"Authorization": f"Bearer {token_env}"})
    assert ok.status_code == 200


def test_resolve_route_is_guarded(settings: Settings, token_env: str) -> None:
    # GET /v1/agents/{name}/card (A2A passthrough) also requires the service token.
    assert _client(settings).get("/v1/agents/whatever/card").status_code == 401


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
