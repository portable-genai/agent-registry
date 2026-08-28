# Demo guide - Hrz3 Agent Registry & Governance (`agent-registry`)

Two ways to demo Hrz3, the governed catalog/gallery of agents for the Horizon platform:

- **Demo A - Local, offline (the headline flow):** a presenter-controlled terminal
  walkthrough that drives the **real** registry through its daily lifecycle - serve the
  self-card, register a synthetic agent gallery (CLI + REST), discover, govern (idempotent
  version-bump upsert, retire, the unowned-card shadow-AI signal), and the onprem fail-fast.
  Runs **fully offline** (SQLite catalog, no Google Cloud, no API key, no emulator).
- **Demo B - GCP managed catalog:** the same REST contract served from Cloud Run against a
  real **AlloyDB** (or **Firestore**) catalog in `asia-southeast1`, exercised with curl.

> The agent cards in this demo are **synthetic and FICTIONAL**. Do not register cards that
> embed secrets or real production endpoints without your own security sign-off.

Hrz3 is a **platform service**: a REST API plus a CLI, with **no web UI**. So both demos are
CLI- and curl-based - there is no browser / Playwright step.

---

## 0. Prerequisites

| Need | Demo A (local) | Demo B (GCP) | Notes |
|------|:--:|:--:|-------|
| `git` | yes | yes | clone the repo |
| **Python 3.12+** | yes | yes | the package pins `>=3.12` (the repo `.venv` uses 3.14) |
| `curl` (and optionally `jq`) | yes | yes | exercise the REST endpoints |
| A GCP project + `gcloud` | no | yes | billing enabled; `asia-southeast1` available |
| Terraform | no | yes | provisions AlloyDB/Firestore, Cloud Run, CMEK, VPC |
| Cloud KMS key (regional) | no | yes | CMEK; set `HRZ_REGISTRY_KMS_KEY` |

Install/setup references (read these once):

