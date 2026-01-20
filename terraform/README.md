# AI-OCR Smart Pipeline - Terraform Infrastructure

This directory contains Terraform configurations for deploying the AI-OCR Smart Pipeline infrastructure on Google Cloud Platform.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Google Cloud Platform                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ Input Bucket │───▶│ Cloud Func.  │───▶│Output Bucket │       │
│  │  (GCS)       │    │ (Processor)  │    │  (GCS)       │       │
│  └──────────────┘    └──────┬───────┘    └──────────────┘       │
│                             │                                    │
│                             │ Failure                            │
│                             ▼                                    │
│                      ┌──────────────┐    ┌──────────────┐       │
│                      │ Quarantine   │    │ Dead Letter  │       │
│                      │ Bucket (GCS) │    │ (Pub/Sub)    │       │
│                      └──────────────┘    └──────┬───────┘       │
│                                                 │                │
│  ┌──────────────┐    ┌──────────────┐          │                │
│  │  Firestore   │    │   BigQuery   │◀─────────┘                │
│  │  (Documents) │    │ (Analytics)  │                           │
│  └──────────────┘    └──────────────┘                           │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐                           │
│  │  Cloud Run   │    │  Cloud Run   │                           │
│  │    (API)     │◀──▶│    (UI)      │                           │
│  └──────────────┘    └──────────────┘                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
terraform/
├── main.tf              # Root module configuration
├── variables.tf         # Input variables
├── outputs.tf           # Output values
├── modules/
│   ├── iam/             # Service accounts and permissions
│   ├── storage/         # GCS buckets and Pub/Sub
│   ├── firestore/       # Firestore database
│   ├── bigquery/        # BigQuery dataset and tables
│   ├── functions/       # Cloud Functions (2nd Gen)
│   ├── cloudrun/        # Cloud Run services
│   └── monitoring/      # Alerts and dashboards
└── environments/
    ├── staging/         # Staging environment config
    └── production/      # Production environment config
```

## Prerequisites

1. **Terraform** >= 1.5.0
2. **Google Cloud SDK** configured with appropriate permissions
3. **GCP Project** with billing enabled

### Required Permissions

The user or service account running Terraform needs:
- `roles/owner` (for initial setup) or specific roles:
  - `roles/iam.serviceAccountAdmin`
  - `roles/storage.admin`
  - `roles/bigquery.admin`
  - `roles/cloudfunctions.admin`
  - `roles/run.admin`
  - `roles/monitoring.admin`
  - `roles/secretmanager.admin`

## Quick Start

### 1. Configure Environment

```bash
cd terraform/environments/staging

# Copy example config
cp terraform.tfvars.example terraform.tfvars

# Edit with your values
vim terraform.tfvars
```

### 2. Initialize Terraform

```bash
terraform init
```

### 3. Plan Deployment

```bash
terraform plan -var-file=terraform.tfvars
```

### 4. Apply Changes

```bash
terraform apply -var-file=terraform.tfvars
```

## Environment Configuration

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `project_id` | GCP Project ID | `my-project-123` |
| `document_ai_processor_id` | Document AI processor | `projects/.../processors/...` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `region` | GCP Region | `asia-northeast1` |
| `api_image` | API Docker image | `""` (skip Cloud Run) |
| `ui_image` | UI Docker image | `""` (skip Cloud Run) |
| `alert_email` | Alert notification email | `""` |

## Modules

### IAM Module (`modules/iam/`)

Creates service accounts and grants minimal required permissions:
- **ocr-processor**: For Cloud Functions processing
- **ocr-api**: For Cloud Run API service

### Storage Module (`modules/storage/`)

Creates GCS buckets with lifecycle policies:
- **input**: Incoming documents (7-day retention)
- **output**: Processed documents (versioned, auto-tiering)
- **quarantine**: Failed documents (30-day retention)

Also creates Pub/Sub topics:
- **document-uploaded**: Triggers processing
- **dead-letter**: For failed processing

### Firestore Module (`modules/firestore/`)

Configures Firestore Native mode with indexes for:
- Document status queries
- Audit log queries
- Draft management

### BigQuery Module (`modules/bigquery/`)

Creates dataset and tables:
- **extraction_results**: Partitioned by document_date
- **corrections**: Append-only audit trail
- Analytics views for daily stats

### Functions Module (`modules/functions/`)

Deploys Cloud Functions (2nd Gen):
- **ocr-processor**: Document processing (1GB, 540s timeout)
- **ocr-health-check**: Health monitoring (256MB, 60s)
- **ocr-alert-handler**: Dead letter handling (256MB, 60s)

Also creates Cloud Scheduler for periodic health checks.

### Cloud Run Module (`modules/cloudrun/`)

Deploys services (optional, requires Docker images):
- **ocr-api**: FastAPI backend
- **ocr-ui**: React frontend

With optional IAP protection for custom domains.

### Monitoring Module (`modules/monitoring/`)

Creates:
- Alert policies (P0, P1, P2)
- Uptime checks
- Log-based metrics
- Notification channels

## Remote State (Recommended for Production)

Configure GCS backend for state storage:

```hcl
terraform {
  backend "gcs" {
    bucket = "your-project-terraform-state"
    prefix = "production"
  }
}
```

Create the state bucket:

```bash
gsutil mb -l asia-northeast1 gs://your-project-terraform-state
gsutil versioning set on gs://your-project-terraform-state
```

## Destroying Infrastructure

```bash
# Review what will be destroyed
terraform plan -destroy -var-file=terraform.tfvars

# Destroy (requires confirmation)
terraform destroy -var-file=terraform.tfvars
```

**Warning**: This will delete all resources including data in Firestore and BigQuery.

## Troubleshooting

### API Not Enabled

If you see "API not enabled" errors:
```bash
gcloud services enable [api-name].googleapis.com
```

Or wait for Terraform to enable them (it does this automatically).

### Permission Denied

Ensure your user/service account has the required IAM roles on the project.

### Firestore Already Exists

Firestore can only be created once per project. If it already exists in Datastore mode, you cannot switch to Native mode.

## Cost Estimation

Monthly costs for 100 documents/month:
- Cloud Functions: ~¥0 (free tier)
- Cloud Storage: ~¥2
- Firestore: ~¥2
- BigQuery: ~¥0 (free tier)
- Cloud Run: ~¥2
- **Total: ~¥170/month**

## Related Documentation

- [docs/OPERATIONS.md](../docs/OPERATIONS.md) - Operations guide
- [docs/specs/](../docs/specs/) - Detailed specifications
- [deploy/README.md](../deploy/README.md) - Deployment scripts
