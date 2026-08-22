# Concrete service identifiers for A3. Region is a validated deploy-time input.

locals {
  region = var.region

  service_name = "agent-registry"

  # Dedicated least-privilege runtime identity (Workload Identity; no keys).
  runtime_sa_id    = "hrz-registry-run"
  runtime_sa_email = "${local.runtime_sa_id}@${var.project_id}.iam.gserviceaccount.com"

  # CMEK — regional Cloud KMS key ring + key in us-central1.
  kms_keyring  = "agent-registry"
  kms_key_name = "registry-cmek"

  # AlloyDB catalog store.
  alloydb_cluster_id  = "hrz-registry-cluster"
  alloydb_instance_id = "hrz-registry-primary"
  alloydb_database    = "agent_registry"
  alloydb_user        = "registry_app"

  # Firestore catalog store (Native mode).
  firestore_database = "agent-registry"

  use_alloydb   = var.backend == "alloydb"
  use_firestore = var.backend == "firestore"

  # Whether a superuser password was supplied, as a plain bool. var.alloydb_password is
  # sensitive and that mark propagates into anything derived from it, including a for_each,
  # which Terraform refuses to iterate. Only the yes/no fact is unmarked here; the password
  # itself stays sensitive everywhere it is actually used.
  alloydb_password_supplied = nonsensitive(var.alloydb_password != "")

  # Private networking for AlloyDB private IP.
  network_name = "hrz-registry-vpc"

  required_apis = [
    "run.googleapis.com",
    "cloudkms.googleapis.com",
    "iam.googleapis.com",
    "compute.googleapis.com",
    "servicenetworking.googleapis.com",
    "alloydb.googleapis.com",
    "firestore.googleapis.com",
    "artifactregistry.googleapis.com",
    "orgpolicy.googleapis.com",
    "storage.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "accesscontextmanager.googleapis.com",
  ]
}
