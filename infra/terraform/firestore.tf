# Firestore (Native mode) — the serverless alternative catalog store. Regional in
# us-central1 with CMEK. Created only when var.backend == "firestore".

resource "google_firestore_database" "registry" {
  count       = local.use_firestore ? 1 : 0
  project     = var.project_id
  name        = local.firestore_database
  location_id = local.region
  type        = "FIRESTORE_NATIVE"

  # Regional CMEK for residency.
  cmek_config {
    kms_key_name = google_kms_crypto_key.registry.id
  }

  # Guardrails so the catalog database is not deleted by accident.
  delete_protection_state = "DELETE_PROTECTION_ENABLED"
  deletion_policy         = "DELETE"

  depends_on = [
    google_project_service.required,
    google_kms_crypto_key.registry,
  ]
}
