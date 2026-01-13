# Monitoring & Alerting

**Spec ID**: 07  
**Status**: Final  
**Dependencies**: Cloud Monitoring, Cloud Logging

---

## 1. Metrics Dashboard

### 1.1 Key Performance Indicators

| Metric | Calculation | Target |
|--------|-------------|--------|
| Processing Success Rate | `completed / total` | >95% |
| Self-Correction Rate | `corrected / (corrected + failed)` | >80% |
| Pro Escalation Rate | `pro_calls / total` | <20% |
| Average Latency (p50) | Median processing time | <10s |
| Average Latency (p99) | 99th percentile | <60s |

### 1.2 Cloud Monitoring Query Examples

```sql
-- Success rate over time
SELECT
  TIMESTAMP_TRUNC(timestamp, HOUR) AS hour,
  COUNTIF(status = 'COMPLETED') / COUNT(*) AS success_rate
FROM `project.dataset.processing_logs`
WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY hour
ORDER BY hour;

-- Pro escalation trend
SELECT
  DATE(timestamp) AS date,
  COUNT(*) AS total_calls,
  COUNTIF(model = 'pro') AS pro_calls,
  COUNTIF(model = 'pro') / COUNT(*) AS pro_rate
FROM `project.dataset.gemini_calls`
WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY date
ORDER BY date;
```

---

## 2. Alert Configuration

### 2.1 Alert Definitions

```yaml
# config/alerts.yaml
version: "1.0"

alerts:
  # P0 - Critical (immediate response required)
  - name: "Queue Backlog Critical"
    id: "P0-001"
    condition: "pending_documents > 100"
    window: "5m"
    severity: "P0"
    channels:
      - slack: "#ocr-alerts"
      - pagerduty: "ocr-oncall"
    message: "Document processing queue has >100 pending items"
    runbook: "https://wiki.example.com/runbooks/ocr-backlog"
  
  - name: "Pipeline Down"
    id: "P0-002"
    condition: "processed_count == 0 AND incoming_count > 0"
    window: "15m"
    severity: "P0"
    channels:
      - slack: "#ocr-alerts"
      - pagerduty: "ocr-oncall"
    message: "No documents processed in 15 minutes despite incoming uploads"
  
  # P1 - High (respond within 1 hour)
  - name: "High Failure Rate"
    id: "P1-001"
    condition: "failure_rate > 0.05"
    window: "1h"
    severity: "P1"
    channels:
      - slack: "#ocr-alerts"
      - pagerduty: "ocr-oncall"
    message: "Document failure rate exceeds 5% in the last hour"
  
  - name: "Saga Compensation Spike"
    id: "P1-002"
    condition: "compensation_count > 5"
    window: "1h"
    severity: "P1"
    channels:
      - slack: "#ocr-alerts"
    message: "Multiple saga rollbacks detected - potential data integrity issue"
  
  # P2 - Medium (respond within 4 hours)
  - name: "Pro Budget Warning"
    id: "P2-001"
    condition: "daily_pro_calls / daily_limit > 0.8"
    window: "1d"
    severity: "P2"
    channels:
      - slack: "#ocr-alerts"
    message: "Pro API usage at 80% of daily budget"
  
  - name: "Processing Latency Spike"
    id: "P2-002"
    condition: "p99_latency > 30s"
    window: "15m"
    severity: "P2"
    channels:
      - slack: "#ocr-alerts"
    message: "99th percentile latency exceeds 30 seconds"
  
  - name: "Low Confidence Trend"
    id: "P2-003"
    condition: "low_confidence_rate > 0.3"
    window: "1d"
    severity: "P2"
    channels:
      - slack: "#ocr-alerts"
    message: "30%+ documents have low OCR confidence - check scan quality"
```

### 2.2 Alert Channels

| Channel | Use Case | Setup |
|---------|----------|-------|
| Slack | All alerts | Webhook to #ocr-alerts |
| PagerDuty | P0, P1 only | Integration key |
| Email | Daily summary | Distribution list |

---

## 3. Structured Logging

