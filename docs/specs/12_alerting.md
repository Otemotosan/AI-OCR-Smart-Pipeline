# Failure Alerting & Health Monitoring

**Spec ID**: 12  
**Status**: Final  
**Dependencies**: Pub/Sub, Cloud Scheduler, Slack/SendGrid

---

## 1. Problem Statement

Silent failures are dangerous:
- Cloud Function crashes without notification
- Documents stuck in PENDING indefinitely
- Rate limits causing backlog growth
- Users unaware system is down

**Result**: Lost trust, manual discovery of issues, delayed response.

---

## 2. Design

### 2.1 Alert Channels

| Channel | Use Case | Response Time |
|---------|----------|---------------|
| Slack | All alerts | Immediate visibility |
| Email | Summary + critical | Async notification |
| PagerDuty | P0/P1 only | On-call escalation |

### 2.2 Alert Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    ALERTING ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Cloud Function                                              │
│       │                                                      │
│       │ Retry exhausted                                      │
│       ▼                                                      │
│  ┌─────────────────┐                                        │
│  │ Dead Letter     │                                        │
│  │ Topic (Pub/Sub) │                                        │
│  └────────┬────────┘                                        │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────┐     ┌─────────────────┐                │
│  │ Alert Handler   │────▶│ Slack           │                │
│  │ (Cloud Function)│     │ #ocr-alerts     │                │
│  └────────┬────────┘     └─────────────────┘                │
│           │                                                  │
│           │              ┌─────────────────┐                │
│           └─────────────▶│ SendGrid        │                │
│                          │ (email)         │                │
│                          └─────────────────┘                │
│                                                              │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  Cloud Scheduler (every 15 min)                              │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────┐                                        │
│  │ Health Check    │                                        │
│  │ Function        │                                        │
│  └────────┬────────┘                                        │
│           │                                                  │
│    ┌──────┴──────┐                                          │
│    │             │                                           │
│  Healthy      Unhealthy                                      │
│    │             │                                           │
│    ▼             ▼                                           │
│  (no-op)     Alert!                                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Dead Letter Queue

### 3.1 Pub/Sub Setup

```yaml
# terraform/pubsub.tf
resource "google_pubsub_topic" "dead_letter" {
  name = "ocr-dead-letter"
}

resource "google_pubsub_subscription" "dead_letter_sub" {
  name  = "ocr-dead-letter-sub"
  topic = google_pubsub_topic.dead_letter.name
  
  push_config {
    push_endpoint = google_cloudfunctions2_function.alert_handler.url
  }
  
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}
```

### 3.2 Cloud Function Configuration

```yaml
# cloudfunctions.yaml
- name: ocr-processor
  runtime: python311
  trigger:
    eventType: google.cloud.storage.object.v1.finalized
    resource: projects/PROJECT/buckets/ocr-input
  
  retryPolicy:
    maxRetries: 3
  
  # Dead letter configuration
  deadLetterPolicy:
    deadLetterTopic: projects/PROJECT/topics/ocr-dead-letter
```

### 3.3 Alert Handler Function

