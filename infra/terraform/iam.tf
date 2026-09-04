# Dedicated least-privilege runtime identity for the Cloud Run service. Cloud Run uses this
# service account as its identity via Workload Identity — no exported keys anywhere.

resource "google_service_account" "runtime" {
  account_id   = local.runtime_sa_id
  display_name = "A3 Agent Registry — Cloud Run runtime"
  project      = var.project_id

  depends_on = [google_project_service.required]
}

# AlloyDB access (only when AlloyDB is the backend): client + IAM DB login, nothing more.
resource "google_project_iam_member" "runtime_alloydb_client" {
  count   = local.use_alloydb ? 1 : 0
  project = var.project_id
  role    = "roles/alloydb.client"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "runtime_alloydb_login" {
  count   = local.use_alloydb ? 1 : 0
  project = var.project_id
  role    = "roles/alloydb.databaseUser"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# Firestore access (only when Firestore is the backend): scoped to the user role.
resource "google_project_iam_member" "runtime_firestore_user" {
  count   = local.use_firestore ? 1 : 0
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# Service-control / telemetry: the runtime needs to mint its own ID tokens for outbound A2A
# calls and write metrics; both are minimal.
resource "google_project_iam_member" "runtime_token_creator" {
  project = var.project_id
  role    = "roles/iam.serviceAccountTokenCreator"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "runtime_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# agent-registry verifies evidence directly under its keyless Cloud Run workload identity.
resource "google_cloud_run_v2_service_iam_member" "quality_evidence_reader" {
  project  = var.quality_service_project_id != "" ? var.quality_service_project_id : var.project_id
  location = local.region
  name     = var.quality_service_name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service_iam_member" "observability_evidence_reader" {
  project  = var.observability_service_project_id != "" ? var.observability_service_project_id : var.project_id
  location = local.region
  name     = var.observability_service_name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service_iam_member" "registry_callers" {
  for_each = toset(var.caller_service_accounts)
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.registry.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${each.value}"
}
