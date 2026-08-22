output "service_url" {
  description = "Base URL of the A3 Cloud Run service."
  value       = google_cloud_run_v2_service.registry.uri
}

output "service_name" {
  description = "Cloud Run service name."
  value       = google_cloud_run_v2_service.registry.name
}

output "runtime_service_account" {
  description = "Least-privilege runtime identity (Workload Identity) used by Cloud Run."
  value       = google_service_account.runtime.email
}

output "cloud_run_service_uri" {
  description = "Actual Cloud Run service URI; use it as public_service_url when no load balancer is present."
  value       = google_cloud_run_v2_service.registry.uri
}

output "cmek_key" {
  description = "Regional CMEK key protecting the catalog store and Cloud Run revision."
  value       = google_kms_crypto_key.registry.id
}

output "backend" {
  description = "Active catalog store backend."
  value       = var.backend
}

output "alloydb_instance" {
  description = "AlloyDB primary instance resource name (empty when backend = firestore)."
  value       = local.use_alloydb ? google_alloydb_instance.primary[0].name : ""
}

output "firestore_database" {
  description = "Firestore database name (empty when backend = alloydb)."
  value       = local.use_firestore ? google_firestore_database.registry[0].name : ""
}

output "well_known_card_url" {
  description = "A2A discovery URL for the registry's own AgentCard."
  value       = "${google_cloud_run_v2_service.registry.uri}/.well-known/agent-card.json"
}

output "audit_log_bucket" {
  description = "WORM (locked-retention, CMEK) bucket holding the control-plane audit log sink."
  value       = google_storage_bucket.audit_logs.name
}

output "vpc_sc_perimeter_mode" {
  description = "dry-run, enforced, or none (no access_policy_name supplied)."
  value       = local.vpc_sc_enabled ? (var.vpc_sc_enforce ? "enforced" : "dry-run") : "none"
}

output "allowed_regions" {
  description = "Residency allowlist enforced at plan time and by Org Policy."
  value       = var.allowed_regions
}
