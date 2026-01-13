# Security Architecture

**Spec ID**: 08  
**Status**: Final  
**Dependencies**: Cloud IAM, Cloud KMS, IAP

---

## 1. Design Principles

1. **Least Privilege**: Each component gets minimum required permissions
2. **Defense in Depth**: Multiple security layers
3. **Encryption Everywhere**: CMEK for data at rest, TLS for transit
4. **Audit Everything**: Comprehensive logging for compliance

---

## 2. Service Account Design

### 2.1 Account Matrix

| Service Account | Purpose | Permissions |
|-----------------|---------|-------------|
| `sa-ocr-processor` | Cloud Function (main pipeline) | Doc AI, Gemini API |
| `sa-storage-manager` | File operations | GCS read/write (scoped buckets) |
| `sa-database-writer` | Data persistence | BigQuery insert, Firestore write |
| `sa-review-ui` | Human review application | GCS read, BigQuery read, SQL read |

### 2.2 Permission Details

```yaml
# terraform/iam.tf (conceptual)

# OCR Processor - AI/ML only
sa-ocr-processor:
  roles:
    - roles/documentai.apiUser
    - roles/aiplatform.user
  # No storage, no database access

# Storage Manager - Files only
sa-storage-manager:
  roles:
    - roles/storage.objectAdmin  # Scoped to specific buckets
  resource_conditions:
    - "resource.name.startsWith('projects/_/buckets/ocr-input')"
    - "resource.name.startsWith('projects/_/buckets/ocr-output')"

# Database Writer - Persistence only
sa-database-writer:
  roles:
    - roles/bigquery.dataEditor  # Scoped to dataset
    - roles/datastore.user       # Firestore
    - roles/cloudsql.client      # Cloud SQL
  # No storage access, no AI access

# Review UI - Read-heavy
sa-review-ui:
  roles:
    - roles/storage.objectViewer  # Read only
    - roles/bigquery.dataViewer   # Read only
    - roles/cloudsql.client       # Read queries
```

### 2.3 Implementation

```python
# Cloud Function with multiple service accounts
# main.py

from google.auth import impersonated_credentials
from google.auth import default

def get_storage_credentials():
    """Get credentials for storage operations."""
    source_credentials, _ = default()
    
    return impersonated_credentials.Credentials(
        source_credentials=source_credentials,
        target_principal="sa-storage-manager@project.iam.gserviceaccount.com",
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        lifetime=300  # 5 minutes
    )

def get_database_credentials():
    """Get credentials for database operations."""
    source_credentials, _ = default()
    
    return impersonated_credentials.Credentials(
        source_credentials=source_credentials,
        target_principal="sa-database-writer@project.iam.gserviceaccount.com",
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
        lifetime=300
    )
```

---

## 3. Encryption Strategy

### 3.1 Overview

| Data State | Method | Key Management |
|------------|--------|----------------|
| At Rest (GCS) | AES-256-GCM | CMEK |
| At Rest (BigQuery) | AES-256-GCM | CMEK |
| At Rest (Cloud SQL) | AES-256-GCM | CMEK |
| At Rest (Firestore) | AES-256-GCM | Google-managed |
| In Transit | TLS 1.3 | Google-managed |

### 3.2 CMEK Setup

```hcl
# terraform/kms.tf

resource "google_kms_key_ring" "ocr_pipeline" {
  name     = "ocr-pipeline-keyring"
  location = "asia-northeast1"
}

resource "google_kms_crypto_key" "storage_key" {
  name            = "storage-encryption-key"
  key_ring        = google_kms_key_ring.ocr_pipeline.id
  purpose         = "ENCRYPT_DECRYPT"
  rotation_period = "7776000s"  # 90 days
  
  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "SOFTWARE"
  }
  
  lifecycle {
    prevent_destroy = true
  }
}

resource "google_kms_crypto_key" "bigquery_key" {
  name            = "bigquery-encryption-key"
  key_ring        = google_kms_key_ring.ocr_pipeline.id
  purpose         = "ENCRYPT_DECRYPT"
  rotation_period = "7776000s"
  
  lifecycle {
    prevent_destroy = true
  }
}

# Grant service accounts access to keys
resource "google_kms_crypto_key_iam_binding" "storage_encrypter" {
  crypto_key_id = google_kms_crypto_key.storage_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  
  members = [
    "serviceAccount:sa-storage-manager@${var.project_id}.iam.gserviceaccount.com",
    "serviceAccount:service-${var.project_number}@gs-project-accounts.iam.gserviceaccount.com",
  ]
}
```

### 3.3 Encrypted Bucket

```hcl
# terraform/storage.tf

resource "google_storage_bucket" "ocr_input" {
  name     = "ocr-input-${var.project_id}"
  location = "ASIA-NORTHEAST1"
  
  encryption {
    default_kms_key_name = google_kms_crypto_key.storage_key.id
  }
  
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = 30  # Delete after 30 days
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket" "ocr_output" {
  name     = "ocr-output-${var.project_id}"
  location = "ASIA-NORTHEAST1"
  
  encryption {
    default_kms_key_name = google_kms_crypto_key.storage_key.id
  }
  
  uniform_bucket_level_access = true
  
  versioning {
    enabled = true
  }
}
```

