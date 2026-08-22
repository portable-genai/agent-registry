# VPC Service Controls perimeter around the registry's managed stores, DRY RUN FIRST.
#
# Rollout discipline encoded here: the perimeter is created with `use_explicit_dry_run_spec`
# and only a `spec` block, so violations are logged and never blocked. An adopter watches the
# dry-run findings (see the posture alert in logging.tf), and only then sets
# `vpc_sc_enforce = true`, which promotes the same service list into `status`.
#
# Both blocks read the SAME locals, so enforcement cannot diverge from what dry run proved.
# The perimeter is created only when the adopter supplies an Access Context Manager policy
# (`access_policy_name`); it is org-level state that a project-scoped module must not invent.

locals {
  vpc_sc_enabled  = var.access_policy_name != ""
  vpc_sc_resource = "projects/${data.google_project.this.number}"
}

resource "google_access_context_manager_service_perimeter" "registry" {
  count = local.vpc_sc_enabled ? 1 : 0

  parent = "accessPolicies/${var.access_policy_name}"
  name   = "accessPolicies/${var.access_policy_name}/servicePerimeters/${replace(local.service_name, "-", "_")}"
  title  = "Hrz3 agent registry data perimeter"

  perimeter_type = "PERIMETER_TYPE_REGULAR"

  # Dry run stays declared even after enforcement, so a later service addition can be
  # rehearsed in dry run before it starts blocking traffic.
  use_explicit_dry_run_spec = true

  spec {
    resources           = [local.vpc_sc_resource]
    restricted_services = var.vpc_sc_restricted_services
  }

  dynamic "status" {
    for_each = var.vpc_sc_enforce ? [1] : []
    content {
      resources           = [local.vpc_sc_resource]
      restricted_services = var.vpc_sc_restricted_services
    }
  }

  lifecycle {
    precondition {
      condition     = !var.vpc_sc_enforce || var.access_policy_name != ""
      error_message = "vpc_sc_enforce requires access_policy_name; enforcement cannot be requested without a perimeter."
    }
  }
}
