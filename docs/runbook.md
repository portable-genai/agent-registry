# Runbook: Hrz3 Agent Registry & Governance

Operational notes for deploying and running Hrz3 (`agent-registry`) on Cloud Run in
`us-central1`. This is a reference build; adapt it to your own change-management and
platform sign-off before any live use. Hrz3 is a **control-plane service**: a governed
catalog with deterministic invariants (idempotent upsert keyed on `name`, no floating
endpoints). It has **no end-user UI** and **no grounded LLM / ADK agent**, so there is no
model-serving, prompt, or eval-of-generation surface to operate; the eval gate here checks
catalog correctness, not generation quality.

## 1. Deploy

```bash
# 1. Provision infra. Region defaults to us-central1 and must be in allowed_regions.
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # set project_id; pick backend (alloydb | firestore)
terraform init -input=false && terraform plan
terraform apply

# 2. Export the outputs the running service consumes (settings.yaml resolves them).
export GOOGLE_CLOUD_PROJECT=my-gcp-project
export HRZ_REGISTRY_PUBLIC_URL="$(terraform output -raw service_url)"
export HRZ_REGISTRY_KMS_KEY="$(terraform output -raw cmek_key)"
export HRZ_REGISTRY_BACKEND="$(terraform output -raw backend)"        # alloydb | firestore
export HRZ_REGISTRY_ALLOYDB_URI="$(terraform output -raw alloydb_instance)"   # empty on firestore

# 3. Build and push the image, then point Cloud Run at it (Artifact Registry, us-central1).
make docker-build
terraform apply -var="container_image=us-central1-docker.pkg.dev/<project>/hrz/agent-registry:0.1.0"
```

The container image selects the secure `gcp` profile explicitly (`HRZ_REGISTRY_PROFILE=gcp` in
the Dockerfile), so a shipped image never falls back to the no-auth SQLite profile; Terraform
sets the same value on the Cloud Run service, along with
`HRZ_REGISTRY_BACKEND=alloydb|firestore`. Outside the image, `local` remains the default
whenever `HRZ_REGISTRY_PROFILE` is unset (`config/settings.yaml`, Makefile), which is what
keeps the offline gate SDK-free. No code above the adapter layer changes between profiles.

**Service-to-service auth.** The catalog CRUD and per-agent resolution routes fail closed;
`/healthz` and the public A2A discovery card stay open. Under `gcp` the service verifies a
Google-signed OIDC ID token against `HRZ_REGISTRY_S2S_AUDIENCE` and checks the caller service
account against `HRZ_REGISTRY_S2S_ALLOWED_CALLERS` (`403` if not allowed). Under `local` an
optional shared secret in `HRZ_REGISTRY_S2S_TOKEN` is compared in constant time (unset means
open for loopback dev; set to a secret means `401` without it; set to an empty value refuses
every guarded route with a `503`, so a template that renders the secret to nothing fails
loudly instead of accepting catalog writes unauthenticated). Set these before exposing the
service.

## 2. Region selection and fail-fast

The Terraform `region` variable defaults to `us-central1` and must be present in
`allowed_regions`. The Cloud Run service, AlloyDB cluster (or Firestore database), and CMEK
key ring are created in that one selected region. Set `GCP_REGION` to the same value at
runtime and confirm the `well_known_card_url` output resolves to that regional deployment.
The `public_url` advertised in the registry's own AgentCard must refer to the same deployment.

Residency is enforced from one allowlist in three places, so a wrong region fails early and
loudly rather than quietly writing agent metadata abroad:

1. `terraform plan` rejects a `region` outside `allowed_regions` (variable validation).
2. The `gcp.resourceLocations` Org Policy (`infra/terraform/org_policy.tf`) refuses resource
   creation elsewhere in the project, including by hand in the console.
3. The application refuses to load settings whose `region` is outside
   `HRZ_REGISTRY_ALLOWED_REGIONS` (`ResidencyError` at process start). Terraform passes the
   same list into the Cloud Run environment.

Approving a new region therefore means one change to `allowed_regions` in tfvars, not a fork.

**Perimeter rollout.** The VPC Service Controls perimeter is created in dry run
(`vpc_sc_enforce = false`). Watch the `Hrz3 registry: VPC-SC dry-run violation` alert; when it
stays silent through a full business cycle, set `vpc_sc_enforce = true` to promote the same
service list into enforcement. Roll back by flipping it to `false`.

## 3. Key rotation

The regional CMEK crypto key (`kms.tf`) rotates every 90 days (`rotation_period = "7776000s"`).
Rotation is transparent to the service; no restart is needed. The key has
`prevent_destroy = true`, and the AlloyDB cluster / Firestore database carry delete
protection, so the catalog store cannot be torn down while data depends on it. Plan any
removal deliberately.

## 4. Catalog invariants

`register` is an **idempotent upsert keyed on `name`**: an agent re-publishes its AgentCard
on every deploy and the row updates in place, so re-running a register is always safe and
never creates duplicates. The same shape holds on all managed and local backends
(`INSERT ... ON CONFLICT(name) DO UPDATE` on SQLite / AlloyDB, one document per agent on
Firestore). There is no ungoverned write path: an agent not in the registry is not
discoverable and the platform refuses to route to it (dependency rule **R4**, kill shadow AI).

## 5. Kill switch

To stop serving without losing catalog state: scale the Cloud Run service to zero, or remove
the runtime service account's AlloyDB client / Firestore user binding. The catalog store and
every registered AgentCard remain intact. Because discovery reads the catalog, tombstoning a
single agent is a lifecycle change instead (`governance.lifecycle: retired`), not a deploy.

## 6. Local operation and the gate

```bash
make run     # uvicorn on http://127.0.0.1:8083 (local profile, loopback)
make smoke   # register a card via the CLI, then list it back
make check   # the full gate: ruff check + ruff format --check + mypy src + pytest + eval
```

`make check` is the CI gate (`.github/workflows/ci.yaml`) and runs entirely offline on the
`local` profile with no Google Cloud SDKs installed. The CLI honours `HRZ_REGISTRY_PROFILE`;
under `onprem` every command exits `2` with the migration message (see
[`onprem-migration.md`](onprem-migration.md)).

## 7. Common failures

| Symptom | Likely cause | Fix |
|---|---|---|
| `NotImplementedError` from a CLI command / the API | `HRZ_REGISTRY_PROFILE=onprem` with placeholder adapters | Set `HRZ_REGISTRY_PROFILE=local` (or `gcp`), or implement the on-prem adapter |
| CLI exits `2` on every command | Running under the `onprem` profile by design | Switch to `local` or `gcp`; `2` is the intended fail-fast |
| `401` on `POST /v1/agents` | `HRZ_REGISTRY_S2S_TOKEN` set but no / wrong bearer token | Send `Authorization: Bearer <token>`, or unset the token for loopback dev |
| `403` on catalog routes under `gcp` | Caller service account not in the allowlist | Add it to `HRZ_REGISTRY_S2S_ALLOWED_CALLERS` |
| Rsk1 cannot resolve agents in `profile: platform` | `HRZ_REGISTRY_URL` not pointing at this service | Set it to the `service_url` output (defaults to `http://localhost:8083`) |
| A managed import fails under `local` | `[gcp]` extra not installed and a gcp branch was taken | Stay SDK-free on `local`, or `pip install -e ".[gcp]"` for the managed path |
