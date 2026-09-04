# WORM log sink and posture alerts.
#
# Audit CONTENT for agent activity is agent-observability's job (COMPLIANCE P-07). What lives here is the
# platform-side, tamper-evident retention of the control-plane's own admin and data-access
# audit logs: a regional, CMEK-encrypted bucket with a LOCKED retention policy, which no
# principal (including a project owner) can shorten or delete early.

resource "google_storage_bucket" "audit_logs" {
  name     = "${var.project_id}-${local.service_name}-audit"
  project  = var.project_id
  location = upper(local.region)

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  # WORM: once locked, the retention period can be raised but never lowered or removed, and
  # objects cannot be deleted or overwritten before it expires.
  retention_policy {
    retention_period = var.log_retention_days * 24 * 60 * 60
    is_locked        = var.log_bucket_locked
  }

  versioning {
    enabled = true
  }

  encryption {
    default_kms_key_name = google_kms_crypto_key.registry.id
  }

  depends_on = [
    google_project_service.required,
    google_kms_crypto_key_iam_member.storage,
  ]
}

# The Cloud Storage service agent must be able to use the regional CMEK key.
resource "google_kms_crypto_key_iam_member" "storage" {
  crypto_key_id = google_kms_crypto_key.registry.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gs-project-accounts.iam.gserviceaccount.com"
}

resource "google_logging_project_sink" "audit_to_worm" {
  name        = "${local.service_name}-audit-worm"
  project     = var.project_id
  destination = "storage.googleapis.com/${google_storage_bucket.audit_logs.name}"

  filter = join(" OR ", [
    "logName:\"cloudaudit.googleapis.com%2Factivity\"",
    "logName:\"cloudaudit.googleapis.com%2Fdata_access\"",
    "logName:\"cloudaudit.googleapis.com%2Fpolicy\"",
  ])

  unique_writer_identity = true
}

resource "google_storage_bucket_iam_member" "sink_writer" {
  bucket = google_storage_bucket.audit_logs.name
  role   = "roles/storage.objectCreator"
  member = google_logging_project_sink.audit_to_worm.writer_identity
}

# ------------------------------------------------------------------------------------- #
# Posture alerts. These are what make "dry run first" a workflow rather than a comment:
# the dry-run perimeter emits a violation log instead of blocking, and this alert routes it
# to the platform team so the enforcement flip is evidence-led.
# ------------------------------------------------------------------------------------- #

resource "google_monitoring_alert_policy" "vpc_sc_dry_run_violation" {
  count = local.vpc_sc_enabled ? 1 : 0

  project      = var.project_id
  display_name = "agent-registry: VPC-SC dry-run violation"
  combiner     = "OR"

  conditions {
    display_name = "VPC Service Controls dry-run denial"
    condition_matched_log {
      filter = join(" AND ", [
        "protoPayload.metadata.@type=\"type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata\"",
        "protoPayload.metadata.dryRun=\"true\"",
        "resource.labels.project_id=\"${var.project_id}\"",
      ])
    }
  }

  alert_strategy {
    notification_rate_limit {
      period = "300s"
    }
  }

  notification_channels = var.notification_channels

  documentation {
    content   = "A call would have been blocked by the agent-registry perimeter. Review before setting vpc_sc_enforce = true."
    mime_type = "text/markdown"
  }
}

resource "google_monitoring_alert_policy" "residency_denial" {
  project      = var.project_id
  display_name = "agent-registry: resource-location policy denial"
  combiner     = "OR"

  conditions {
    display_name = "Org Policy denied a resource outside the residency allowlist"
    condition_matched_log {
      filter = join(" AND ", [
        "protoPayload.status.message:\"constraints/gcp.resourceLocations\"",
        "resource.labels.project_id=\"${var.project_id}\"",
      ])
    }
  }

  alert_strategy {
    notification_rate_limit {
      period = "300s"
    }
  }

  notification_channels = var.notification_channels

  documentation {
    content   = "Something tried to create a resource outside allowed_regions. Residency posture held; investigate the caller."
    mime_type = "text/markdown"
  }
}
