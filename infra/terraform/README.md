# Hrz3 Agent Registry: Terraform

Provisions the GCP footprint for **Hrz3 `agent-registry`**. The region is configurable,
defaults to **`us-central1`**, and must be in `allowed_regions`. The catalog store backend is
selectable (`alloydb` default, or `firestore`).

## What it creates

| Concern | Resource(s) |
|---|---|
| **Cloud Run** | `google_cloud_run_v2_service.registry`: v2 service `agent-registry`, internal+LB ingress, min 1 instance, **CMEK-encrypted**, runs as the dedicated runtime SA, `:8083`, `/healthz` probes. |
| **AlloyDB** (default) | Regional cluster + primary instance, **private IP only**, **CMEK**; IAM DB user for the runtime SA. Plus VPC, private-services access and a Serverless VPC connector. |
| **Firestore** (alt.) | `google_firestore_database` Native mode in `us-central1` with **CMEK** and delete protection. |
| **IAM / Workload Identity** | A least-privilege runtime service account; Cloud Run uses it as its identity, **no exported keys**. Scoped to `alloydb.client`+`alloydb.databaseUser` (or `datastore.user`), token creation and metric writes. |
| **CMEK** | Regional Cloud KMS key ring + key in `us-central1` (90-day rotation), granted to the AlloyDB / Firestore and Cloud Run service agents. |
| **Org Policy** | `gcp.resourceLocations` allowlist derived from `allowed_regions`, `iam.disableServiceAccountKeyCreation` enforced, optional domain-restricted sharing. |
| **VPC Service Controls** | A regular perimeter around the managed stores, created DRY RUN FIRST (`use_explicit_dry_run_spec`); enforcement is the separate `vpc_sc_enforce` opt-in. |
| **WORM audit logs** | Regional, CMEK-encrypted bucket with a LOCKED retention policy plus a project log sink (admin activity, data access, policy) with a unique writer identity. |
| **Posture alerts** | Log-based Monitoring alerts on VPC-SC dry-run violations and on `gcp.resourceLocations` denials, so the enforcement flip is evidence-led. |

## Usage

```bash
terraform init

# Default backend (AlloyDB):
terraform apply -var="project_id=my-gcp-project"

# Firestore backend instead:
terraform apply -var="project_id=my-gcp-project" -var="backend=firestore"
```

Build and push the image to Artifact Registry first, then pass it in:

```bash
terraform apply \
  -var="project_id=my-gcp-project" \
  -var="container_image=us-central1-docker.pkg.dev/my-gcp-project/hrz/agent-registry:0.1.0"
```

## Variables

| Name | Default | Notes |
|---|---|---|
| `project_id` | n/a (**required**) | The only per-tenant input. |
| `region` | `us-central1` | Selected regional deployment location. |
| `allowed_regions` | `["us-central1"]` | Governance-approved residency locations. |
| `backend` | `alloydb` | `alloydb` \| `firestore`. |
| `container_image` | placeholder Artifact Registry path | Override with your pushed image. |
| `alloydb_password` | `""` (sensitive) | Optional initial superuser password; IAM auth is used otherwise. |
| `access_policy_name` | `""` | Access Context Manager policy id. Empty means no perimeter is managed here. |
| `vpc_sc_enforce` | `false` | Dry run first. Flip only after the dry-run alert is quiet. |
| `vpc_sc_restricted_services` | AlloyDB, Firestore, Storage, KMS, Logging | Identical in the dry-run spec and in enforcement. |
| `log_retention_days` | `400` | Locked WORM retention; the validation floor is 365. |
| `log_bucket_locked` | `true` | Locking is irreversible; `false` is for sandbox projects only. |
| `allowed_member_domain_ids` | `[]` | Cloud Identity customer ids for domain-restricted sharing. |
| `notification_channels` | `[]` | Monitoring channels for the posture alerts. |

## Outputs

`service_url`, `well_known_card_url`, `runtime_service_account`, `cmek_key`, `backend`,
`alloydb_instance`, `firestore_database`.

## Notes

- The CMEK key has `prevent_destroy = true`; AlloyDB/Firestore have delete protection. Plan
  removals deliberately.
- `region` is validated against `allowed_regions`; extend that allowlist only after the
  deployment's residency review.
- Wiring is environment-variable driven; the same `config/settings.yaml` is used in every
  environment via `${ENV:-default}` interpolation.
- Residency is enforced three times from one allowlist: `terraform plan` validation, the
  `gcp.resourceLocations` Org Policy, and a fail-closed check when the application loads its
  settings (`HRZ_REGISTRY_ALLOWED_REGIONS`, see `src/agent_registry/config.py`).
- The VPC-SC perimeter starts in dry run. Watch the `Hrz3 registry: VPC-SC dry-run violation`
  alert until it is silent, then set `vpc_sc_enforce = true`. The same service list is used in
  both modes, so enforcement cannot exceed what dry run rehearsed.
- Locking the log bucket retention cannot be undone. Keep `log_bucket_locked = false` in
  sandboxes and `true` everywhere a regulator would look.
- `terraform fmt -check` and `terraform validate` run in CI with no cloud credentials
  (`.github/workflows/ci.yaml`, job `terraform`). Applying this configuration against a real
  project, and the live enforcement evidence that follows, is deployment work, not repo work.
