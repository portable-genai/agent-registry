# On-prem migration (exit / portability): reversibility principle P-02

The whole point of the ports-and-adapters shape is that `agent-registry`'s exit story is **demonstrable,
not aspirational**. Moving the governed catalog off the managed GCP stack onto a sovereign /
on-premise platform (the Google Distributed Cloud target) is a one-line profile change
(`AGENT_REGISTRY_PROFILE=onprem`) plus filling in the adapter body. The domain, the HTTP API,
the CLI, the card mapping and the container wiring do not change.

## What "onprem" gives you today

Setting `AGENT_REGISTRY_PROFILE=onprem` rebinds the catalog port to a placeholder adapter under
`src/agent_registry/adapters/onprem/`. That adapter:

- constructs cleanly with **no Google Cloud SDK installed** and **no external dependencies**
  (the contract test proves it),
- structurally satisfies the same `@runtime_checkable` `AgentRegistryPort` Protocol as the
  managed AlloyDB / Firestore and local SQLite adapters, and
- raises `NotImplementedError` from every method (`register`, `get`, `list`) rather than
  silently no-op'ing, so a half-migrated deployment fails loud, not quiet. Under this profile
  the `agent-registry` CLI (and any driving command) exits `2` with the migration message.

This is what makes the contract test `tests/test_contract.py` meaningful: it imports and
constructs the on-prem placeholder, asserts interface parity against `AgentRegistryPort` with
no `google-cloud-*` installed, and confirms the fail-fast behaviour.

## The migration checklist

`agent-registry` has a single outbound port, so the migration is bounded to one adapter. To run the
registry on a sovereign / on-premise platform, implement this adapter body (the only file
that changes):

| Port | On-prem file | What to implement |
|---|---|---|
| `AgentRegistryPort` | `onprem/registry.py` | An on-prem catalog store for AgentCards: `register` as an idempotent upsert keyed on `name`, `get` by name (`None` if absent), `list` returning the full gallery. Back it with your on-premise database and regional key management. |

Match the managed adapters' guarantees when you fill the body in: the upsert must be
idempotent on `name` (agents re-publish their card on every deploy), the store must be
thread-safe under the FastAPI thread pool, and the card body should round-trip through
`cards.card_to_dict` so the persisted JSON stays identical to the managed and local backends.

Nothing under `src/agent_registry/` above the adapter changes. `models.py`, `cards.py`,
`schemas.py`, `self_card.py`, `container.py`, the FastAPI app (`api/app.py`), the S2S auth
(`api/security.py`) and the CLI (`cli/main.py`) are all profile-agnostic, which is the
no-lock-in proof (see [`COMPLIANCE.md`](../COMPLIANCE.md), P-02 and P-12, and
[`ARCHITECTURE.md`](../ARCHITECTURE.md) §4).

## Why this matters for a regulated buyer

An agent platform's governance function cannot accept a control plane it cannot exit. Because
the service depends only on one Protocol, the regulator-facing properties survive a platform
change unchanged: every agent still publishes an owned AgentCard before it is discoverable
(dependency rule **R4**, kill shadow AI), least-privilege `governance.scopes` still declare
exactly which MCP tools and A2A peers each agent may use, lifecycle governance still gates
production discoverability, and the A2A / MCP discovery contract (`/.well-known/agent-card.json`
and the per-agent card passthrough) is served identically. The migration is a single,
testable adapter rather than a rewrite, and data residency moves with the store you choose to
back it.