```python
# functions/alert_handler/main.py
import functions_framework
from google.cloud import firestore
import requests
import os
from datetime import datetime

SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK_URL"]
SENDGRID_API_KEY = os.environ["SENDGRID_API_KEY"]
ALERT_EMAIL = os.environ["ALERT_EMAIL"]

@functions_framework.cloud_event
def handle_dead_letter(event):
    """
    Process dead letter messages — documents that failed all retries.
    """
    # Parse failed document info
    message = event.data.get("message", {})
    attributes = message.get("attributes", {})
    
    doc_info = {
        "bucket": attributes.get("bucket"),
        "name": attributes.get("objectId"),
        "error": attributes.get("errorMessage", "Unknown error"),
        "retry_count": attributes.get("retryCount", "unknown"),
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    # Calculate doc_hash if possible
    doc_hash = attributes.get("docHash", "unknown")
    
    # Update Firestore status
    if doc_hash != "unknown":
        db = firestore.Client()
        db.collection("processed_documents").document(doc_hash).update({
            "status": "FAILED",
            "error_message": doc_info["error"],
            "failed_at": datetime.utcnow(),
        })
    
    # Send Slack alert
    send_slack_alert(doc_info, doc_hash)
    
    # Send email alert
    send_email_alert(doc_info, doc_hash)
    
    return "OK"


def send_slack_alert(doc_info: dict, doc_hash: str):
    """Send alert to Slack channel."""
    review_url = f"https://review.example.com/document/{doc_hash}"
    
    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 Document Processing Failed",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*File:*\n{doc_info['name']}"},
                    {"type": "mrkdwn", "text": f"*Retries:*\n{doc_info['retry_count']}"},
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error:*\n```{doc_info['error'][:500]}```"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Open Review UI"},
                        "url": review_url,
                        "style": "primary"
                    }
                ]
            }
        ]
    }
    
    requests.post(SLACK_WEBHOOK, json=payload)


def send_email_alert(doc_info: dict, doc_hash: str):
    """Send email via SendGrid."""
    import sendgrid
    from sendgrid.helpers.mail import Mail
    
    review_url = f"https://review.example.com/document/{doc_hash}"
    
    message = Mail(
        from_email="ocr-alerts@example.com",
        to_emails=ALERT_EMAIL,
        subject=f"[OCR Pipeline] Processing Failed: {doc_info['name']}",
        html_content=f"""
        <h2>Document Processing Failed</h2>
        <p><strong>File:</strong> {doc_info['name']}</p>
        <p><strong>Error:</strong> {doc_info['error']}</p>
        <p><strong>Retries:</strong> {doc_info['retry_count']}</p>
        <p><a href="{review_url}">Open in Review UI</a></p>
        """
    )
    
    sg = sendgrid.SendGridAPIClient(SENDGRID_API_KEY)
    sg.send(message)
```

---

## 4. Health Check

### 4.1 Cloud Scheduler Job

```yaml
# terraform/scheduler.tf
resource "google_cloud_scheduler_job" "health_check" {
  name        = "ocr-health-check"
  description = "Check pipeline health every 15 minutes"
  schedule    = "*/15 * * * *"
  time_zone   = "Asia/Tokyo"
  
  http_target {
    uri         = google_cloudfunctions2_function.health_check.url
    http_method = "POST"
    
    oidc_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}
```

### 4.2 Health Check Function

```python
# functions/health_check/main.py
import functions_framework
from google.cloud import firestore
from datetime import datetime, timedelta
import requests
import os

SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK_URL"]
ALERT_THRESHOLDS = {
    "stuck_pending_minutes": 30,
    "max_pending_count": 50,
    "max_failure_rate": 0.10,  # 10%
    "min_processed_when_incoming": 1,
}

@functions_framework.http
def health_check(request):
    """
    Periodic health check for pipeline.
    
    Checks:
    1. Stuck documents (PENDING > 30 min)
    2. Backlog growth
    3. Failure rate
    4. Zero processing with incoming documents
    """
    db = firestore.Client()
    issues = []
    
    # Check 1: Stuck PENDING documents
    stuck_threshold = datetime.utcnow() - timedelta(
        minutes=ALERT_THRESHOLDS["stuck_pending_minutes"]
    )
    
    stuck_docs = (
        db.collection("processed_documents")
        .where("status", "==", "PENDING")
        .where("created_at", "<", stuck_threshold)
        .get()
    )
    
    if len(stuck_docs) > 0:
        issues.append({
            "type": "stuck_pending",
            "severity": "P1",
            "message": f"{len(stuck_docs)} documents stuck in PENDING for >30 min",
            "doc_hashes": [doc.id for doc in stuck_docs[:5]],
        })
    
    # Check 2: Backlog size
    pending_count = len(
        db.collection("processed_documents")
        .where("status", "==", "PENDING")
        .get()
    )
    
    if pending_count > ALERT_THRESHOLDS["max_pending_count"]:
        issues.append({
            "type": "backlog_high",
            "severity": "P0",
            "message": f"Backlog critical: {pending_count} documents pending",
        })
    
    # Check 3: Failure rate (last hour)
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    
    recent_docs = (
        db.collection("processed_documents")
        .where("updated_at", ">", one_hour_ago)
        .get()
    )
    
    if len(recent_docs) > 10:  # Only check if enough samples
        failed_count = sum(1 for doc in recent_docs if doc.to_dict().get("status") == "FAILED")
        failure_rate = failed_count / len(recent_docs)
        
        if failure_rate > ALERT_THRESHOLDS["max_failure_rate"]:
            issues.append({
                "type": "high_failure_rate",
                "severity": "P1",
                "message": f"Failure rate {failure_rate:.1%} exceeds threshold",
            })
    
    # Check 4: Zero processing with incoming documents
    incoming_count = count_incoming_last_hour()
    processed_count = sum(
        1 for doc in recent_docs 
        if doc.to_dict().get("status") == "COMPLETED"
    )
    
    if incoming_count > 0 and processed_count == 0:
        issues.append({
            "type": "pipeline_stalled",
            "severity": "P0",
            "message": f"Pipeline stalled: {incoming_count} incoming, 0 processed in last hour",
        })
    
    # Send alerts if issues found
    if issues:
        send_health_alert(issues)
        return {"status": "unhealthy", "issues": issues}, 500
    
    return {"status": "healthy"}, 200


def send_health_alert(issues: list):
    """Send health check failure alert to Slack."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "⚠️ Pipeline Health Check Failed",
                "emoji": True
            }
        }
    ]
    
    for issue in issues:
        severity_emoji = "🚨" if issue["severity"] == "P0" else "⚠️"
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{severity_emoji} *[{issue['severity']}] {issue['type']}*\n{issue['message']}"
            }
        })
    
    requests.post(SLACK_WEBHOOK, json={"blocks": blocks})


def count_incoming_last_hour() -> int:
    """Count files uploaded to input bucket in last hour."""
    from google.cloud import storage
    
    client = storage.Client()
    bucket = client.bucket("ocr-input")
    
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    
    count = 0
    for blob in bucket.list_blobs():
        if blob.time_created > one_hour_ago:
            count += 1
    
    return count
```

