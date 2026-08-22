# CMEK — a regional Cloud KMS key ring + key in us-central1, used to encrypt the AlloyDB
# cluster (or Firestore) and the Cloud Run revision. Regional CMEK is what gives data
# residency; a global/multi-region key would not.

resource "google_kms_key_ring" "registry" {
  name     = local.kms_keyring
  location = local.region
  project  = var.project_id

  depends_on = [google_project_service.required]
}

resource "google_kms_crypto_key" "registry" {
  name            = local.kms_key_name
  key_ring        = google_kms_key_ring.registry.id
  rotation_period = "7776000s" # 90 days

  purpose = "ENCRYPT_DECRYPT"

  lifecycle {
    prevent_destroy = true
  }
}

# Service agents that must be able to use the CMEK key.

data "google_project" "this" {
  project_id = var.project_id
}

# AlloyDB service agent (only when AlloyDB is the backend).
resource "google_kms_crypto_key_iam_member" "alloydb" {
  count         = local.use_alloydb ? 1 : 0
  crypto_key_id = google_kms_crypto_key.registry.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-alloydb.iam.gserviceaccount.com"
}

# Cloud Run service agent (encrypts the revision with CMEK).
resource "google_kms_crypto_key_iam_member" "run" {
  crypto_key_id = google_kms_crypto_key.registry.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@serverless-robot-prod.iam.gserviceaccount.com"
}
