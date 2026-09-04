# Only the project id (and other genuinely per-tenant inputs) are variables. Every other
# deployment region is an explicit, validated input.

variable "project_id" {
  type        = string
  description = "GCP project id that hosts A3 (the only required per-tenant input)."
}

variable "allowed_regions" {
  type        = list(string)
  default     = ["asia-southeast1"]
  description = "Residency-approved deployment regions."

  validation {
    condition     = length(var.allowed_regions) > 0
    error_message = "allowed_regions must contain at least one approved GCP region."
  }
}

variable "region" {
  type        = string
  default     = "asia-southeast1"
  description = "Deployment region, validated against allowed_regions."

  validation {
    condition     = contains(var.allowed_regions, var.region)
    error_message = "region must be present in allowed_regions."
  }
}

variable "backend" {
  type        = string
  default     = "alloydb"
  description = "Catalog store for the gcp profile: 'alloydb' (default) or 'firestore'."

  validation {
    condition     = contains(["alloydb", "firestore"], var.backend)
    error_message = "backend must be 'alloydb' or 'firestore'."
  }
}

variable "container_image" {
  type        = string
  default     = "asia-southeast1-docker.pkg.dev/REPLACE_WITH_PROJECT/hrz/agent-registry:0.1.0"
  description = "Fully-qualified image for the Cloud Run service."
}

variable "public_service_url" {
  type        = string
  description = "Canonical HTTPS Cloud Run or load-balancer URL published in the registry card."

  validation {
    condition     = startswith(var.public_service_url, "https://")
    error_message = "public_service_url must use HTTPS."
  }
}

variable "service_audience" {
  type        = string
  description = "Canonical HTTPS audience accepted for inbound service ID tokens."

  validation {
    condition     = startswith(var.service_audience, "https://")
    error_message = "service_audience must use HTTPS."
  }
}

variable "caller_service_accounts" {
  type        = list(string)
  description = "Service-account emails allowed to call protected registry endpoints."

  validation {
    condition     = length(var.caller_service_accounts) > 0
    error_message = "at least one registry caller identity is required."
  }
}

variable "quality_service_url" {
  type        = string
  description = "HTTPS base URL of the model-quality-gate AI Quality service."

  validation {
    condition     = startswith(var.quality_service_url, "https://")
    error_message = "quality_service_url must use HTTPS."
  }
}

variable "observability_service_url" {
  type        = string
  description = "HTTPS base URL of the agent-observability service."

  validation {
    condition     = startswith(var.observability_service_url, "https://")
    error_message = "observability_service_url must use HTTPS."
  }
}

variable "quality_service_project_id" {
  type        = string
  default     = ""
  description = "Project hosting model-quality-gate; empty means project_id."
}

variable "quality_service_name" {
  type        = string
  default     = "model-quality-gate"
  description = "Cloud Run service name for model-quality-gate."
}

variable "observability_service_project_id" {
  type        = string
  default     = ""
  description = "Project hosting agent-observability; empty means project_id."
}

variable "observability_service_name" {
  type        = string
  default     = "agent-observability"
  description = "Cloud Run service name for agent-observability."
}

variable "release_policy_version" {
  type        = string
  description = "Immutable registry-owned release policy version."
}

variable "release_dataset_id" {
  type        = string
  description = "Approved model-quality-gate golden dataset ID for registry releases."
}

variable "release_dataset_version" {
  type        = string
  description = "Approved immutable version label of the release golden dataset."
}

variable "release_dataset_digest" {
  type        = string
  description = "Approved content digest of the release golden dataset."
}

variable "release_evaluator" {
  type        = string
  description = "Approved managed evaluator identity."
}

variable "release_threshold_policy_digest" {
  type        = string
  description = "Approved digest of metric names and thresholds."
}

variable "release_artifact_prefixes" {
  type        = list(string)
  description = "Required immutable managed-evaluation artifact URI prefixes."
}

variable "release_redteam_categories" {
  type        = list(string)
  description = "Required passing red-team categories."
}

variable "alloydb_password" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Initial AlloyDB superuser password. Leave empty to rely on IAM auth only."
}

# --------------------------------------------------------------------------------------- #
# Residency / sovereignty posture (D5). Everything here is an input: a second enterprise or
# region is a tfvars file, never a fork of this configuration.
# --------------------------------------------------------------------------------------- #

variable "allowed_member_domain_ids" {
  type        = list(string)
  default     = []
  description = "Cloud Identity customer IDs allowed in IAM policies (domain-restricted sharing). Empty disables the constraint."
}

variable "access_policy_name" {
  type        = string
  default     = ""
  description = "Access Context Manager policy id that owns the VPC-SC perimeter. Empty means no perimeter is managed here."
}

variable "vpc_sc_enforce" {
  type        = bool
  default     = false
  description = "Promote the VPC-SC perimeter from dry run to enforcement. Dry run first: leave false until the dry-run alert is quiet."
}

variable "vpc_sc_restricted_services" {
  type = list(string)
  default = [
    "alloydb.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "cloudkms.googleapis.com",
    "logging.googleapis.com",
  ]
  description = "Services fenced by the perimeter, identical in the dry-run spec and in enforcement."

  validation {
    condition     = length(var.vpc_sc_restricted_services) > 0
    error_message = "the perimeter must restrict at least one service."
  }
}

variable "log_retention_days" {
  type        = number
  default     = 400
  description = "Locked WORM retention for control-plane audit logs, in days."

  validation {
    condition     = var.log_retention_days >= 365
    error_message = "log_retention_days must be at least 365 to satisfy the platform retention floor."
  }
}

variable "log_bucket_locked" {
  type        = bool
  default     = true
  description = "Lock the retention policy (WORM). Irreversible; false is for sandbox projects only."
}

variable "notification_channels" {
  type        = list(string)
  default     = []
  description = "Monitoring notification channel ids for the posture alerts."
}
