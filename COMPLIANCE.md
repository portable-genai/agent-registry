# Compliance: principle-to-control mapping

This document maps the GRC General Principles (**P-01..P-12**) and platform dependency rules
(**R1..R6**) that are in scope for an agent registry to the concrete control that enforces
each in *this* repo: a file, an adapter, a config value, or a Terraform resource. Principles
that do not apply to a catalog service are marked **n/a** with a reason.

> Scope note: this is a reference build. The mappings show *how the architecture enforces each
> principle*; a production deployment still needs your own legal, security, and model-risk
> sign-off.

Paths are relative to the repo root. The port lives at `src/agent_registry/ports/registry.py`;
adapters under `src/agent_registry/adapters/`.

---

## A. General Principles (P-01..P-12)

| Principle | Statement | Control in this repo | Where |
|---|---|---|---|
| **P-01** | Data residency / sovereignty | One residency allowlist drives three enforcement points: `terraform plan` validation, an Org Policy `gcp.resourceLocations` allowlist, and a fail-closed check at application load. Regional CMEK per service, a dry-run-first VPC Service Controls perimeter and a locked-retention audit log bucket complete the posture | `config/settings.yaml` (`allowed_regions`), `src/agent_registry/config.py`, `infra/terraform/org_policy.tf`, `infra/terraform/vpc_sc.tf`, `infra/terraform/logging.tf` |
| **P-02** | No vendor lock-in: ports & adapters, swappable backends | One `Protocol` port, three interchangeable families bound by dotted path; a one-line `profile` switch across `gcp` / `local` / `onprem`. The **SDK-free `local` family proves the whole catalog runs off-cloud**, and the `onprem` placeholder family satisfies the same Protocol | `ports/registry.py`, `container.py`, `config/settings.yaml` (`adapters:`), `adapters/local/sqlite_registry.py`, `adapters/onprem/registry.py`, `tests/test_contract.py` |
| **P-03** | Least-privilege access & governed tools | `governance.scopes` on each card declares the exact MCP tools / A2A peers an agent may use; the registry is the source of truth the runtime enforces against. The catalog CRUD + A2A resolution routes are also **fail-closed to the calling service**: `require_service_caller` authenticates every caller (a deliberately chosen `local` a constant-time shared-secret compare against `HRZ_REGISTRY_S2S_TOKEN`, where a blank value is a `503` rather than the unset zero-secret opening; `gcp` a Google-signed OIDC ID token verified against `HRZ_REGISTRY_S2S_AUDIENCE` plus a caller allowlist, both required or the route is `503`; any other profile string, including a deployment that never named one, gets no opening at all), while `/healthz` and the public discovery card stay open | `models.py` (`AgentCard.scopes`), `api/security.py`, `api/app.py`, `cards.py`, `README` (interop) |
| **P-04** | Data minimisation, redact PII | n/a: the catalog stores agent metadata (names, owning team, scopes), not user content or PII. Owner contact is an operational email, not regulated personal data | |
| **P-05** | Input/output safety | n/a at this service: Hrz3 governs which agents may run and what they may call; prompt/response screening is Hrz1's responsibility (`agent-guardrail-gateway`). Hrz3 carries the scopes Hrz1 enforces | |
| **P-06** | Human-in-the-loop / maker-checker | Lifecycle gating: an agent is only discoverable for production routing when `lifecycle` is `active` / `deprecated`; promotion from `draft` is the maker-checker step | `models.py` (`Lifecycle`, `AgentCard.discoverable`) |
| **P-07** | Immutable audit trail with provenance | The catalog is the system of record for *which* agents exist and *who* owns them; the managed store is CMEK-encrypted and the write path is an idempotent, owner-stamped upsert. Cross-service audit is Hrz5 (`agent-observability`) | `adapters/gcp/alloydb_registry.py`, `models.py` (`Ownership`) |
| **P-08** | Model risk / quality gate before promotion | Offline promotion gate scoring catalog-correctness invariants (upsert idempotency, round-trip fidelity, resolve accuracy, governance preservation); CI blocks on a non-zero exit | `eval/run_eval.py`, `.github/workflows/ci.yaml` (eval step) |
| **P-09** | Observability without exposing sensitive content | The registry stores no message content; logs carry catalog operations only | `api/app.py`, `adapters/*` |
| **P-10** | Cost / FinOps transparency | Cost and latency are sized with the shared interactive calculator | `cost-latency-calculator.html`, `README` (Cost and latency) |
| **P-11** | Resilience / graceful degradation | `register` is an idempotent upsert (re-publishing on deploy never duplicates); `deprecated` cards stay resolvable so in-flight peers degrade gracefully | `adapters/local/sqlite_registry.py`, `models.py` (`Lifecycle.DEPRECATED`) |
| **P-12** | Reversibility / exit strategy | The `onprem` family is the documented Google Distributed Cloud exit: it satisfies the Protocol and fails fast with a migration message until ported. The `local` family additionally proves the catalog runs with no Google Cloud at all | `adapters/onprem/registry.py`, `adapters/local/sqlite_registry.py`, `tests/test_contract.py` (`test_onprem_registry_fails_fast`, `test_local_registry_works_offline`) |

---

