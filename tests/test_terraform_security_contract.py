from __future__ import annotations

from pathlib import Path

_TF = Path(__file__).parents[1] / "infra" / "terraform"


def test_managed_registry_wires_fail_closed_inbound_identity() -> None:
    cloud_run = (_TF / "cloud_run.tf").read_text(encoding="utf-8")
    variables = (_TF / "variables.tf").read_text(encoding="utf-8")
    iam = (_TF / "iam.tf").read_text(encoding="utf-8")

    assert "HRZ_REGISTRY_S2S_AUDIENCE" in cloud_run
    assert "HRZ_REGISTRY_S2S_ALLOWED_CALLERS" in cloud_run
    assert "length(var.caller_service_accounts) > 0" in variables
    assert 'role     = "roles/run.invoker"' in iam
    assert "var.caller_service_accounts" in iam


# --------------------------------------------------------------------------------------- #
# D5: residency and sovereignty posture-as-code. Live enforcement proof needs a real GCP
# project; what is testable offline is that the posture is declared, parameterised from one
# allowlist, and rolled out dry-run first.
# --------------------------------------------------------------------------------------- #


def test_org_policy_pins_resource_locations_to_the_same_allowlist() -> None:
    org_policy = (_TF / "org_policy.tf").read_text(encoding="utf-8")

    assert "constraints/gcp.resourceLocations" not in org_policy  # v2 policies use the name
    assert "policies/gcp.resourceLocations" in org_policy
    assert 'for r in var.allowed_regions : "in:${r}-locations"' in org_policy
    # Sovereignty: keyless runtime identity is enforced, not merely conventional.
    assert "policies/iam.disableServiceAccountKeyCreation" in org_policy


def test_vpc_sc_perimeter_is_dry_run_first() -> None:
    vpc_sc = (_TF / "vpc_sc.tf").read_text(encoding="utf-8")
    variables = (_TF / "variables.tf").read_text(encoding="utf-8")

    assert "google_access_context_manager_service_perimeter" in vpc_sc
    assert "use_explicit_dry_run_spec = true" in vpc_sc
    # The enforcing `status` block is conditional on an explicit opt-in that defaults false.
    assert "for_each = var.vpc_sc_enforce ? [1] : []" in vpc_sc
    assert 'variable "vpc_sc_enforce" {' in variables
    enforce_block = variables.split('variable "vpc_sc_enforce" {')[1].split("\n}")[0]
    assert "default     = false" in enforce_block


def test_worm_log_bucket_has_locked_retention_and_cmek() -> None:
    logging_tf = (_TF / "logging.tf").read_text(encoding="utf-8")
    variables = (_TF / "variables.tf").read_text(encoding="utf-8")

    assert "retention_policy {" in logging_tf
    assert "is_locked        = var.log_bucket_locked" in logging_tf
    assert "default_kms_key_name = google_kms_crypto_key.registry.id" in logging_tf
    assert "google_logging_project_sink" in logging_tf
    assert "unique_writer_identity = true" in logging_tf
    assert "var.log_retention_days >= 365" in variables

    locked_block = variables.split('variable "log_bucket_locked" {')[1].split("\n}")[0]
    assert "default     = true" in locked_block


def test_posture_alerts_watch_the_dry_run_and_residency_denials() -> None:
    logging_tf = (_TF / "logging.tf").read_text(encoding="utf-8")

    assert 'google_monitoring_alert_policy" "vpc_sc_dry_run_violation' in logging_tf
    assert 'protoPayload.metadata.dryRun=\\"true\\"' in logging_tf
    assert 'google_monitoring_alert_policy" "residency_denial' in logging_tf
    assert "constraints/gcp.resourceLocations" in logging_tf


def test_cmek_is_bound_per_service_not_project_wide() -> None:
    kms = (_TF / "kms.tf").read_text(encoding="utf-8")
    logging_tf = (_TF / "logging.tf").read_text(encoding="utf-8")
    cloud_run = (_TF / "cloud_run.tf").read_text(encoding="utf-8")

    assert "gcp-sa-alloydb.iam.gserviceaccount.com" in kms
    assert "serverless-robot-prod.iam.gserviceaccount.com" in kms
    assert "gs-project-accounts.iam.gserviceaccount.com" in logging_tf
    assert "encryption_key                   = google_kms_crypto_key.registry.id" in cloud_run


def test_region_and_allowlist_reach_the_runtime_as_configuration() -> None:
    cloud_run = (_TF / "cloud_run.tf").read_text(encoding="utf-8")

    assert "HRZ_REGISTRY_ALLOWED_REGIONS" in cloud_run
    assert 'join(",", var.allowed_regions)' in cloud_run
