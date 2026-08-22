# AlloyDB for PostgreSQL — the A3 catalog store (default backend). Regional in
# us-central1, private IP only, encrypted with the regional CMEK key. Created only when
# var.backend == "alloydb".

resource "google_alloydb_cluster" "registry" {
  count      = local.use_alloydb ? 1 : 0
  cluster_id = local.alloydb_cluster_id
  location   = local.region
  project    = var.project_id

  network_config {
    network = google_compute_network.registry[0].id
  }

  encryption_config {
    kms_key_name = google_kms_crypto_key.registry.id
  }

  dynamic "initial_user" {
    for_each = local.alloydb_password_supplied ? [1] : []
    content {
      user     = "postgres"
      password = var.alloydb_password
    }
  }

  depends_on = [
    google_service_networking_connection.psa,
    google_kms_crypto_key_iam_member.alloydb,
  ]
}

resource "google_alloydb_instance" "primary" {
  count         = local.use_alloydb ? 1 : 0
  cluster       = google_alloydb_cluster.registry[0].name
  instance_id   = local.alloydb_instance_id
  instance_type = "PRIMARY"

  machine_config {
    cpu_count = 2
  }

  # Private IP only — no public exposure of the catalog store.
  network_config {
    enable_public_ip = false
  }
}

# Grant the runtime service account IAM DB login on the cluster.
resource "google_alloydb_user" "runtime" {
  count          = local.use_alloydb ? 1 : 0
  cluster        = google_alloydb_cluster.registry[0].name
  user_id        = trimsuffix(google_service_account.runtime.email, ".gserviceaccount.com")
  user_type      = "ALLOYDB_IAM_USER"
  database_roles = ["alloydbiamuser"]

  depends_on = [google_alloydb_instance.primary]
}