---

## 4. Identity-Aware Proxy (IAP)

### 4.1 Overview

IAP provides:
- Zero-trust access to Review UI
- Google Workspace SSO integration
- No custom authentication code needed
- Centralized access control

### 4.2 Setup

```hcl
# terraform/iap.tf

# Enable IAP for Cloud Run
resource "google_iap_web_iam_member" "review_ui_access" {
  project = var.project_id
  role    = "roles/iap.httpsResourceAccessor"
  
  # Allow specific Google Workspace group
  member = "group:ocr-reviewers@example.com"
}

# Backend service for Cloud Run
resource "google_compute_backend_service" "review_ui" {
  name                  = "review-ui-backend"
  protocol              = "HTTP"
  port_name             = "http"
  timeout_sec           = 30
  
  iap {
    enabled              = true
    oauth2_client_id     = var.oauth_client_id
    oauth2_client_secret = var.oauth_client_secret
  }
  
  backend {
    group = google_compute_region_network_endpoint_group.review_ui.id
  }
}
```

### 4.3 Cloud Run Configuration

```yaml
# review-ui/cloudbuild.yaml

steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/review-ui', '.']
  
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/review-ui']
  
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: 'gcloud'
    args:
      - 'run'
      - 'deploy'
      - 'review-ui'
      - '--image=gcr.io/$PROJECT_ID/review-ui'
      - '--region=asia-northeast1'
      - '--platform=managed'
      - '--no-allow-unauthenticated'  # Requires IAP
      - '--service-account=sa-review-ui@$PROJECT_ID.iam.gserviceaccount.com'
      - '--ingress=internal-and-cloud-load-balancing'
```

### 4.4 Getting User Identity in Application

```python
# api/auth.py
from fastapi import Request, HTTPException

def get_iap_user(request: Request) -> dict:
    """
    Extract user identity from IAP headers.
    
    IAP adds these headers after authentication:
    - X-Goog-Authenticated-User-Email
    - X-Goog-Authenticated-User-Id
    """
    email = request.headers.get("X-Goog-Authenticated-User-Email", "")
    user_id = request.headers.get("X-Goog-Authenticated-User-Id", "")
    
    if not email:
        raise HTTPException(401, "No IAP authentication found")
    
    # Email format: "accounts.google.com:user@example.com"
    if ":" in email:
        email = email.split(":", 1)[1]
    
    return {
        "email": email,
        "user_id": user_id
    }

# Usage in FastAPI
@app.post("/api/documents/{doc_hash}/approve")
async def approve_document(doc_hash: str, request: Request):
    user = get_iap_user(request)
    
    # Log who approved
    audit_log(
        action="DOCUMENT_APPROVED",
        resource=doc_hash,
        actor=user["email"]
    )
    
    # ... approval logic
```

---

## 5. Audit Logging

### 5.1 Automatic Audit Logs

Cloud Audit Logs capture automatically:
- Admin Activity (IAM changes, resource creation)
- Data Access (BigQuery queries, GCS access)
- System Events (Cloud Function invocations)

### 5.2 Custom Audit Events

```python
# core/audit.py
import json
from datetime import datetime
from google.cloud import logging as cloud_logging

audit_client = cloud_logging.Client()
audit_logger = audit_client.logger("ocr-audit-log")

def audit_log(
    action: str,
    resource: str,
    actor: str,
    details: dict = None,
    request: "Request" = None
):
    """
    Write custom audit event.
    
    Actions:
    - DOCUMENT_APPROVED
    - DOCUMENT_REJECTED
    - DOCUMENT_RESUBMITTED
    - DATA_CORRECTED
    - EXPORT_REQUESTED
    """
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "action": action,
        "resource": resource,
        "resource_type": "document",
        "actor": actor,
        "details": details or {},
    }
    
    if request:
        entry["client_ip"] = request.client.host
        entry["user_agent"] = request.headers.get("User-Agent", "")
    
    audit_logger.log_struct(
        entry,
        severity="INFO",
        labels={"audit_type": "custom"}
    )

# Usage
audit_log(
    action="DOCUMENT_APPROVED",
    resource="sha256:abc123",
    actor="user@example.com",
    details={
        "corrections": [
            {"field": "management_id", "old": "INV-001", "new": "INV-00001"}
        ],
        "quality_warnings_acknowledged": 2
    }
)
```

### 5.3 Audit Log Retention

