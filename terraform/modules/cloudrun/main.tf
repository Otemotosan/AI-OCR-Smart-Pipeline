# Cloud Run Module - API and UI Services
# Creates Cloud Run services for the Review UI.

# ============================================================
# API Service
# ============================================================

resource "google_cloud_run_v2_service" "api" {
  count    = var.api_image != "" ? 1 : 0
  name     = "ocr-api-${var.environment}"
  project  = var.project_id
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = var.service_account

    scaling {
      max_instance_count = 10
      min_instance_count = 0
    }

    containers {
      image = var.api_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }

      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 5
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/health"
        }
        period_seconds    = 30
        failure_threshold = 3
      }
    }
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
    component   = "api"
  }
}

# Allow unauthenticated access (IAP will handle auth)
resource "google_cloud_run_v2_service_iam_member" "api_invoker" {
  count    = var.api_image != "" ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ============================================================
# UI Service
# ============================================================

resource "google_cloud_run_v2_service" "ui" {
  count    = var.ui_image != "" ? 1 : 0
  name     = "ocr-ui-${var.environment}"
  project  = var.project_id
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = var.service_account

    scaling {
      max_instance_count = 5
      min_instance_count = 0
    }

    containers {
      image = var.ui_image

      ports {
        container_port = 80
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "256Mi"
        }
      }

      env {
        name  = "API_URL"
        value = var.api_image != "" ? google_cloud_run_v2_service.api[0].uri : ""
      }

      startup_probe {
        http_get {
          path = "/"
        }
        initial_delay_seconds = 2
        period_seconds        = 5
        failure_threshold     = 3
      }
    }
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  labels = {
    environment = var.environment
    service     = "ocr-pipeline"
    component   = "ui"
  }
}

# Allow unauthenticated access (IAP will handle auth)
resource "google_cloud_run_v2_service_iam_member" "ui_invoker" {
  count    = var.ui_image != "" ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.ui[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ============================================================
# Load Balancer with IAP (optional, when domains provided)
# ============================================================

# Backend service for API
resource "google_compute_backend_service" "api" {
  count                 = var.api_domain != "" && var.api_image != "" ? 1 : 0
  name                  = "ocr-api-backend-${var.environment}"
  project               = var.project_id
  protocol              = "HTTP"
  port_name             = "http"
  timeout_sec           = 30
  enable_cdn            = false
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group = google_compute_region_network_endpoint_group.api[0].id
  }

  iap {
    oauth2_client_id     = var.iap_oauth_client_id
    oauth2_client_secret = var.iap_oauth_client_secret
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# Network endpoint group for Cloud Run API
resource "google_compute_region_network_endpoint_group" "api" {
  count                 = var.api_domain != "" && var.api_image != "" ? 1 : 0
  name                  = "ocr-api-neg-${var.environment}"
  project               = var.project_id
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.api[0].name
  }
}

# Backend service for UI
resource "google_compute_backend_service" "ui" {
  count                 = var.ui_domain != "" && var.ui_image != "" ? 1 : 0
  name                  = "ocr-ui-backend-${var.environment}"
  project               = var.project_id
  protocol              = "HTTP"
  port_name             = "http"
  timeout_sec           = 30
  enable_cdn            = true
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group = google_compute_region_network_endpoint_group.ui[0].id
  }

  iap {
    oauth2_client_id     = var.iap_oauth_client_id
    oauth2_client_secret = var.iap_oauth_client_secret
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# Network endpoint group for Cloud Run UI
resource "google_compute_region_network_endpoint_group" "ui" {
  count                 = var.ui_domain != "" && var.ui_image != "" ? 1 : 0
  name                  = "ocr-ui-neg-${var.environment}"
  project               = var.project_id
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.ui[0].name
  }
}
