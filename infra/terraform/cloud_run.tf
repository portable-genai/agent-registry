# Cloud Run v2 service for A3. Runs as the dedicated least-privilege runtime identity
# (Workload Identity, no keys), encrypted with the regional CMEK key, in us-central1.
# Environment variables drive the settings.yaml ${ENV:-default} interpolation so no code or
# config file changes between environments.

resource "google_cloud_run_v2_service" "registry" {
  name     = local.service_name
  location = local.region
  project  = var.project_id

  # Internal + load balancer ingress — the registry is a platform-internal service.
  ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  # Encrypt the revision with the regional CMEK key.
  template {
    encryption_key                   = google_kms_crypto_key.registry.id
    service_account                  = google_service_account.runtime.email
    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = 1
      max_instance_count = 4
    }

    # Attach the VPC connector for AlloyDB private IP (no-op block for Firestore).
    dynamic "vpc_access" {
      for_each = local.use_alloydb ? [1] : []
      content {
        connector = google_vpc_access_connector.registry[0].id
        egress    = "PRIVATE_RANGES_ONLY"
      }
    }

    containers {
      image = var.container_image

      ports {
        container_port = 8083
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "AGENT_REGISTRY_PROFILE"
        value = "gcp"
      }
      env {
        name  = "AGENT_REGISTRY_S2S_AUDIENCE"
        value = var.service_audience
      }
      env {
        name  = "AGENT_REGISTRY_S2S_ALLOWED_CALLERS"
        value = join(",", var.caller_service_accounts)
      }
      env {
        name  = "AGENT_REGISTRY_BACKEND"
        value = var.backend
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "AGENT_REGISTRY_ALLOWED_REGIONS"
        value = join(",", var.allowed_regions)
      }
      env {
        name  = "AGENT_REGISTRY_KMS_KEY"
        value = google_kms_crypto_key.registry.id
      }
      env {
        name  = "AGENT_REGISTRY_PUBLIC_URL"
        value = var.public_service_url
      }
      env {
        name  = "QUALITY_GATE_URL"
        value = var.quality_service_url
      }
      env {
        name  = "OBSERVABILITY_URL"
        value = var.observability_service_url
      }
      env {
        name  = "RELEASE_POLICY_VERSION"
        value = var.release_policy_version
      }
      env {
        name  = "RELEASE_DATASET_ID"
        value = var.release_dataset_id
      }
      env {
        name  = "RELEASE_DATASET_VERSION"
        value = var.release_dataset_version
      }
      env {
        name  = "RELEASE_DATASET_DIGEST"
        value = var.release_dataset_digest
      }
      env {
        name  = "RELEASE_EVALUATOR"
        value = var.release_evaluator
      }
      env {
        name  = "RELEASE_THRESHOLD_POLICY_DIGEST"
        value = var.release_threshold_policy_digest
      }
      env {
        name  = "RELEASE_ARTIFACT_PREFIXES"
        value = join(",", var.release_artifact_prefixes)
      }
      env {
        name  = "RELEASE_REDTEAM_CATEGORIES"
        value = join(",", var.release_redteam_categories)
      }

      # AlloyDB wiring (rendered only when AlloyDB is the backend).
      dynamic "env" {
        for_each = local.use_alloydb ? [1] : []
        content {
          name  = "AGENT_REGISTRY_ALLOYDB_URI"
          value = google_alloydb_instance.primary[0].name
        }
      }

      # Firestore wiring (rendered only when Firestore is the backend).
      dynamic "env" {
        for_each = local.use_firestore ? [1] : []
        content {
          name  = "AGENT_REGISTRY_FIRESTORE_DB"
          value = google_firestore_database.registry[0].name
        }
      }

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8083
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 6
      }

      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8083
        }
        period_seconds = 30
      }
    }
  }

  depends_on = [
    google_kms_crypto_key_iam_member.run,
    google_project_iam_member.runtime_alloydb_client,
    google_project_iam_member.runtime_firestore_user,
  ]
}