```hcl
# terraform/logging.tf

# Lock audit logs (cannot be deleted)
resource "google_logging_project_bucket_config" "audit_bucket" {
  project        = var.project_id
  location       = "global"
  bucket_id      = "_Default"
  retention_days = 400  # Required for compliance
  
  locked = true  # Prevent accidental deletion
}

# Export to BigQuery for analysis
resource "google_logging_project_sink" "audit_to_bigquery" {
  name        = "audit-to-bigquery"
  destination = "bigquery.googleapis.com/projects/${var.project_id}/datasets/audit_logs"
  
  filter = <<EOF
    logName="projects/${var.project_id}/logs/ocr-audit-log"
    OR logName="projects/${var.project_id}/logs/cloudaudit.googleapis.com%2Factivity"
    OR logName="projects/${var.project_id}/logs/cloudaudit.googleapis.com%2Fdata_access"
  EOF
  
  unique_writer_identity = true
  
  bigquery_options {
    use_partitioned_tables = true
  }
}
```

---

## 6. Secret Management

### 6.1 Secret Manager Usage

All sensitive credentials stored in Secret Manager, not environment variables:

| Secret | Purpose | Accessor |
|--------|---------|----------|
| `slack-webhook-url` | Alert notifications | Alert Handler Function |
| `sendgrid-api-key` | Email notifications | Alert Handler Function |
| `oauth-client-secret` | IAP configuration | Cloud Run |

### 6.2 Terraform Configuration

```hcl
# terraform/secrets.tf

resource "google_secret_manager_secret" "slack_webhook" {
  secret_id = "slack-webhook-url"
  
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "slack_webhook_v1" {
  secret      = google_secret_manager_secret.slack_webhook.id
  secret_data = var.slack_webhook_url  # From tfvars (gitignored)
}

resource "google_secret_manager_secret" "sendgrid_api_key" {
  secret_id = "sendgrid-api-key"
  
  replication {
    auto {}
  }
}

# Grant access to Cloud Function service account
resource "google_secret_manager_secret_iam_member" "alert_handler_slack" {
  secret_id = google_secret_manager_secret.slack_webhook.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.alert_handler.email}"
}

resource "google_secret_manager_secret_iam_member" "alert_handler_sendgrid" {
  secret_id = google_secret_manager_secret.sendgrid_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.alert_handler.email}"
}
```

### 6.3 Cloud Function Configuration

```yaml
# functions/alert_handler/cloudfunctions.yaml

runtime: python311
entry_point: handle_dead_letter
service_account: sa-alert-handler@PROJECT.iam.gserviceaccount.com

# Reference secrets (mounted as environment variables)
secret_environment_variables:
  - key: SLACK_WEBHOOK_URL
    secret: slack-webhook-url
    version: latest
  - key: SENDGRID_API_KEY
    secret: sendgrid-api-key
    version: latest
```

### 6.4 Accessing Secrets in Code

```python
# Option 1: Environment variables (populated by Cloud Functions)
import os

SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK_URL"]
SENDGRID_KEY = os.environ["SENDGRID_API_KEY"]

# Option 2: Direct API access (for non-Cloud Function services)
from google.cloud import secretmanager

def get_secret(secret_id: str, version: str = "latest") -> str:
    """Retrieve secret from Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/{secret_id}/versions/{version}"
    
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")
```

### 6.5 Secret Rotation

```hcl
# Rotation policy (manual trigger recommended for webhooks)
resource "google_secret_manager_secret" "slack_webhook" {
  secret_id = "slack-webhook-url"
  
  # Optional: automatic rotation
  rotation {
    rotation_period    = "7776000s"  # 90 days
    next_rotation_time = "2025-04-01T00:00:00Z"
  }
  
  # Notification when rotation needed
  topics {
    name = google_pubsub_topic.secret_rotation.id
  }
}
```

---

## 7. Data Privacy

### 6.1 Vertex AI Enterprise

```python
# Gemini API calls use Vertex AI Enterprise
# Data is NOT used for model training

from vertexai.preview.generative_models import GenerativeModel

model = GenerativeModel(
    "gemini-1.5-pro",
    # Enterprise agreement ensures data privacy
)
```

### 6.2 Data Handling

| Data Type | Retention | Access | Notes |
|-----------|-----------|--------|-------|
| Original PDFs | 30 days (input) | Processor SA | Auto-deleted |
| Processed PDFs | Indefinite | Storage SA | Customer data |
| Extracted JSON | Indefinite | Database SA | Customer data |
| OCR Text | Not stored | Processor SA | Transient |
| Gemini Prompts | Not stored | - | Transient |

---

## 8. Security Checklist

### Pre-Deployment

- [ ] All service accounts created with minimum permissions
- [ ] CMEK keys created and rotated
- [ ] IAP configured for Review UI
- [ ] Audit logging enabled
- [ ] VPC Service Controls evaluated (future)

### Post-Deployment

- [ ] Verify no public access to buckets
- [ ] Test IAP authentication flow
- [ ] Confirm audit logs appearing
- [ ] Run security scanner on Cloud Run images
- [ ] Review IAM permissions quarterly

### Incident Response

- [ ] Document security contact
- [ ] Define breach notification process
- [ ] Test key rotation procedure
- [ ] Backup audit logs to cold storage
