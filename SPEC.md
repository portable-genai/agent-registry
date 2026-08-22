# SPEC: Hrz3 Agent Registry & Governance (`agent-registry`)

The governed catalog/gallery of agents for the Horizon platform. This SPEC pins the
deployment profiles, the one port, and the HTTP contract Hrz3 **defines** for sibling services
(Rsk1's `RemoteRegistryAdapter` consumes it).

**Documentation authority.** `SPEC.md` (this file) > `ARCHITECTURE.md` > `COMPLIANCE.md` >
`README.md`, with everything under `docs/` below README. On any disagreement this file wins and
the lower document is the defect, fixed in the same change. The order is declared in
[`AGENTS.md`](AGENTS.md) and enforced by `tests/test_doc_authority.py`.

---

## 1. Deployment profiles

Selected by `HRZ_REGISTRY_PROFILE` (or `profile:` in `config/settings.yaml`). Nothing above
the adapter layer changes between profiles.

The selection has **three** states, not two, and neither the variable nor the settings file
supplies a default. `config.resolve_profile` is the only reader of `HRZ_REGISTRY_PROFILE`:

1. **set to a known profile**, or named in `profile:`: that profile, matched exactly and
   case-sensitively. An unknown or mis-capitalised value refuses to load rather than
   selecting none of the relaxations and none of the restrictions.
2. **unset or blank**: nobody chose. The adapter family still falls back to `local`, because
   the alternative is importing cloud SDKs that are not installed, but every posture
   *relaxation* reads `exposure_profile`, which is a sentinel outside the profile set. A run
   that never named a profile therefore does not inherit the loopback-dev opening `local` is
   granted in §7, and an unset `HRZ_REGISTRY_S2S_TOKEN` is a refusal rather than consent.
3. Restrictions read `bind_profile` and fail closed in the **opposite** direction: an
   unconsented run looks like `local` to the bind guard and stays on loopback.

`tests/test_profile_single_source.py` fails the build if any module re-derives the profile
with its own permissive default, or if the settings file reintroduces one.

| Profile | Catalog backend | Google Cloud SDKs | Emulator | Use |
|---|---|---|---|---|
| `gcp` | AlloyDB for PostgreSQL (JSONB upsert) or Firestore (one doc per agent), lazy SDK imports | required (`[gcp]` extra) | n/a | Production (set `HRZ_REGISTRY_PROFILE=gcp` explicitly). |
| `local` | single-file SQLite catalog, idempotent upsert, seedable | none | optional Firestore emulator (opt-in) | What dev / test / CI name explicitly (Makefile, `ci.yaml`). Runs offline, no API key. |
| `onprem` | fail-fast placeholders (`NotImplementedError`) | none | n/a | Google Distributed Cloud migration target. CLI exits `2`. |

**Local backends.** Retrieval / persistence -> SQLite (`agent_cards` table, card body as
JSON). Deterministic schema-driven behaviour, fully seedable for tests. The `local`
path imports no google-cloud package.

**Emulator opt-in.** When `FIRESTORE_EMULATOR_HOST` is set AND `google-cloud-firestore`
imports, the `local` adapter mirrors writes to the official Firestore emulator. The google
client is imported lazily, only on that branch. Never required.

---

## 2. Port

One port, `AgentRegistryPort` (`src/agent_registry/ports/registry.py`), a
`@runtime_checkable` `typing.Protocol`:

- `register(card: AgentCard) -> None` : idempotent upsert keyed on `card.name`.
- `get(name: str) -> AgentCard | None` : resolve a single card; `None` if absent.
- `list() -> list[AgentCard]` : the full gallery.

Three adapter families implement it (`gcp`, `local`, `onprem`); see
[`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 3. CLI

`agent-registry` (`src/agent_registry/cli/main.py`, stdlib `argparse`, import-safe):

| Command | Behaviour |
|---|---|
| `register --card '{...}'` | upsert an AgentCard, print the stored card |
| `get <name>` | resolve and print one card |
| `list` | print the JSON array of cards |

Exit codes: `0` success; `2` the active profile cannot satisfy the command (the `onprem`
stub, or no binding); `1` an unexpected runtime failure.

---

## 4. Eval gate

`eval/run_eval.py` is the offline promotion gate. It drives the `local` adapter and scores
catalog-correctness invariants (`upsert_idempotency`, `roundtrip_fidelity`,
`resolve_accuracy`, `governance_preserved`), exiting non-zero on failure. CI runs it.

---

## 5. HTTP contract (defined by Hrz3, consumed by Rsk1)

All JSON field names mirror the domain dataclasses; enums are strings. The **Auth** column
marks which routes require service-to-service auth (see §5.1); the rest stay open.

| Method & path | Body | Response | Auth |
|---|---|---|---|
| `POST /v1/agents` | `{AgentCard}` | `201 {AgentCard}` (+ `Location`) | S2S |
| `GET /v1/agents/{name}` | n/a | `200 {AgentCard}` or `404` | S2S |
| `GET /v1/agents` | n/a | `200 [{AgentCard}, ...]` | S2S |
| `GET /.well-known/agent-card.json` | n/a | `200` the registry's own card | open |
| `GET /v1/agents/{name}/card` | n/a | `200 {AgentCard}` or `404` (A2A passthrough) | S2S |
| `GET /healthz` | n/a | `200 {"status": "ok"}` | open |

The `AgentCard` JSON is the six A2A discovery fields (`name`, `description`, `url`, `version`,
`provider`, `skills`) plus an additive `governance` block (`owner`, `lifecycle`, `scopes`,
`protocols`). See [`README.md`](README.md) for the full shape.

### 5.1 Service-to-service auth

The catalog CRUD and per-agent resolution routes (marked **S2S** above) authenticate the
*calling service* and fail closed; `/healthz` (liveness) and the public A2A discovery card
(`GET /.well-known/agent-card.json`) stay open. Callers present
`Authorization: Bearer <token>` (`src/agent_registry/api/security.py`,
`require_service_caller`):

- exactly `local`, deliberately chosen: a static shared secret compared in constant time
  against `HRZ_REGISTRY_S2S_TOKEN`. The variable is read in three states. UNSET: the API
  stays open (loopback dev, so the offline gate runs with no secret). SET to a secret: a
  request without the matching token is `401`. SET to an EMPTY value: every guarded route is
  a `503`, because an operator who set the variable expressed an intent to authenticate and
  an empty secret authenticates nobody, so it must never inherit the unset opening.
- `gcp` / `secure`: the bearer is a Google-signed OIDC ID token; its signature, issuer, expiry
  and audience (`HRZ_REGISTRY_S2S_AUDIENCE`) are verified, then the caller service account is
  authorized against the `HRZ_REGISTRY_S2S_ALLOWED_CALLERS` allowlist (`403` if not allowed).
  An unset or blank audience, and an unset or blank allowlist, are each a `503`, decided
  before the bearer is inspected, so an unconfigured identity policy cannot pass for a
  satisfied one. The Google verification libraries are imported lazily, so the offline
  profile needs no GCP SDK.
- any other profile string, including the unconfigured case where nothing ever named one: the
  shared-secret path with no opening, so an unset `HRZ_REGISTRY_S2S_TOKEN` is a `503`. The
  opening in the first case belongs to a profile somebody chose; it is not granted to a
  deployment whose configuration never arrived (§1).