### 3.1 Log Schema

```python
# core/logging.py
import structlog
import os
from datetime import datetime
from typing import Any, Dict, Optional

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()

def log_processing_event(
    event_type: str,
    doc_hash: str,
    **kwargs: Any
) -> None:
    """
    Emit structured log event for Cloud Logging.
    
    Standard fields:
    - event_type: Classification of the event
    - doc_hash: Document identifier for correlation
    - execution_id: Cloud Function execution ID
    - timestamp: ISO format
    """
    logger.info(
        event_type,
        doc_hash=doc_hash,
        execution_id=os.environ.get("FUNCTION_EXECUTION_ID", "local"),
        function_name=os.environ.get("FUNCTION_NAME", "unknown"),
        **kwargs
    )
```

### 3.2 Event Types

| Event Type | When Logged | Key Fields |
|------------|-------------|------------|
| `document_received` | Upload detected | `source_path`, `file_size` |
| `lock_acquired` | Lock obtained | `ttl_seconds` |
| `lock_skipped_duplicate` | Already processing | - |
| `ocr_completed` | Doc AI finished | `confidence`, `page_count` |
| `gemini_flash_attempt` | Flash API call | `attempt`, `input_tokens` |
| `gemini_flash_success` | Flash succeeded | `output_tokens`, `duration_ms` |
| `gemini_pro_escalation` | Escalating to Pro | `reason`, `previous_errors` |
| `gate_linter_passed` | Gate validation OK | `checks` |
| `gate_linter_failed` | Gate validation failed | `errors` |
| `quality_warnings` | Quality issues found | `warnings` |
| `saga_started` | Persistence begins | `steps` |
| `saga_step_completed` | Step succeeded | `step_name` |
| `saga_compensating` | Rollback started | `steps_to_rollback` |
| `saga_completed` | Persistence done | `status`, `duration_ms` |
| `processing_completed` | Full pipeline done | `total_duration_ms`, `model_used` |
| `processing_failed` | Pipeline failed | `error`, `attempts` |

### 3.3 Log Examples

```python
# Document received
log_processing_event(
    "document_received",
    doc_hash="sha256:abc123",
    source_path="gs://bucket/input/invoice.pdf",
    file_size=245678
)

# OCR completed
log_processing_event(
    "ocr_completed",
    doc_hash="sha256:abc123",
    confidence=0.92,
    page_count=2,
    duration_ms=1234
)

# Gemini attempt
log_processing_event(
    "gemini_flash_attempt",
    doc_hash="sha256:abc123",
    attempt=1,
    input_tokens=2048,
    include_image=False
)

# Gate linter failed
log_processing_event(
    "gate_linter_failed",
    doc_hash="sha256:abc123",
    errors=[
        "management_id: Invalid format 'INV'",
        "issue_date: Future date not allowed"
    ],
    attempt=1
)

# Processing completed
log_processing_event(
    "processing_completed",
    doc_hash="sha256:abc123",
    status="COMPLETED",
    total_duration_ms=4567,
    model_used="flash",
    attempts=1,
    output_path="gs://bucket/output/INV-2025-001_山田商事_2025-01-09.pdf"
)
```

---

## 4. Log Retention

| Log Type | Retention | Storage | Purpose |
|----------|-----------|---------|---------|
| Application Logs | 90 days | Cloud Logging | Debugging |
| Audit Logs | 400 days | Cloud Logging (locked) | Compliance |
| Metrics | 6 weeks | Cloud Monitoring | Dashboards |
| Extracted Data | Indefinite | BigQuery | Analytics |
| FAILED Reports | 1 year | Cloud Storage | Review |

---