---

## 5. User-Facing Notifications

### 5.1 Processing Complete Email

```python
# core/notifications.py
def send_processing_complete(doc_hash: str, status: str, user_email: str):
    """
    Notify user when their document is processed.
    
    Called after Saga completion or failure.
    """
    review_url = f"https://review.example.com/document/{doc_hash}"
    
    if status == "COMPLETED":
        subject = "✅ Document processed successfully"
        body = f"""
        Your document has been processed successfully.
        
        View details: {review_url}
        """
    else:
        subject = "⚠️ Document requires review"
        body = f"""
        Your document could not be processed automatically and requires manual review.
        
        Please review and correct: {review_url}
        """
    
    send_email(to=user_email, subject=subject, body=body)
```

### 5.2 Batch Summary (Daily Digest)

```python
# functions/daily_digest/main.py
@functions_framework.http
def send_daily_digest(request):
    """
    Daily summary email to admin.
    Triggered by Cloud Scheduler at 9 AM.
    """
    db = firestore.Client()
    yesterday = datetime.utcnow() - timedelta(days=1)
    
    # Gather stats
    docs = db.collection("processed_documents").where("created_at", ">", yesterday).get()
    
    total = len(docs)
    completed = sum(1 for d in docs if d.to_dict()["status"] == "COMPLETED")
    failed = sum(1 for d in docs if d.to_dict()["status"] == "FAILED")
    pending = sum(1 for d in docs if d.to_dict()["status"] == "PENDING")
    
    success_rate = (completed / total * 100) if total > 0 else 0
    
    # Get Pro usage
    pro_usage = get_pro_usage()
    
    # Build email
    send_email(
        to=ADMIN_EMAIL,
        subject=f"[OCR Pipeline] Daily Summary - {success_rate:.1f}% success",
        body=f"""
        Daily Summary for {yesterday.date()}
        
        Documents Processed: {total}
        - Completed: {completed}
        - Failed: {failed}
        - Pending: {pending}
        
        Success Rate: {success_rate:.1f}%
        
        Pro API Usage:
        - Today: {pro_usage['daily']}/{PRO_DAILY_LIMIT}
        - This Month: {pro_usage['monthly']}/{PRO_MONTHLY_LIMIT}
        
        Review pending documents: https://review.example.com/failed
        """
    )
    
    return "OK"
```

---

## 6. Alert Severity Matrix

| Severity | Condition | Notification | Response Time |
|----------|-----------|--------------|---------------|
| P0 | Backlog >100 OR Pipeline stalled | Slack + PagerDuty | Immediate |
| P1 | Failure rate >10% OR Stuck docs | Slack + Email | 1 hour |
| P2 | Pro budget >80% | Slack | 4 hours |
| P3 | Daily failure count >10 | Email digest | Next day |

---

## 7. Slack Channel Structure

| Channel | Purpose | Alerts |
|---------|---------|--------|
| `#ocr-alerts` | Real-time alerts | P0, P1, P2 |
| `#ocr-daily` | Daily digest | Summary |
| `#ocr-debug` | Detailed logs | Debug info (optional) |
