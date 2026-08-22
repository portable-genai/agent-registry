# Enable the Google APIs A3 depends on. Services are not destroyed on `terraform destroy`
# to avoid tearing down APIs shared with other workloads in the project.

resource "google_project_service" "required" {
  for_each = toset(local.required_apis)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