## 5. Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  OCR Pipeline Dashboard                              [Refresh]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐│
│  │  Today     │  │  Success   │  │  Pro Used  │  │  Pending   ││
│  │    47      │  │   94.2%    │  │   12/50    │  │     3      ││
│  │ processed  │  │  (24h)     │  │  (daily)   │  │  review    ││
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘│
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Processing Volume (Last 7 Days)                          │  │
│  │  ████████████████████████████████████████████████████    │  │
│  │  Mon   Tue   Wed   Thu   Fri   Sat   Sun                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────┐  ┌─────────────────────────────┐ │
│  │  Model Usage             │  │  Failure Breakdown          │ │
│  │                          │  │                             │ │
│  │  Flash: ████████ 85%     │  │  Gate: ████ 40%            │ │
│  │  Pro:   ██ 15%           │  │  Semantic: ██████ 60%      │ │
│  │                          │  │                             │ │
│  └──────────────────────────┘  └─────────────────────────────┘ │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Latency Distribution (p50 / p95 / p99)                   │  │
│  │  ████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░     │  │
│  │  2.1s      /      5.4s      /      12.3s                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Cloud Monitoring Setup

### 6.1 Custom Metrics

```python
from google.cloud import monitoring_v3
from google.api import metric_pb2

def create_custom_metrics(project_id: str):
    """Create custom metrics for OCR pipeline."""
    client = monitoring_v3.MetricServiceClient()
    project_name = f"projects/{project_id}"
    
    metrics = [
        {
            "type": "custom.googleapis.com/ocr/documents_processed",
            "labels": ["status", "document_type"],
            "description": "Number of documents processed"
        },
        {
            "type": "custom.googleapis.com/ocr/processing_duration",
            "labels": ["model", "document_type"],
            "description": "Processing duration in milliseconds"
        },
        {
            "type": "custom.googleapis.com/ocr/pro_budget_usage",
            "labels": [],
            "description": "Daily Pro API budget usage"
        }
    ]
    
    for metric in metrics:
        descriptor = metric_pb2.MetricDescriptor(
            type=metric["type"],
            metric_kind=metric_pb2.MetricDescriptor.MetricKind.GAUGE,
            value_type=metric_pb2.MetricDescriptor.ValueType.INT64,
            description=metric["description"]
        )
        client.create_metric_descriptor(
            name=project_name,
            metric_descriptor=descriptor
        )
```

### 6.2 Recording Metrics

```python
from google.cloud import monitoring_v3
import time

def record_metric(
    project_id: str,
    metric_type: str,
    value: int,
    labels: dict = None
):
    """Record a custom metric value."""
    client = monitoring_v3.MetricServiceClient()
    project_name = f"projects/{project_id}"
    
    series = monitoring_v3.TimeSeries()
    series.metric.type = metric_type
    
    if labels:
        for key, val in labels.items():
            series.metric.labels[key] = val
    
    series.resource.type = "global"
    
    now = time.time()
    point = monitoring_v3.Point()
    point.value.int64_value = value
    point.interval.end_time.seconds = int(now)
    
    series.points.append(point)
    
    client.create_time_series(
        name=project_name,
        time_series=[series]
    )

# Usage
record_metric(
    "my-project",
    "custom.googleapis.com/ocr/documents_processed",
    1,
    {"status": "completed", "document_type": "delivery_note"}
)
```

---

## 7. Alert Response Runbooks

### 7.1 P0-001: Queue Backlog Critical

**Symptoms**: >100 documents waiting, processing not keeping up

**Immediate Actions**:
1. Check Cloud Function logs for errors
2. Verify Gemini API status: https://status.cloud.google.com
3. Check Firestore lock table for stuck locks
4. Scale up if needed (increase concurrency)

**Investigation**:
```bash
# Check recent errors
gcloud logging read "resource.type=cloud_function \
  resource.labels.function_name=ocr-processor \
  severity>=ERROR" --limit=50

# Check stuck locks
gcloud firestore documents list \
  --collection=processed_documents \
  --filter="status=PENDING AND lock_expires_at < NOW()"
```

### 7.2 P1-001: High Failure Rate

**Symptoms**: >5% documents failing extraction

**Investigation**:
1. Check failure breakdown (Gate vs Semantic)
2. Sample failed documents for patterns
3. Check if specific document type is failing
4. Review recent code/config changes

**Common Causes**:
- New document format not in registry
- OCR quality degradation
- Gemini prompt regression
