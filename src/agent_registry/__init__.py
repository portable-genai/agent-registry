"""A3 Agent Registry & Governance — the catalog/gallery for the Horizon agent platform.

Catalog identity: **A3** (group ``hrz``). The system of record for *which* agents exist,
*who* owns them, *what* they are entitled to do, and *how* peers discover and talk to them
(A2A v1.0 + MCP 2026-07-28). Registering every agent here is what **kills shadow AI**
(dependency rule **R4**): an agent that is not in the registry is not governed, not
discoverable, and not allowed to run on the platform.

What A3 provides:

* **Identity & ownership** — a stable ``name``, an owning team, and a lifecycle state for
  every agent (the :class:`~agent_registry.models.AgentCard`).
* **Scoped entitlements** — the least-privilege scopes / tools an agent is allowed to use,
  carried on the card so the platform can enforce them.
* **A2A / MCP interop** — the A2A AgentCard served at ``/.well-known/agent-card.json`` and a
  per-agent ``/v1/agents/{name}/card`` passthrough so peers can resolve a card before
  initiating a task.
* **Discovery** — ``GET /v1/agents`` lists the whole gallery for humans and orchestrators.

Backed by an **AlloyDB / Firestore**-style managed adapter in the configured GCP region behind a
:class:`~agent_registry.ports.registry.AgentRegistryPort`. The same port also has an SDK-free
``local`` SQLite adapter (the dev / test default, runs the catalog offline with no Google
Cloud SDKs) and a fail-fast ``onprem`` migration placeholder.
"""

from __future__ import annotations

__version__ = "0.0.1"
__all__ = ["__version__"]
