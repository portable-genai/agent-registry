# Private VPC + private-services access for AlloyDB private IP. Created only when AlloyDB is
# the backend (Firestore is serverless and needs no VPC).

resource "google_compute_network" "registry" {
  count                   = local.use_alloydb ? 1 : 0
  name                    = local.network_name
  project                 = var.project_id
  auto_create_subnetworks = false

  depends_on = [google_project_service.required]
}

resource "google_compute_subnetwork" "registry" {
  count                    = local.use_alloydb ? 1 : 0
  name                     = "${local.network_name}-subnet"
  project                  = var.project_id
  region                   = local.region
  network                  = google_compute_network.registry[0].id
  ip_cidr_range            = "10.20.0.0/24"
  private_ip_google_access = true
}

# Reserved range + private services connection so AlloyDB gets a private IP.
resource "google_compute_global_address" "psa_range" {
  count         = local.use_alloydb ? 1 : 0
  name          = "${local.network_name}-psa"
  project       = var.project_id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.registry[0].id
}

resource "google_service_networking_connection" "psa" {
  count                   = local.use_alloydb ? 1 : 0
  network                 = google_compute_network.registry[0].id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.psa_range[0].name]
}

# Serverless VPC connector so Cloud Run can reach AlloyDB's private IP.
resource "google_vpc_access_connector" "registry" {
  count          = local.use_alloydb ? 1 : 0
  name           = "hrz-registry-vpc-conn"
  project        = var.project_id
  region         = local.region
  network        = google_compute_network.registry[0].name
  ip_cidr_range  = "10.8.0.0/28"
  min_throughput = 200
  max_throughput = 300

  depends_on = [google_project_service.required]
}
