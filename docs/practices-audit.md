# Common-base practices audit

- **Repo:** `agent-registry`
- **Catalog id:** Hrz3 (package `agent_registry`, env prefix `AGENT_REGISTRY`)
- **Catalogue reference:** [`common-base-practices.md`](https://github.com/portable-genai/.github/blob/main/common-base-practices.md) (checks A1..G7)
- **Authoritative source:** reconciled locally; the maintainer's
  cross-repository audit matrix is updated separately.
- **Note:** Each check was re-run against the CURRENT tree, with this repo's package (`agent_registry`)
  and env prefix (`AGENT_REGISTRY`) substituted into the catalogue's commands.

**This repo is a HORIZONTAL (Hrz3), a control-plane agent registry / governance catalog.** It does no
grounded LLM reasoning: it is a governed CRUD store of A2A/MCP AgentCards. Applicability is judged
honestly on that basis:

- The `[agentic]` checks (B1-B3, C3-C4, E1-E2) are **N-A by design**: a registry runs no model, stores
  no user content or PII, and produces no generated claim. They are marked N-A with a reason, not FAIL.
- `[ui]` checks (C6, C8) are **N-A**: there is no `ui/`; the only surfaces are a REST API and a CLI.
- `[infra]` checks (D4, D5) apply: the repo ships `infra/terraform/`.
- The `platform` delegate profile is intentionally absent: this repo IS the platform service that a
  vertical's `RemoteRegistryAdapter` (Rsk1) delegates to, so there is no sibling to delegate to.

**Load-bearing** checks (a FAIL breaks a shared catalog guarantee) are A1-A6, C1-C5, D1-D3 and E1.
Summary: A1-A6 all PASS; C1 PASS, C2/C3/C4 N-A by design, C5 PASS; D1-D3 PASS; E1 N-A
by design (agentic framing), its merge-gate substance met by `eval/run_eval.py` in CI. Every load-bearing
check passes or is N-A by design: the supply-chain checks (D1 lockfiles/exact-pin, D2 digest+SHA pins /
dependabot / audit) hold and C5 fail-closed defaults hold, so no
load-bearing FAIL remains.

| Check | Verdict | Evidence / gap |
|---|---|---|
| **A1** Hexagonal core, stdlib-only domain `[all]` **(load-bearing)** | PASS | Pure logic (`models.py`, `cards.py`, `self_card.py`) imports only stdlib; `grep -rE "google\|fastapi\|httpx\|pydantic\|boto3\|azure"` over them returns nothing. `schemas.py` (pydantic) is the wire/DTO layer, like the reference's `api/schemas.py`. Structural note: no separate `domain/` subpackage (the small model set lives at package root), which is fine at this size. |
| **A2** Ports are `@runtime_checkable` Protocols, re-exported once `[all]` **(load-bearing)** | PASS | One port, `AgentRegistryPort` (`ports/registry.py`), carries `@runtime_checkable`, re-exported from `ports/__init__.py`; `test_contract.py::test_protocol_is_runtime_checkable` asserts it. |
| **A3** Swappable profiles by one config value `[all]` **(load-bearing)** | PASS | `AGENT_REGISTRY_PROFILE = gcp\|local\|onprem`; per-port `adapters:` map in `config/settings.yaml`; the offline suite runs on `pip install -e ".[dev]"` with no GCP SDK. The `platform` profile is intentionally absent (this repo IS the platform service). |
| **A4** One adapter constructor `Adapter(settings)` `[all]` **(load-bearing)** | PASS | `test_contract.py::test_adapter_constructs_with_single_settings_arg` parametrises over `SDK_FREE_PROFILES` (`local`, `onprem`) x the port; `container._load` constructs any binding with a single `Settings`. |
| **A5** Lazy cloud imports in cloud adapters `[all]` **(load-bearing)** | PASS | `grep -n "^from google\|^import google\|^from sqlalchemy" adapters/gcp/*.py` returns nothing; `test_gcp_adapter_modules_import_without_google_sdks` + `test_gcp_adapters_construct_cleanly_without_sdks` prove it. The local adapter's Firestore-emulator import is lazy, on its branch only. |
| **A6** Contract tests enforce the hexagon; port map cannot drift `[all]` **(load-bearing)** | PASS | `test_contract.py` enforces runtime-checkable, single-settings construction, structural Protocol conformance, exact port/profile set equality and unknown-selector rejection. |
| **A7** Kernel vs vertical split in the domain `[all]` | N-A | By design: the domain is a single ~92-line `models.py` (AgentCard/AgentSkill/Ownership/Lifecycle). A single-purpose control-plane service has no vertical to fork from a kernel, so the split does not apply. |
| **A8** Consume platform horizontals via thin delegates `[all]` | N-A | By design: Hrz3 is a foundational (P0) horizontal. It defines a contract that others consume (Rsk1), consumes no sibling horizontal at runtime, and re-implements none. No second implementation of any horizontal's core exists. |
| **B1** Consequential math is deterministic, pure, replayable `[agentic]` | N-A | Registry does no LLM reasoning and computes no scores; persistence is a deterministic idempotent upsert. No numeric decision to make pure. |
| **B2** Every claim carries a citation; empty retrieval is a hard error `[agentic]` | N-A | No generated claims and no retrieval-then-cite path: the service stores and returns AgentCards verbatim. |
| **B3** Maker-checker on every consequential output `[agentic]` | N-A | No generated output to review. (Governance analog exists: `Lifecycle` gating, `AgentCard.discoverable` = active/deprecated only, per COMPLIANCE P-06, but this is not the agentic maker-checker the check describes.) |
| **B4** Bank-owned policy numbers in config, defaults = reference `[all]` | N-A | By design: pure CRUD, no weights/tolerances/cadences/scoring. The eval thresholds are correctness invariants (all `1.00`), not tunable policy. Nothing to externalise into a `policy:` section. |
| **B5** Open taxonomy: `StrEnum` vocabularies, engines typed on `str` `[all]` | N-A | By design: `Lifecycle` / `InteropProtocol` are closed governance vocabularies (`enum.Enum`, serialised to `.value`); there is no engine keyed on an adopter-extensible taxonomy. |
| **C1** Identity resolved server-side; client actor/ACL discarded `[all]` **(load-bearing)** | PASS | `schemas.py` (`AgentCardModel`) carries no `actor` field; the caller is authenticated server-side from the bearer token (`api/security.py`), never a client-asserted JSON field. There is no per-end-user Principal because this is a service-to-service control plane. |
| **C2** Object-level authz derived server-side; tenant isolation by data tags `[all]` **(load-bearing)** | N-A | By design: the catalog is a single shared platform gallery of agent metadata, not per-tenant resource data; there are no `case:`/`tenant:` row tags to isolate. Access is gated at the service boundary (C7 S2S allowlist), not per-object. |
| **C3** Redact before everything `[agentic]` **(load-bearing)** | N-A | No PII or user content: the store holds agent names, owning team, scopes and an operational owner email (COMPLIANCE P-04 marks this n/a). No model/index/trace call to redact before. |
| **C4** Jurisdiction-driven PII packs keep the gate honest `[agentic]` **(load-bearing)** | N-A | No PII handling and no eval PII metric, so there is no jurisdiction-selected pattern pack to keep honest. |
| **C5** Fail-closed defaults everywhere `[all]` **(load-bearing)** | PASS | The dev server binds loopback by default (Makefile `API_HOST ?= 127.0.0.1`; `python -m agent_registry` resolves the bind via `hex_service_kit.resolve_bind_host`, refusing to expose the no-auth local profile off loopback unless `AGENT_REGISTRY_ALLOW_INSECURE_DEMO=1`). Existing fail-closed elements stand: secure/gcp always verifies OIDC + allowlist; `local` constant-time compare when the token is set (unset = loopback dev convention); no CORS configured; an unbound port raises. The Dockerfile CMD binds 0.0.0.0 by design (container runs profile=gcp behind platform ingress). |
| **C6** Security-header baseline on every surface `[ui]` | N-A | No web UI. The REST API has no CSP/nosniff/Referrer-Policy/HSTS middleware; as an internal S2S JSON API this is a minor hardening opportunity, not a browser surface. |
| **C7** S2S calls authenticated, fail-closed `[all]` | PASS | `require_service_caller` is the shared `hex_service_kit.web.make_require_service_caller`, same env names (`AGENT_REGISTRY_S2S_*`) and profile rule (secure = gcp/secure), with the profile still resolved through `deps.get_settings` so test-app dependency overrides hold. Guards every catalog CRUD and per-agent resolution route; `/healthz` + the registry's own public card stay open. Covered by `test_s2s_auth.py`. |
| **C8** Web login flow hardening `[ui]` | N-A | The repo owns no browser login flow (no UI, S2S only). |
| **C9** Tamper-evident audit with honest limits `[all]` | N-A | By design: the registry owns no audit store. Cross-service audit / WORM logging is delegated to Hrz5 (`agent-observability`), per COMPLIANCE P-07 and the consume-the-horizontal rule (A8). The managed store is CMEK-encrypted and the write path is an idempotent owner-stamped upsert. |
| **C10** No secret values in the repo `[all]` | PASS | `config/settings.yaml` stores only `${ENV:-default}` names (e.g. `AGENT_REGISTRY_KMS_KEY`); `api/security.py` reads `AGENT_REGISTRY_S2S_TOKEN` at request time and never logs it; `.env.example` has placeholders only. |
| **D1** Locked, reproducible installs everywhere `[all]` **(load-bearing)** | PASS | Committed `requirements-dev.lock` + `requirements-gcp.lock`, both regenerated only through `make lock` -> `scripts/lock.py` (`uv pip compile --universal`), which re-applies the `tag = commit` header a bare compile destroys. `pyproject.toml` names the reviewable release TAG and each lock pins the 40-character COMMIT it resolves to, with the header mapping the two; `tests/unit/test_repo_artifacts.py` asserts the three-way agreement offline, asks a local object store whether each pinned sha is a commit rather than an annotated tag object, and fails if a lockfile ever escapes `make lock`. Read the pin out of the lockfiles rather than a number written here. `ruff==0.16.3` is exact; the Dockerfile installs from the runtime lock. **Observed failing first:** the locks previously carried uv's own two-line provenance comment and no map, so nothing recorded that the pinned `20ba3bece41c069a135151b9630d02dc1c69169f` was `hex-service-kit@v0.0.5` — `org-metadata/scripts/prove-installed-pins.py` had no `HEADER_TAG` line to read and `fleet-deps.py` had no `scripts/lock.py` to restore a header through, so this repo was skipped by both. |
| **D2** Digest-pinned images, SHA-pinned Actions, dependabot, CI audit `[all]` **(load-bearing)** | PASS | Base image digest-pinned, Actions SHA-pinned, `.github/dependabot.yml` present, `pip-audit` a hard CI gate. |
| **D3** Whole gate runs offline, zero org secrets `[all]` **(load-bearing)** | PASS | the hosted GitHub Actions check sets `AGENT_REGISTRY_PROFILE: local`, installs `.[dev]` only (no `[gcp]` extra), and runs ruff + mypy + pytest + `eval/run_eval.py` with no `secrets.` references. |
| **D4** Non-root, minimal, healthchecked container `[infra]` | PASS | Genuinely two-stage (`builder` installs into `/opt/venv` with git; `runtime` copies only that venv, so no git/compiler ships), dedicated non-root uid/gid 10001, `EXPOSE 8083`, `HEALTHCHECK` probing `/healthz` over loopback with the interpreter already present, and `AGENT_REGISTRY_PROFILE=gcp` set in the image so a shipped container cannot silently fall back to the no-auth SQLite profile. Both `FROM` lines stay digest-pinned. Asserted by `tests/test_container_image_contract.py` (6 tests). |
| **D5** Deploy-time residency/sovereignty, parameterised `[infra]` | PARTIAL (posture-as-code complete; live enforcement unproved) | The whole offline half is in place: one `allowed_regions` allowlist enforced at `terraform plan` (variable validation), by Org Policy `gcp.resourceLocations` derived from the same variable (`infra/terraform/org_policy.tf`), and at application load, where a region outside it raises `ResidencyError` (`src/agent_registry/config.py`, `tests/test_residency.py`). Also added: `iam.disableServiceAccountKeyCreation` enforced, a VPC-SC perimeter created DRY RUN FIRST with `use_explicit_dry_run_spec` and enforcement behind the `vpc_sc_enforce` opt-in defaulting false (`infra/terraform/vpc_sc.tf`), a CMEK-encrypted WORM log bucket with LOCKED retention plus the audit sink (`infra/terraform/logging.tf`), log-based posture alerts on dry-run and residency denials, per-service CMEK bindings including the storage service agent, and a credential-free `terraform fmt -check` + `init -backend=false` + `validate` job in CI. Asserted by `tests/test_terraform_security_contract.py` (6 tests) and `tests/test_residency.py` (5 tests); `terraform validate` passes locally. **Still PARTIAL, honestly:** everything above is posture-as-code. Proof that the Org Policy is applied to a named project, that the perimeter was promoted out of dry run, and that a real bucket carries a locked retention policy requires a production deployment that does not exist yet, and the hosted CI job cannot run while no hosted CI existed until GitHub Actions became the fleet's gate on 2026-09-02. |
| **E1** Offline eval smoke guards merge; Hrz4 owns promotion `[agentic]` **(load-bearing)** | N-A | The agentic framing (Hrz4 promotion authority, `EvaluationGatePort`, golden LLM dataset) does not apply to a registry. The load-bearing substance IS met: `eval/run_eval.py` is a deterministic offline gate over a fictional golden card set scoring catalog-correctness invariants (`upsert_idempotency`, `roundtrip_fidelity`, `resolve_accuracy`, `governance_preserved`), run by CI on every PR and exiting non-zero on failure. |
| **E2** Safety metric with strictest threshold, no false green `[agentic]` | N-A | No LLM output and no PII, so there is no safety/`pii_safety` metric. The correctness invariants are held at `1.00`, structurally unable to pass on a broken store. |
| **E3** Fixtures and golden data obviously fictional `[all]` | PASS | The eval golden set and the demo gallery use unmistakably synthetic names/URLs (`compliance-advisory`, `guardrail-gateway`, `fx-rate-helper (UNOWNED)`, `*.asia-southeast1.example`) and are labelled FICTIONAL in `scripts/registry_demo.py`. |
| **F1** Demo is code, offline, one command, presenter-paced `[all]` | PASS | `make demo` -> `scripts/registry_demo.py` drives the REAL `SqliteRegistryAdapter` through the CLI + an in-process FastAPI `TestClient` on the `local` profile (no cloud, no API key). Presenter-paced (waits for Enter; `DEMO_AUTO=1` self-runs); narrates on the console. |
| **F2** Demo cannot rot silently `[all]` | PASS | `scripts/demo_selftest.py` runs the real walkthrough unattended, reads its generated live transcript and fails on step-order, self-card skill, registration, discovery, lifecycle, uniqueness or on-prem-exit drift. CI invokes it. |
| **F3** Portability claim is executable `[all]` | PASS | `make portability-demo` exits non-zero unless the exact local/gcp/onprem map holds, fresh SQLite runs agree, the managed adapter constructs SDK-free, on-prem fails fast and an unknown selector is rejected. It states that live stores, completed on-prem, tenant/audit portability and export/import are unproved. CI invokes it. |
| **G1** Declared doc authority order, kept true `[all]` | PASS | `AGENTS.md` declares SPEC > ARCHITECTURE > COMPLIANCE > README (with `docs/` below README) and states that staleness is a defect fixed in the shipping change; the SPEC preamble restates the same order. `tests/test_doc_authority.py` fails if the order stops being declared, if it is listed out of sequence, if a named document disappears, or if a forward-looking marker ("forthcoming", "not yet built", "not yet implemented", "coming soon") reappears in any of the four authority documents. |
| **G2** Compliance mapping table + adopter-owned crosswalk `[all]` | PASS | `COMPLIANCE.md` section C adds a regulator crosswalk (MAS TRM, outsourcing/cloud advisory, Notice 644, FEAT, model risk) mapped to the internal principle, the control here and an openable artefact. The section states plainly that it is owned by the adopting institution, that upstream ships it as a filled-in template, and that it asserts no compliance: live enforcement evidence follows deployment. P-01 and R2 were rewritten to cite the new residency controls. `tests/test_doc_authority.py::test_compliance_mapping_cites_files_that_exist` proves every cited path exists; `::test_regulator_crosswalk_is_present_and_adopter_owned` proves the ownership and no-overstatement statements are present. |
| **G3** Documented, mechanised fork path `[all]` | PASS | `docs/ADOPTING.md` compares consume/fork/implement-port modes, names stable versus adopter-owned files and documents upstream/exit gates. `scripts/rename_fork.py` previews by default and preflights destination collision before writes; tests cover both rename content and collision safety. |
| **G4** Retired `[all]` | N-A (retired) | Retired practice. Releases are tracked by git tag and the `pyproject.toml` version. |
| **G5** Role-specific FAQs referencing sibling systems `[all]` | PASS | `docs/faq/` contains security, portability, features, adoption and compliance guides and keeps safety with Hrz1, knowledge with Hrz2, promotion with Hrz4, audit with Hrz5 and review with Hrz7. |
| **G6** Contribution docs cover full extension touch list `[all]` | PASS | `CONTRIBUTING.md` documents setup, the seven-step gate, the hexagon rules, the adding-a-port touch list and the commons-first rule; `test_contract.py` enforces the binding contract. |
| **G7** Markdown discipline: minimise em-dashes, validate mermaid `[all]` | PASS | An em-dash search returns 0 hits across README, SPEC, ARCHITECTURE, COMPLIANCE and DEMO; the mermaid blocks (`ARCHITECTURE.md` flowchart + sequenceDiagram, README graph) use standard syntax. |

**Verdict counts:** 24 PASS, 1 PARTIAL, 0 FAIL, 16 N-A (of 41 checks).
Load-bearing (A1-A6, C1-C5,
D1-D3, E1): A1-A6 PASS; C1 PASS, C2/C3/C4 N-A by design, C5 PASS; D1-D3 PASS; E1 N-A by
design with its merge-gate substance met by `eval/run_eval.py`. No load-bearing check FAILs or is a
non-design PARTIAL. The single surviving PARTIAL is D5,
whose code and config half is complete and whose remaining half is live-deployment evidence
this repo cannot produce.

## Gaps carried to systems/

Tracked against the Hrz3 row of
the maintainer's per-system register under
`Capability gaps`. Open items only.

- **D5 (infra): deploy-time sovereignty.** Org Policy
  resource-location allowlist, keyless service accounts, a dry-run-first VPC-SC perimeter, a
  WORM log bucket with locked retention, posture alerts, the validated region variable and the
  credential-free `terraform fmt -check`/`validate` CI job are all in place, and the same allowlist
  fails closed at application load. What remains is evidence that cannot be produced
  offline: an Org Policy applied to a named GCP project, a perimeter promoted out of dry run,
  a locked retention policy on a real bucket, and a hosted CI run of the terraform job (no hosted CI existed until GitHub Actions became the fleet's gate on 2026-09-02).

Mandated docs `docs/runbook.md` and `docs/onprem-migration.md` are present.

The `[agentic]` checks (B1-B3, C3-C4, E1-E2) and C2/C9 are **N-A by design** for a control-plane
registry (no grounded LLM, no user content/PII, no per-tenant resource data, audit delegated to Hrz5);
they are not gaps.
