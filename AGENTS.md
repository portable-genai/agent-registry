# agent-registry

The shared working agreement is [`.github/AGENTS.md`](https://github.com/portable-genai/.github/blob/main/AGENTS.md).
It carries the architecture rules, the gate contract, the fleet invariants, the
falsification discipline, versions and house style, and it holds in every repository
here. Read it first. This file carries only what is specific to this one.

## What this is

Catalog id `agent-registry`. The governed catalog of A2A/MCP AgentCards for the Horizon platform.
Control plane only: it stores and serves agent metadata, runs no model, and holds no customer
content.

## Documentation authority order

When two documents disagree, the higher one wins and the lower one is the bug:

1. **[`SPEC.md`](SPEC.md)**, locked decisions: profiles, the port, the HTTP contract other
   systems consume.
2. **[`ARCHITECTURE.md`](ARCHITECTURE.md)**, structure: ports, adapters, sequences, deployment
   topology. It defers the wire contract to SPEC rather than restating it.
3. **[`COMPLIANCE.md`](COMPLIANCE.md)**, the principle-to-control map plus the adopter-owned
   regulator crosswalk. It cites files; it does not define behaviour.
4. **[`README.md`](README.md)**, the orientation and quickstart. Narrative only.

Everything under `docs/` (runbook, on-prem migration, ADOPTING, FAQs) sits below README on the
same rule: it explains, it never decides.

**Staleness is a bug, not a caveat.** A shipped feature described as forthcoming, planned or
not yet built is a defect in the document, fixed in the same change that ships the feature.
`tests/test_doc_authority.py` fails the build if the order stops being declared here or if a
forward-looking marker reappears in the four authority documents.

## Non-negotiables in this repo

- Hexagonal: pure domain (`models.py`, `cards.py`, `self_card.py`) imports stdlib only; every
  adapter constructor takes exactly one `Settings`; cloud imports are lazy.
- Three profiles selected by `AGENT_REGISTRY_PROFILE` (`gcp` / `local` / `onprem`); the offline
  `local` profile is the default and the whole gate runs on it with no cloud SDKs.
- Fail closed: unknown profile raises, S2S auth guards every catalog route, a region outside
  `allowed_regions` refuses to load.
- Cross-cutting layers come from the shared packages (`hex-service-kit`), pinned by tag. Never
  copy such a layer in from a sibling repo.
- The gate, from the repo root:
  `ruff check . && ruff format --check . && mypy src && pytest -m 'not integration' && python eval/run_eval.py`
