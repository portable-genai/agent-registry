"""Shared pytest fixtures: the ``local`` adapter (seeded), driven offline.

The suite is driven by the **real** ``local`` adapter family
(``src/agent_registry/adapters/local``) rather than a bespoke in-memory fake, so the offline
implementation lives in exactly one place and the tests exercise the same code the offline
CLI runs. Every fixture pins the ``local`` profile with an in-memory SQLite store
(``db_path=":memory:"``) so the whole suite runs offline with no Google Cloud SDKs installed
and is hermetic (no ``settings.yaml`` read, no environment dependence).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the repo root importable so the eval scorers (``eval.run_eval``) resolve regardless of
# the pytest invocation directory: ``tests/`` is not a package, so pytest inserts that
# directory rather than the root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The dev / test default profile is ``local`` (the offline SQLite catalog). Set it before any
# adapter module imports so the module-level ``api.app:app = create_app()`` builds the local
# adapter rather than the gcp one (whose first store call would need the Google Cloud SDKs).
os.environ.setdefault("HRZ_REGISTRY_PROFILE", "local")

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent_registry.adapters.local.sqlite_registry import SqliteRegistryAdapter  # noqa: E402
from agent_registry.config import Settings  # noqa: E402
from agent_registry.container import Container  # noqa: E402

#: A loopback peer for every ``TestClient``. The app-object exposure guard refuses the
#: unauthenticated ``local`` posture to any other peer, and TestClient's DEFAULT peer is the
#: literal host ``"testclient"``, which is not a loopback address and is refused with a 503.
LOOPBACK_PEER = ("127.0.0.1", 50000)

# The build-contract adapter bindings the in-process settings expose, mirroring
# config/settings.yaml so Container resolution under test matches production wiring.
_ADAPTER_BINDINGS = {
    "registry": {
        "gcp": "agent_registry.adapters.gcp.alloydb_registry:AlloyDBRegistryAdapter",
        "local": "agent_registry.adapters.local.sqlite_registry:SqliteRegistryAdapter",
        "onprem": "agent_registry.adapters.onprem.registry:OnPremRegistryAdapter",
    }
}


@pytest.fixture
def settings() -> Settings:
    """Local-profile settings with an ephemeral in-memory SQLite catalog bound."""
    return Settings.from_dict(
        {
            "project_id": "test-project",
            "region": "asia-southeast1",
            "profile": "local",
            "registry": {
                "name": "agent-registry",
                "public_url": "https://agent-registry.asia-southeast1.run.app",
                "version": "0.1.0",
            },
            "local": {"db_path": ":memory:"},
            "adapters": _ADAPTER_BINDINGS,
        }
    )


@pytest.fixture
def container(settings: Settings) -> Container:
    return Container(settings)


@pytest.fixture
def registry(settings: Settings) -> SqliteRegistryAdapter:
    """The real local SQLite adapter, constructed against an in-memory store."""
    return SqliteRegistryAdapter(settings)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """A FastAPI TestClient bound to a fresh in-memory local registry.

    The lifespan seeds the reserved self-card directly through the registry port. External
    API callers cannot mutate that card.
    """
    from agent_registry.api.app import create_app

    with TestClient(create_app(settings), client=LOOPBACK_PEER) as test_client:
        yield test_client


@pytest.fixture
def sample_card_json() -> dict:
    """A representative AgentCard body in the SPEC §6 wire shape."""
    return {
        "name": "compliance-advisory",
        "description": "C1 Compliance Assistant, grounded RAG over MAS/HKMA/APRA/FSA.",
        "url": "https://compliance-advisory.asia-southeast1.example/a2a",
        "version": "1.0.0",
        "provider": "compliance-advisory",
        "skills": [
            {"id": "answer", "name": "Grounded compliance Q&A", "description": "Cited answers."},
            {"id": "checklist", "name": "Control checklist", "description": "Per use-case."},
        ],
        "governance": {
            "owner": {
                "team": "rsk-compliance",
                "contact": "compliance-eng@bank.example",
                "organization": "APAC Bank",
            },
            "lifecycle": "draft",
            "scopes": ["a2a:invoke:agent-guardrail-gateway", "mcp:tool:agent_search.query"],
            "protocols": ["a2a", "mcp"],
        },
    }