## B. Platform dependency rules (R1..R6)

| Rule | Statement | Control in this repo | Where |
|---|---|---|---|
| **R1** | Pinned interop standards | A2A v1.0 + MCP 2026-07-28; `governance.protocols` records what each agent speaks | `README` (interop), `models.py` (`InteropProtocol`) |
| **R2** | Region pinned for residency | The selected region is used across the store, KMS and runtime; default `us-central1`, and a region outside `allowed_regions` fails at plan time and at process start | `config/settings.yaml`, `src/agent_registry/config.py`, `infra/terraform/variables.tf`, `infra/terraform/org_policy.tf` |
| **R3** | Lazy SDK imports / SDK-free offline path | All google-cloud imports are lazy; the `local` path imports no google-cloud package | `adapters/gcp/*` (lazy), `adapters/local/*`, `tests/test_contract.py` |
| **R4** | Kill shadow AI | Every agent must publish an `AgentCard` with an `owner` before it is discoverable; unregistered agents are invisible to orchestrators | `models.py` (`Ownership`), `README` (Governance mapping) |
| **R5** | Eval / quality gate in CI | The offline eval gate runs in CI and blocks on failure | `eval/run_eval.py`, `.github/workflows/ci.yaml` |
| **R6** | Reversible deployment | Three profiles behind one port; `local` runs off-cloud, `onprem` is the fail-fast exit | `config/settings.yaml` (`adapters:`), `container.py` |

---

## C. Regulator crosswalk (ADOPTER-OWNED)

**Ownership.** This appendix is owned by the ADOPTING institution, not by this repository.
Upstream ships it as a filled-in template for one home regulator (MAS, Singapore) so the shape
is unambiguous; a fork replaces the rows with its own regulator and keeps the file. Merges from
upstream never overwrite this section (see [`docs/ADOPTING.md`](docs/ADOPTING.md), adopter-owned
files). Nothing here is legal advice or a regulatory filing: it maps *what this control plane
does* to the obligations an adopter must evidence, so a compliance reviewer can start from
concrete artefacts rather than from prose.

Columns: the regulator's obligation, the internal principle it lands on, the control that
implements it here, and the artefact a reviewer can open.

| Regulator reference (MAS, Singapore) | Obligation in scope for an agent registry | Internal principle | Control here | Evidence |
|---|---|---|---|---|
| MAS TRM Guidelines s.6 (technology risk in IT operations) | Maintain a current inventory of IT assets, including their owners | P-04 (n/a for PII), R4 | Every agent must publish an `AgentCard` with an `owner` before it is discoverable; unregistered agents are invisible to orchestrators | `src/agent_registry/models.py`, `tests/test_local_registry.py` |
| MAS TRM Guidelines s.7 (access control, least privilege) | Restrict system access to authorised parties, verified server-side | P-03 | `require_service_caller` authenticates every catalog CRUD and resolution call; OIDC plus a caller allowlist under `gcp` | `src/agent_registry/api/security.py`, `tests/test_s2s_auth.py` |
| MAS TRM Guidelines s.11 (cryptography and key management) | Protect data at rest with managed keys under the institution's control | P-01 | Regional CMEK key ring and key, bound per service agent (AlloyDB, Cloud Run, log bucket) | `infra/terraform/kms.tf`, `tests/test_terraform_security_contract.py::test_cmek_is_bound_per_service_not_project_wide` |
| MAS Outsourcing / cloud advisory (data residency) | Keep regulated data within approved jurisdictions | P-01, R2 | One residency allowlist enforced at `terraform plan`, by Org Policy `gcp.resourceLocations`, and at application load | `infra/terraform/org_policy.tf`, `src/agent_registry/config.py`, `tests/test_residency.py` |
| MAS Outsourcing / cloud advisory (exit and reversibility) | Demonstrate an exit path from the service provider | P-12, R6 | Three profiles behind one port; `local` runs off cloud, `onprem` is the fail-fast Google Distributed Cloud exit; the portability claim is executable | `docs/onprem-migration.md`, `scripts/portability_demo.py` |
| MAS Notice 644 / TRM incident reporting | Retain records needed to reconstruct an incident, tamper-evident | P-07 | Control-plane admin and data-access audit logs sink to a CMEK bucket with a LOCKED retention policy; agent-level audit is delegated to Hrz5 | `infra/terraform/logging.tf` |
| MAS FEAT principles (fairness, ethics, accountability, transparency) | Name an accountable owner for every deployed model or agent | P-06, R4 | `Ownership` is mandatory on the card and lifecycle gating is the promotion (maker-checker) step | `src/agent_registry/models.py` |
| MAS Guidelines on Risk Management Practices, model risk | Evidence a quality gate before promotion | P-08, R5 | Attested release verification against Hrz4 evidence, plus the deterministic offline eval gate in CI | `src/agent_registry/release_verifier.py`, `eval/run_eval.py` |

**What this crosswalk does not claim.** It does not assert compliance. Live enforcement
evidence (an Org Policy actually applied to a named project, a VPC Service Controls perimeter
promoted out of dry run, a locked retention policy on a real bucket) exists only after the
adopter deploys; until then these rows point at posture-as-code, which is the input to that
evidence and not a substitute for it.
