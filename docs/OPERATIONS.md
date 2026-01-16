# Operations Manual

**Version**: 1.0.0
**Last Updated**: 2025-01-16

---

## Table of Contents

1. [Deployment](#deployment)
2. [Monitoring](#monitoring)
3. [Troubleshooting](#troubleshooting)
4. [Maintenance](#maintenance)
5. [Disaster Recovery](#disaster-recovery)

---

## Deployment

### Prerequisites

#### Required GCP APIs

```bash
gcloud services enable \
  documentai.googleapis.com \
  aiplatform.googleapis.com \
  cloudfunctions.googleapis.com \
  run.googleapis.com \
  storage.googleapis.com \
  firestore.googleapis.com \
  bigquery.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  cloudkms.googleapis.com \
  secretmanager.googleapis.com
```

#### Service Account Setup

```bash
# Create service account
gcloud iam service-accounts create ocr-processor \
  --display-name="OCR Processor Service Account"

# Grant required roles
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:ocr-processor@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/documentai.editor"

gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:ocr-processor@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:ocr-processor@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:ocr-processor@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:ocr-processor@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"
```

### Full Deployment Script

```bash
#!/bin/bash
set -e

# Configuration
export GCP_PROJECT_ID=${GCP_PROJECT_ID:-"your-project-id"}
export GCP_REGION=${GCP_REGION:-"asia-northeast1"}
export ENVIRONMENT=${ENVIRONMENT:-"production"}

echo "Deploying AI-OCR Smart Pipeline to $GCP_PROJECT_ID..."

# 1. Create GCS buckets
echo "Creating GCS buckets..."
gsutil mb -l $GCP_REGION gs://${GCP_PROJECT_ID}-input || true
gsutil mb -l $GCP_REGION gs://${GCP_PROJECT_ID}-output || true
gsutil mb -l $GCP_REGION gs://${GCP_PROJECT_ID}-quarantine || true

# 2. Create BigQuery dataset
echo "Creating BigQuery dataset..."
bq mk --dataset \
  --location=$GCP_REGION \
  --description="OCR Pipeline Data" \
  ${GCP_PROJECT_ID}:ocr_pipeline || true

# 3. Deploy Cloud Function
echo "Deploying Cloud Function..."
gcloud functions deploy ocr-processor \
  --gen2 \
  --runtime python311 \
  --region $GCP_REGION \
  --source src/functions/processor \
  --entry-point process_document \
  --memory 1024MB \
  --timeout 540s \
  --max-instances 10 \
  --min-instances 0 \
  --service-account ocr-processor@${GCP_PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars "GCP_PROJECT_ID=$GCP_PROJECT_ID,ENVIRONMENT=$ENVIRONMENT" \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=${GCP_PROJECT_ID}-input"

# 4. Deploy Review UI
echo "Deploying Review UI..."
gcloud run deploy review-ui \
  --source src/api \
  --region $GCP_REGION \
  --memory 512Mi \
  --min-instances 0 \
  --max-instances 3 \
  --service-account ocr-processor@${GCP_PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars "GCP_PROJECT_ID=$GCP_PROJECT_ID,ENVIRONMENT=$ENVIRONMENT" \
  --allow-unauthenticated

echo "Deployment complete!"
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GCP_PROJECT_ID` | GCP Project ID | Required |
| `GCP_REGION` | Deployment region | `asia-northeast1` |
| `ENVIRONMENT` | `development`, `staging`, `production` | `development` |
| `OUTPUT_BUCKET` | Bucket for processed files | `{project}-output` |
| `QUARANTINE_BUCKET` | Bucket for failed files | `{project}-quarantine` |
| `BIGQUERY_DATASET` | BigQuery dataset name | `ocr_pipeline` |
| `DOCUMENT_AI_PROCESSOR` | Document AI processor path | Required |
| `PRO_DAILY_LIMIT` | Daily Pro API call limit | `50` |
| `PRO_MONTHLY_LIMIT` | Monthly Pro API call limit | `1000` |

---

## Monitoring

### Key Metrics

| Metric | Description | Target | Alert Threshold |
|--------|-------------|--------|-----------------|
| Processing Success Rate | Documents successfully processed | >95% | <90% |
| Average Processing Time | End-to-end processing latency | <5 min | >10 min |
| Pro Escalation Rate | Percentage using Pro model | <20% | >30% |
| Queue Backlog | Pending documents | <10 | >100 |
| Failure Rate | Documents failing extraction | <5% | >10% |

### Cloud Monitoring Dashboard

Access the dashboard at: `https://console.cloud.google.com/monitoring/dashboards`

#### Custom Metrics

- `custom.googleapis.com/ocr/documents_processed` - Document processing count
- `custom.googleapis.com/ocr/processing_duration_ms` - Processing time
- `custom.googleapis.com/ocr/gemini_flash_calls` - Flash API usage
- `custom.googleapis.com/ocr/gemini_pro_calls` - Pro API usage
- `custom.googleapis.com/ocr/pro_budget_usage` - Daily Pro budget usage

### Log Queries

#### View Recent Errors

```
resource.type="cloud_function"
resource.labels.function_name="ocr-processor"
severity>=ERROR
timestamp>=timestamp.sub(now(), 1h)
```

#### View Processing Completions

```
resource.type="cloud_function"
resource.labels.function_name="ocr-processor"
jsonPayload.event_type="processing_completed"
```

#### View Pro Escalations

```
resource.type="cloud_function"
resource.labels.function_name="ocr-processor"
jsonPayload.event_type="gemini_pro_call"
```

#### View Quarantined Documents

```
resource.type="cloud_function"
resource.labels.function_name="ocr-processor"
jsonPayload.event_type="document_quarantined"
```

### Alert Policies

| Alert | Condition | Severity | Response Time |
|-------|-----------|----------|---------------|
| Queue Backlog Critical | pending_docs > 100 | P0 | Immediate |
| Pipeline Down | no processing in 15 min | P0 | Immediate |
| High Failure Rate | failure_rate > 5% | P1 | 1 hour |
| Pro Budget Warning | daily_usage > 80% | P2 | 4 hours |
| Latency Spike | p99_latency > 30s | P2 | 4 hours |

---

## Troubleshooting

### Common Issues

#### 1. Documents Not Processing

**Symptoms**: Documents uploaded but not appearing in output bucket

**Investigation**:
```bash
# Check Cloud Function logs
gcloud functions logs read ocr-processor --limit=50 --region=$GCP_REGION

# Check for stuck locks
gcloud firestore documents list \
  --collection=processing_locks \
  --project=$GCP_PROJECT_ID
```

**Resolution**:
1. Check if Cloud Function is triggered (look for `document_received` logs)
2. Check for lock acquisition failures
3. Verify GCS trigger is configured correctly
4. Check Document AI API quotas

#### 2. High Failure Rate

**Symptoms**: Many documents moving to quarantine

**Investigation**:
```bash
# View quarantine bucket contents
gsutil ls gs://${GCP_PROJECT_ID}-quarantine/quarantine/

# Read a failed report
gsutil cat gs://${GCP_PROJECT_ID}-quarantine/quarantine/{doc_hash}/FAILED_REPORT.md
```

**Resolution**:
1. Check Gate Linter errors in failed reports
2. Review document quality (scan quality, format)
3. Check if new document format requires schema update

#### 3. Pro Budget Exceeded

**Symptoms**: Documents not escalating to Pro despite failures

**Investigation**:
```bash
# Check current budget usage
gcloud firestore documents get \
  --collection=budget_tracking \
  --document=$(date +%Y-%m-%d) \
  --project=$GCP_PROJECT_ID
```

**Resolution**:
1. Wait for daily budget reset (midnight JST)
2. Increase `PRO_DAILY_LIMIT` if justified
3. Investigate root cause of high semantic errors

#### 4. Slow Processing

**Symptoms**: Processing time > 5 minutes

**Investigation**:
```bash
# Check processing duration distribution
bq query --use_legacy_sql=false "
SELECT
  APPROX_QUANTILES(processing_duration_ms, 100)[OFFSET(50)] AS p50,
  APPROX_QUANTILES(processing_duration_ms, 100)[OFFSET(95)] AS p95,
  APPROX_QUANTILES(processing_duration_ms, 100)[OFFSET(99)] AS p99
FROM \`${GCP_PROJECT_ID}.ocr_pipeline.extractions\`
WHERE DATE(processed_at) = CURRENT_DATE()
"
```

**Resolution**:
1. Check Document AI latency
2. Check Gemini API latency
3. Check Firestore/BigQuery write latency
4. Consider increasing Cloud Function memory/concurrency

### Log Analysis Commands

```bash
# Count errors by type
gcloud logging read "
  resource.type=cloud_function
  severity>=ERROR
  timestamp>=timestamp.sub(now(), 24h)
" --format="value(jsonPayload.error_type)" | sort | uniq -c | sort -rn

# Find slow processing documents
gcloud logging read "
  resource.type=cloud_function
  jsonPayload.event_type=processing_completed
  jsonPayload.duration_seconds>60
  timestamp>=timestamp.sub(now(), 24h)
" --format="value(jsonPayload.doc_hash,jsonPayload.duration_seconds)"
```

---

## Maintenance

### Regular Tasks

#### Daily
- [ ] Check monitoring dashboard for anomalies
- [ ] Review quarantine bucket for new failures
- [ ] Verify Pro budget usage is within limits

#### Weekly
- [ ] Review error trends in Cloud Logging
- [ ] Check document processing statistics
- [ ] Clear old entries from processing_locks collection

#### Monthly
- [ ] Review and archive quarantined documents
- [ ] Analyze correction patterns for prompt improvement
- [ ] Update quality linter rules based on feedback
- [ ] Review cost breakdown

### Clearing Stuck Locks

```bash
# Find locks older than 1 hour
gcloud firestore documents list \
  --collection=processing_locks \
  --filter="expires_at < '$(date -d '-1 hour' -Iseconds)'" \
  --project=$GCP_PROJECT_ID

# Delete specific stuck lock
gcloud firestore documents delete \
  --collection=processing_locks \
  --document={doc_hash} \
  --project=$GCP_PROJECT_ID
```

### Archiving Quarantined Documents

```bash
# Move to archive after review
gsutil mv gs://${GCP_PROJECT_ID}-quarantine/quarantine/{doc_hash}/ \
  gs://${GCP_PROJECT_ID}-quarantine/archived/$(date +%Y-%m)/

# Or delete if not needed
gsutil rm -r gs://${GCP_PROJECT_ID}-quarantine/quarantine/{doc_hash}/
```

### Updating Quality Linter Rules

Edit `config/quality_rules.yaml`:
```yaml
rules:
  - id: Q1
    field: confidence
    condition: ">= 0.7"
    message: "Low extraction confidence"
    severity: warning

  # Add new rules here
  - id: Q10
    field: company_name
    condition: "length >= 2"
    message: "Company name too short"
    severity: warning
```

No code deployment required - rules are loaded at runtime.

---

## Disaster Recovery

### Backup Strategy

| Data | Backup Method | Frequency | Retention |
|------|---------------|-----------|-----------|
| Firestore | Automated export | Daily | 30 days |
| BigQuery | Table snapshots | Weekly | 90 days |
| GCS (output) | Object versioning | Continuous | 30 days |
| Config files | Git repository | On change | Indefinite |

### Backup Commands

```bash
# Export Firestore
gcloud firestore export gs://${GCP_PROJECT_ID}-backups/firestore/$(date +%Y-%m-%d)

# Snapshot BigQuery dataset
bq cp ${GCP_PROJECT_ID}:ocr_pipeline.extractions \
  ${GCP_PROJECT_ID}:ocr_pipeline_backup.extractions_$(date +%Y%m%d)
```

### Restore Procedures

#### Restore Firestore

```bash
gcloud firestore import gs://${GCP_PROJECT_ID}-backups/firestore/{backup-date}
```

#### Restore BigQuery Table

```bash
bq cp ${GCP_PROJECT_ID}:ocr_pipeline_backup.extractions_{date} \
  ${GCP_PROJECT_ID}:ocr_pipeline.extractions
```

#### Reprocess Failed Documents

```bash
# Copy from quarantine back to input bucket
gsutil cp gs://${GCP_PROJECT_ID}-quarantine/quarantine/{doc_hash}/original_*.pdf \
  gs://${GCP_PROJECT_ID}-input/reprocess/

# This triggers the Cloud Function automatically
```

### RPO/RTO Targets

| Scenario | RPO | RTO |
|----------|-----|-----|
| Document loss | 0 (versioning) | 1 hour |
| Database corruption | 24 hours | 4 hours |
| Complete region failure | 24 hours | 8 hours |

### Incident Response Contacts

| Role | Contact | Escalation |
|------|---------|------------|
| On-call Engineer | Slack #ocr-oncall | PagerDuty |
| Team Lead | @team-lead | P0 incidents |
| Operations Manager | @ops-manager | Business impact |

---

## Appendix

### Useful Links

- [Cloud Console](https://console.cloud.google.com/home/dashboard?project=PROJECT_ID)
- [Cloud Functions](https://console.cloud.google.com/functions?project=PROJECT_ID)
- [Cloud Monitoring](https://console.cloud.google.com/monitoring?project=PROJECT_ID)
- [Cloud Logging](https://console.cloud.google.com/logs?project=PROJECT_ID)
- [Firestore](https://console.cloud.google.com/firestore?project=PROJECT_ID)
- [BigQuery](https://console.cloud.google.com/bigquery?project=PROJECT_ID)

### CLI Cheat Sheet

```bash
# View function logs
gcloud functions logs read ocr-processor --region=$GCP_REGION --limit=100

# List recent uploads
gsutil ls -l gs://${GCP_PROJECT_ID}-input/ | tail -20

# View processed documents
gsutil ls -r gs://${GCP_PROJECT_ID}-output/

# Check function status
gcloud functions describe ocr-processor --region=$GCP_REGION --format="value(state)"

# Force redeploy
gcloud functions deploy ocr-processor --region=$GCP_REGION --source src/functions/processor
```
