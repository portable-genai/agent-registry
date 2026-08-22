# Residency and sovereignty enforced by Org Policy, parameterised by var.allowed_regions.
#
# The variable validation in variables.tf fails a `terraform plan` when var.region is outside
# the residency allowlist. That is a plan-time guard on THIS configuration only. The policies
# below are the platform-side guard: they refuse resource creation anywhere else in the
# project, including by hand in the console, and they are derived from the same variable, so a
# second enterprise or region is a tfvars change and never a fork.

# Resource-location allowlist. Values use the "in:<region>-locations" value group so a region
# also covers its multi-region and zonal children.
resource "google_org_policy_policy" "resource_locations" {
  name   = "projects/${var.project_id}/policies/gcp.resourceLocations"
  parent = "projects/${var.project_id}"

  spec {
    inherit_from_parent = false

    rules {
      values {
        allowed_values = [for r in var.allowed_regions : "in:${r}-locations"]
      }
    }
  }

  depends_on = [google_project_service.required]
}

# Sovereignty: no exported service-account keys. The runtime identity is Workload Identity
# only (see iam.tf), so key creation is disabled outright rather than merely unused.
resource "google_org_policy_policy" "disable_sa_keys" {
  name   = "projects/${var.project_id}/policies/iam.disableServiceAccountKeyCreation"
  parent = "projects/${var.project_id}"

  spec {
    inherit_from_parent = false

    rules {
      enforce = "TRUE"
    }
  }

  depends_on = [google_project_service.required]
}

# The catalog is a platform-internal service: no unauthenticated public Cloud Run invocation.
resource "google_org_policy_policy" "domain_restricted_sharing" {
  name   = "projects/${var.project_id}/policies/iam.allowedPolicyMemberDomains"
  parent = "projects/${var.project_id}"
  count  = length(var.allowed_member_domain_ids) > 0 ? 1 : 0

  spec {
    inherit_from_parent = false

    rules {
      values {
        allowed_values = var.allowed_member_domain_ids
      }
    }
  }

  depends_on = [google_project_service.required]
}
