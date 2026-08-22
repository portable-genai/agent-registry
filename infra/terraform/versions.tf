terraform {
  # Cross-variable input validation (region in allowed_regions) requires Terraform 1.9+.
  required_version = ">= 1.9.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.40, < 7.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 5.40, < 7.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = local.region
}

provider "google-beta" {
  project = var.project_id
  region  = local.region
}