- Local install & profiles -> [README "Deployment profiles"](README.md#deployment-profiles)
  and [README "Run it locally"](README.md#run-it-locally-offline-no-gcp)
- The HTTP contract -> [README "HTTP API (SPEC §6, Hrz3)"](README.md#http-api-spec-6-a3)
- The demo scripts -> [`scripts/README.md`](scripts/README.md)
- Terraform for the managed stack -> [`infra/terraform/README.md`](infra/terraform/README.md)
- Config (`${ENV_VAR}` resolved at load) -> [`config/settings.yaml`](config/settings.yaml)

---

## 1. Common setup (both demos)

```bash
git clone https://github.com/portable-genai/agent-registry.git
cd agent-registry

python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # core + dev tooling (NO google-cloud-* packages)

# Sanity-check the offline stack before presenting:
export HRZ_REGISTRY_PROFILE=local
make check                       # ruff + mypy + pytest + eval (all local, no cloud)
```

See [README "Run it locally"](README.md#run-it-locally-offline-no-gcp) for details.

---

## 2. Demo A - Local, offline (the headline flow)

The `local` profile is a **working** SQLite catalog, so it needs no Google Cloud and no API
key - ideal for a laptop demo. Two ways to present it, in order of polish.

### 2.1 Guided, presenter-controlled walkthrough (recommended)

The script narrates each step and **waits for you to press Enter** before running the real
CLI/API call, so you control the pace. No browser - Hrz3 has no UI; the REST calls run against
an in-process FastAPI `TestClient` and the CLI runs in-process, so nothing needs a port.

```bash
source .venv/bin/activate
PYTHONPATH=src python scripts/registry_demo.py     # or: make demo
```

You step through, pressing Enter each time:

1. **Self-describing registry** - `GET /.well-known/agent-card.json` returns Hrz3's own
   AgentCard (skills: register / resolve / discover) before any agent registers.
2. **Register the gallery** - four FICTIONAL Horizon agents publish their cards (one via the
   `agent-registry` CLI, the rest via `POST /v1/agents`), each with Hrz3 governance metadata
   (owner / lifecycle / scopes / protocols).
3. **Discover** - `GET /v1/agents` lists the gallery; `GET /v1/agents/{name}` and the A2A
   `/card` passthrough resolve a single agent.
4. **Govern (rule R4)** - re-publishing is an idempotent upsert keyed on `name` (the version
   bumps **in place**, no duplicate row); retiring an agent (`lifecycle -> retired`) drops it
   from production discovery while it stays resolvable; the **unowned** card is the shadow-AI
   signal a platform owner triages.
5. **Reversibility (P-02)** - the same command under `HRZ_REGISTRY_PROFILE=onprem` fails fast
   (exit 2) with the migration message.

**What to point at:** the `governance` block on each card (owner / lifecycle / scopes), the
unowned-card warning in step 3, the catalog count staying constant across the version bump in
step 4, and the clean exit-2 in step 5. Options (`DEMO_AUTO=1`, output JSON) are in
[`scripts/README.md`](scripts/README.md).

To self-run without prompts (recording / smoke), and optionally write the transcript JSON:

```bash
DEMO_AUTO=1 PYTHONPATH=src python scripts/registry_demo.py registry_demo.json
```

### 2.2 The raw CLI + curl commands (drive it yourself)

The same flow with the actual surfaces. **CLI** (the primary local artifact):

```bash
export HRZ_REGISTRY_PROFILE=local
export HRZ_REGISTRY_LOCAL_DB="${TMPDIR:-/tmp}/hrz-demo.db"   # pin a throwaway catalog
rm -f "$HRZ_REGISTRY_LOCAL_DB"

# Publish (upsert) an AgentCard, then read it back from the catalog.
agent-registry register --card '{
  "name": "compliance-advisory",
  "description": "Rsk1 Compliance Assistant (FICTIONAL).",
  "url": "https://compliance-advisory.asia-southeast1.example/a2a",
  "version": "1.2.0",
  "provider": "compliance-advisory",
  "skills": [{"id": "answer", "name": "Grounded compliance Q&A", "description": "Cited answers."}],
  "governance": {
    "owner": {"team": "rsk-compliance", "contact": "compliance-eng@horizon.example", "organization": "APAC Bank"},
    "lifecycle": "active",
    "scopes": ["a2a:invoke:agent-guardrail-gateway"],
    "protocols": ["a2a", "mcp"]
  }
}'
agent-registry get  compliance-advisory      # resolve one card
agent-registry list                           # the whole gallery

# Reversibility: the same command under onprem fails fast (exit 2), no traceback:
HRZ_REGISTRY_PROFILE=onprem agent-registry list; echo "exit=$?"   # -> exit=2
```

`make smoke` runs the register-then-list flow in one step.

**REST** (start the service on the local profile, then curl it):

```bash
make run                                       # uvicorn on http://localhost:8083 (profile=local)

curl -s localhost:8083/healthz
curl -s localhost:8083/.well-known/agent-card.json | jq      # Hrz3's own card
curl -s -X POST localhost:8083/v1/agents -H 'content-type: application/json' -d '{
  "name": "guardrail-gateway",
  "description": "Horizon guardrail gateway (FICTIONAL).",
  "url": "https://guardrail-gateway.asia-southeast1.example/a2a",
  "version": "0.9.0",
  "provider": "agent-guardrail-gateway",
  "skills": [{"id": "screen", "name": "Screen prompt", "description": "Block / allow / redact."}],
  "governance": {"owner": {"team": "platform-trust", "contact": "trust-eng@horizon.example"}}
}'
curl -s localhost:8083/v1/agents | jq                        # list the gallery
curl -s localhost:8083/v1/agents/guardrail-gateway | jq      # resolve one
curl -s localhost:8083/v1/agents/guardrail-gateway/card | jq # A2A passthrough
```

---

## 3. Demo B - GCP managed catalog (`asia-southeast1`)

Shows the **same REST contract** served from Cloud Run against a real managed catalog
(AlloyDB or Firestore). Use [`infra/terraform/README.md`](infra/terraform/README.md) for the
authoritative deploy steps; the short version:

### 3.1 GCP setup

```bash
source .venv/bin/activate
pip install -e ".[gcp,dev]"                 # adds the AlloyDB connector / SQLAlchemy / firestore

export GOOGLE_CLOUD_PROJECT=your-sg-project
export HRZ_REGISTRY_PROFILE=gcp
export HRZ_REGISTRY_BACKEND=alloydb         # or: firestore
export HRZ_REGISTRY_KMS_KEY="projects/.../locations/asia-southeast1/keyRings/.../cryptoKeys/..."
gcloud auth application-default login
```

### 3.2 Provision infra (one-time)

```bash
cd infra/terraform && terraform init -input=false && terraform plan   # review (CMEK + VPC)
terraform apply && cd ../..
# Export the connection facts the app reads (see infra/terraform/README.md):
export HRZ_REGISTRY_ALLOYDB_URI="$(terraform -chdir=infra/terraform output -raw alloydb_instance)"
```

Region defaults to `asia-southeast1` and is pinned at deploy time through the reviewed allowlist; the catalog is
CMEK-encrypted and reached over a private IP / VPC connector.

### 3.3 Run and show

```bash
make run PROFILE=gcp PORT=8083     # FastAPI on :8083, profile=gcp (talks to the managed catalog)
```

> `make run` always launches the real FastAPI app (`agent_registry.api.app:app`). The
> module-level `app` is import-safe - it performs no adapter I/O or SDK import until the first
> request - so it boots identically under `local` and `gcp`.

Then exercise the same endpoints against the managed catalog:

```bash
# Register an agent into the managed catalog:
curl -s -X POST localhost:8083/v1/agents -H 'content-type: application/json' -d '{
  "name": "kyc-doc-extractor",
  "description": "Doc1 KYC document extractor (FICTIONAL).",
  "url": "https://kyc-doc-extractor.asia-southeast1.example/a2a",
  "version": "2.0.0",
  "provider": "cdd-sow-research",
  "skills": [{"id": "extract", "name": "Extract fields", "description": "Cited field extraction."}],
  "governance": {"owner": {"team": "doc-intelligence", "contact": "doc-eng@horizon.example"}}
}'

# Discovery / resolution / health (identical to the local contract):
curl -s localhost:8083/v1/agents | jq
curl -s localhost:8083/v1/agents/kyc-doc-extractor | jq
curl -s localhost:8083/.well-known/agent-card.json | jq
curl -s localhost:8083/healthz
```

Against a deployed Cloud Run service, point curl at the service URL instead:
`terraform -chdir=infra/terraform output -raw service_url`.

**What to highlight:** the AgentCard wire shape (six A2A fields) is byte-for-byte identical
across `local` and `gcp` - only the adapter behind `AgentRegistryPort` changes; governance
(owner / lifecycle / scopes) is additive metadata a plain A2A peer ignores; everything stays
in `asia-southeast1` with CMEK ([README "Deployment profiles"](README.md#deployment-profiles)).

---

## 4. Talking points

- **One contract, three profiles.** `register` / `get` / `list` and the SPEC §6 AgentCard
  JSON are identical across `local` / `gcp` / `onprem`; only the adapter behind
  `AgentRegistryPort` changes. Rsk1's `RemoteRegistryAdapter` talks to Hrz3 with no translation.
- **Register is an idempotent upsert** keyed on `name`, so an agent re-publishing its card on
  every deploy updates the row in place - safe to re-run, never duplicates.
- **Governance kills shadow AI (rule R4).** Every card carries `governance.owner`; an unowned
  card is the signal a platform owner triages. `lifecycle` controls production
  discoverability; `scopes` carry least-privilege entitlements. A plain A2A peer reads only
  the six top-level fields and ignores the rest.
- **Self-describing.** The registry seeds its own AgentCard at the A2A well-known path on
  startup, so a fresh deployment is immediately discoverable and `GET /v1/agents` is never
  empty.
- **Reversibility (P-02).** Switching to `onprem` rebinds the port to a migration placeholder
  that fails fast (exit 2) - the domain above the adapter is unchanged.

---

## 5. Troubleshooting & cleanup

| Symptom | Fix |
|---------|-----|
| `python3.12: command not found` | Install Python 3.12+; the package pins `>=3.12`. |
| `ModuleNotFoundError: sqlalchemy` (or `google.cloud.*`) on `make run` | You are on `PROFILE=gcp` without the `[gcp]` extra. Use `HRZ_REGISTRY_PROFILE=local` for Demo A, or `pip install -e ".[gcp,dev]"` for Demo B. |
| `error: '...' is not available under profile 'onprem'` (exit 2) | Expected on `onprem` (fail-fast). Use `local` (Demo A) or `gcp` (Demo B). |
| Port 8083 already in use | `make run PORT=9000` and curl `localhost:9000`. |
| `agent-registry list` shows stale cards locally | The local catalog persists at `~/.agent_registry/local.db`; set `HRZ_REGISTRY_LOCAL_DB` to a throwaway path (the demo script uses a temp file it deletes). |
| GCP deploy / region / VPC errors | See [`infra/terraform/README.md`](infra/terraform/README.md). |

**Stop / clean up:** Ctrl-C `make run`. The guided script (`registry_demo.py`) uses a temp
catalog it removes on exit - it never touches `~/.agent_registry/local.db`. For GCP, scale
the Cloud Run service to zero or `terraform destroy`; the catalog data is CMEK-encrypted and
stays in `asia-southeast1`. `make clean` removes local caches/artefacts.
