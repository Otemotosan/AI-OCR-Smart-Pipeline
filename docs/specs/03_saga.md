# Saga Pattern for Atomic Operations

**Spec ID**: 03  
**Status**: Final  
**Dependencies**: Firestore, Cloud Storage

---

## 1. Problem Statement

Multi-step persistence is not atomic:
1. Rename file in GCS
2. Insert record in BigQuery
3. Delete source file

If step 2 fails, we have:
- Renamed file in destination (orphan)
- No database record
- Source file deleted

**Solution**: Saga pattern with compensation transactions.

---

## 2. Design Philosophy

**Database is Single Source of Truth (SSOT)**

- DB state determines what happened
- File operations are compensatable
- If DB says FAILED, rollback file operations

---

## 3. Saga Steps

| Step | Operation | Compensation |
|------|-----------|--------------|
| 1 | DB: Insert with `status=PENDING` | DB: Update `status=FAILED` |
| 2 | GCS: Copy file to destination | GCS: Delete destination file |
| 3 | GCS: Delete source file | GCS: Copy back from destination |
| 4 | DB: Update `status=COMPLETED` | N/A (final step) |

---

## 4. Implementation

### 4.1 Saga Orchestrator

```python
from dataclasses import dataclass, field
from typing import Callable, List, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class SagaStep:
    """A single step in the saga with its compensation."""
    name: str
    execute: Callable[[], None]
    compensate: Callable[[], None]

class SagaFailedError(Exception):
    """Raised when saga execution fails."""
    def __init__(self, step_name: str, original_error: Exception):
        self.step_name = step_name
        self.original_error = original_error
        super().__init__(f"Saga failed at step '{step_name}': {original_error}")

class SagaOrchestrator:
    """
    Executes saga steps in order.
    On failure, compensates in reverse order.
    """
    
    def __init__(self):
        self.executed_steps: List[SagaStep] = []
    
    def execute(self, steps: List[SagaStep]) -> bool:
        """
        Execute all saga steps.
        
        Args:
            steps: Ordered list of saga steps
            
        Returns:
            True if all steps succeeded
            
        Raises:
            SagaFailedError: If any step fails (after compensation)
        """
        self.executed_steps = []
        
        for step in steps:
            try:
                logger.info(f"Saga executing: {step.name}")
                step.execute()
                self.executed_steps.append(step)
                logger.info(f"Saga completed: {step.name}")
                
            except Exception as e:
                logger.error(f"Saga failed at {step.name}: {e}")
                self._rollback()
                raise SagaFailedError(step.name, e)
        
        return True
    
    def _rollback(self) -> None:
        """Execute compensations in reverse order."""
        logger.warning(f"Saga rollback: {len(self.executed_steps)} steps to compensate")
        
        for step in reversed(self.executed_steps):
            try:
                logger.info(f"Saga compensating: {step.name}")
                step.compensate()
                logger.info(f"Saga compensated: {step.name}")
                
            except Exception as e:
                # Log but continue — best effort compensation
                logger.error(f"Compensation failed for '{step.name}': {e}")
                # Consider alerting here for manual intervention
```

### 4.2 GCS Operations

```python
from google.cloud import storage
from typing import Optional

def _copy_blob(
    client: storage.Client,
    source_path: str,
    dest_path: str
) -> None:
    """
    Copy a blob from source to destination.
    
    Args:
        source_path: gs://bucket/path/to/source
        dest_path: gs://bucket/path/to/dest
    """
    source_bucket, source_name = _parse_gcs_path(source_path)
    dest_bucket, dest_name = _parse_gcs_path(dest_path)
    
    source_blob = client.bucket(source_bucket).blob(source_name)
    dest_blob = client.bucket(dest_bucket).blob(dest_name)
    
    # Use rewrite for large files (auto-handles >5GB)
    rewrite_token = None
    while True:
        rewrite_token, bytes_rewritten, total_bytes = dest_blob.rewrite(
            source_blob, token=rewrite_token
        )
        if rewrite_token is None:
            break


def _delete_blob(
    client: storage.Client,
    path: str,
    ignore_not_found: bool = True
) -> None:
    """
    Delete a blob.
    
    Args:
        path: gs://bucket/path/to/blob
        ignore_not_found: If True, don't raise on missing blob
    """
    bucket_name, blob_name = _parse_gcs_path(path)
    blob = client.bucket(bucket_name).blob(blob_name)
    
    try:
        blob.delete()
    except Exception as e:
        if "Not Found" in str(e) and ignore_not_found:
            return
        raise


def _parse_gcs_path(path: str) -> tuple[str, str]:
    """Parse gs://bucket/path into (bucket, path)."""
    if not path.startswith("gs://"):
        raise ValueError(f"Invalid GCS path: {path}")
    
    parts = path[5:].split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid GCS path: {path}")
    
    return parts[0], parts[1]
```

### 4.3 Persistence Function

```python
from google.cloud import firestore, storage

def persist_document(
    doc_hash: str,
    validated_json: dict,
    source_path: str,
    dest_path: str,
    schema_version: str
) -> bool:
    """
    Atomically persist document using Saga pattern.
    
    Args:
        doc_hash: SHA-256 hash of document
        validated_json: Validated extraction result
        source_path: gs://bucket/input/original.pdf
        dest_path: gs://bucket/output/ID_Company_Date.pdf
        schema_version: e.g., "delivery_note/v2"
    
    Returns:
        True if successful
        
    Raises:
        SagaFailedError: If persistence fails
    """
    db = firestore.Client()
    storage_client = storage.Client()
    
    doc_ref = db.collection("processed_documents").document(doc_hash)
    
    # Define saga steps
    steps = [
        SagaStep(
            name="db_pending",
            execute=lambda: doc_ref.update({
                "status": "PENDING",
                "validated_json": validated_json,
                "schema_version": schema_version,
                "gcs_output_path": dest_path,
                "updated_at": firestore.SERVER_TIMESTAMP
            }),
            compensate=lambda: doc_ref.update({
                "status": "FAILED",
                "error_message": "Saga rollback at db_pending",
                "updated_at": firestore.SERVER_TIMESTAMP
            })
        ),
        
        SagaStep(
            name="gcs_copy",
            execute=lambda: _copy_blob(storage_client, source_path, dest_path),
            compensate=lambda: _delete_blob(storage_client, dest_path)
        ),
        
        SagaStep(
            name="gcs_delete_source",
            execute=lambda: _delete_blob(storage_client, source_path),
            compensate=lambda: _copy_blob(storage_client, dest_path, source_path)
        ),
        
        SagaStep(
            name="db_complete",
            execute=lambda: doc_ref.update({
                "status": "COMPLETED",
                "completed_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            }),
            compensate=lambda: None  # Final step — no compensation
        ),
    ]
    
    saga = SagaOrchestrator()
    return saga.execute(steps)
```

---

## 5. State Transitions

```
┌─────────────────────────────────────────────────────────────┐
│                    SAGA STATE MACHINE                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────┐                                                │
│  │  START  │                                                │
│  └────┬────┘                                                │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────────────────────────────┐                │
│  │  Step 1: DB PENDING                     │                │
│  │  state = PENDING                        │                │
│  └────────────────┬────────────────────────┘                │
│                   │                                          │
│          ┌────────┴────────┐                                │
│          │                 │                                │
│       success            fail                               │
│          │                 │                                │
│          ▼                 ▼                                │
│  ┌───────────────┐  ┌───────────────┐                       │
│  │ Step 2: COPY  │  │ Compensate:   │                       │
│  │ dest created  │  │ state=FAILED  │                       │
│  └───────┬───────┘  └───────────────┘                       │
│          │                                                   │
│     ┌────┴────┐                                             │
│     │         │                                             │
│  success    fail                                            │
│     │         │                                             │
│     ▼         ▼                                             │
│  ┌─────────┐ ┌───────────────────────┐                      │
│  │ Step 3: │ │ Compensate:           │                      │
│  │ DELETE  │ │ 1. delete dest        │                      │
│  │ source  │ │ 2. state=FAILED       │                      │
│  └────┬────┘ └───────────────────────┘                      │
│       │                                                      │
│   ┌───┴───┐                                                 │
│   │       │                                                 │
│ success  fail                                               │
│   │       │                                                 │
│   ▼       ▼                                                 │
│ ┌─────┐ ┌─────────────────────────────┐                     │
│ │Step4│ │ Compensate:                 │                     │
│ │DONE │ │ 1. copy dest→source         │                     │
│ └──┬──┘ │ 2. delete dest              │                     │
│    │    │ 3. state=FAILED             │                     │
│    ▼    └─────────────────────────────┘                     │
│ ┌───────────┐                                               │
│ │ COMPLETED │                                               │
│ └───────────┘                                               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Failure Handling

### 6.1 FAILED Report Generation

When saga fails, generate human-readable report:

```python
def generate_failed_report(
    doc_hash: str,
    source_path: str,
    attempts: List[dict],
    errors: List[str],
    saga_error: Optional[SagaFailedError] = None
) -> str:
    """Generate FAILED_REPORT.md content."""
    
    report = f"""# Processing Failed Report

## Document Information
- **Hash**: {doc_hash}
- **Source**: {source_path}
- **Failed At**: {datetime.utcnow().isoformat()}Z

## Extraction Attempts
"""
    
    for i, attempt in enumerate(attempts, 1):
        report += f"""
### Attempt {i}
```json
{json.dumps(attempt, indent=2, ensure_ascii=False)}
```
"""
    
    report += """
## Validation Errors
"""
    for error in errors:
        report += f"- ❌ {error}\n"
    
    if saga_error:
        report += f"""
## Saga Error
- **Failed Step**: {saga_error.step_name}
- **Error**: {saga_error.original_error}
"""
    
    report += f"""
## Required Action
Manual review required in the Review UI.

[Open in Review UI](https://review.example.com/document/{doc_hash})
"""
    
    return report
```

### 6.2 Quarantine Flow

```python
async def quarantine_document(
    doc_hash: str,
    source_path: str,
    attempts: List[dict],
    errors: List[str]
) -> None:
    """
    Move failed document to quarantine with report.
    """
    storage_client = storage.Client()
    
    # Generate paths
    filename = source_path.split("/")[-1]
    quarantine_folder = f"gs://bucket/quarantine/{doc_hash}/"
    
    # Copy original to quarantine
    _copy_blob(
        storage_client,
        source_path,
        f"{quarantine_folder}original_{filename}"
    )
    
    # Write extracted data
    data_blob = storage_client.bucket("bucket").blob(
        f"quarantine/{doc_hash}/extracted_data.json"
    )
    data_blob.upload_from_string(
        json.dumps(attempts[-1] if attempts else {}, indent=2, ensure_ascii=False),
        content_type="application/json"
    )
    
    # Write failed report
    report = generate_failed_report(doc_hash, source_path, attempts, errors)
    report_blob = storage_client.bucket("bucket").blob(
        f"quarantine/{doc_hash}/FAILED_REPORT.md"
    )
    report_blob.upload_from_string(report, content_type="text/markdown")
    
    # Update Firestore
    db = firestore.Client()
    db.collection("processed_documents").document(doc_hash).update({
        "status": "FAILED",
        "quarantine_path": quarantine_folder,
        "error_summary": errors[:3],  # First 3 errors
        "updated_at": firestore.SERVER_TIMESTAMP
    })
```

---

## 7. Resume from Compensation

When human approves corrected data in Review UI:

```python
async def resume_saga(doc_hash: str, corrected_data: dict) -> bool:
    """
    Resume saga after human correction.
    
    Called from Review UI after approval.
    """
    db = firestore.Client()
    doc_ref = db.collection("processed_documents").document(doc_hash)
    
    doc = doc_ref.get()
    if not doc.exists:
        raise ValueError(f"Document not found: {doc_hash}")
    
    data = doc.to_dict()
    
    if data["status"] != "FAILED":
        raise ValueError(f"Cannot resume non-FAILED document: {data['status']}")
    
    # Get paths
    quarantine_path = data.get("quarantine_path")
    original_filename = [f for f in list_blobs(quarantine_path) if f.startswith("original_")][0]
    source_path = f"{quarantine_path}{original_filename}"
    
    # Generate new destination
    dest_path = generate_output_path(corrected_data)
    
    # Run saga with corrected data
    return persist_document(
        doc_hash=doc_hash,
        validated_json=corrected_data,
        source_path=source_path,
        dest_path=dest_path,
        schema_version=corrected_data.get("schema_version", "v2")
    )
```

---

## 8. Testing Strategy

### 8.1 Unit Tests (Mocked Dependencies)

```python
# tests/unit/test_saga.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from core.saga import SagaOrchestrator, SagaStep, SagaFailedError

class TestSagaOrchestrator:
    """Unit tests for Saga orchestrator logic."""
    
    def test_all_steps_succeed(self):
        """Happy path: all steps execute successfully."""
        executed = []
        compensated = []
        
        steps = [
            SagaStep(
                name="step1",
                execute=lambda: executed.append("step1"),
                compensate=lambda: compensated.append("step1")
            ),
            SagaStep(
                name="step2",
                execute=lambda: executed.append("step2"),
                compensate=lambda: compensated.append("step2")
            ),
        ]
        
        saga = SagaOrchestrator()
        result = saga.execute(steps)
        
        assert result is True
        assert executed == ["step1", "step2"]
        assert compensated == []
    
    def test_step2_fails_compensates_step1(self):
        """When step 2 fails, step 1 is compensated."""
        executed = []
        compensated = []
        
        def fail_step2():
            executed.append("step2")
            raise Exception("Step 2 failed")
        
        steps = [
            SagaStep(
                name="step1",
                execute=lambda: executed.append("step1"),
                compensate=lambda: compensated.append("step1")
            ),
            SagaStep(
                name="step2",
                execute=fail_step2,
                compensate=lambda: compensated.append("step2")
            ),
        ]
        
        saga = SagaOrchestrator()
        
        with pytest.raises(SagaFailedError) as exc_info:
            saga.execute(steps)
        
        assert exc_info.value.step_name == "step2"
        assert executed == ["step1", "step2"]
        assert compensated == ["step1"]  # Only step1 compensated (step2 wasn't completed)
    
    def test_compensation_failure_logged_but_continues(self):
        """If compensation fails, continue compensating other steps."""
        compensated = []
        
        def fail_compensation():
            raise Exception("Compensation failed")
        
        steps = [
            SagaStep(
                name="step1",
                execute=lambda: None,
                compensate=lambda: compensated.append("step1")
            ),
            SagaStep(
                name="step2",
                execute=lambda: None,
                compensate=fail_compensation
            ),
            SagaStep(
                name="step3",
                execute=lambda: (_ for _ in ()).throw(Exception("Step 3 failed")),
                compensate=lambda: compensated.append("step3")
            ),
        ]
        
        saga = SagaOrchestrator()
        
        with pytest.raises(SagaFailedError):
            saga.execute(steps)
        
        # step1 should still be compensated even though step2 compensation failed
        assert "step1" in compensated
```

### 8.2 Integration Tests (Emulators)

```python
# tests/integration/test_saga_gcs.py
import pytest
from google.cloud import storage, firestore
import os

# Use emulators
os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"
os.environ["STORAGE_EMULATOR_HOST"] = "localhost:9023"

@pytest.fixture
def gcs_client():
    """GCS client connected to emulator."""
    client = storage.Client()
    bucket = client.create_bucket("test-bucket")
    yield client
    # Cleanup
    bucket.delete(force=True)

@pytest.fixture
def firestore_client():
    """Firestore client connected to emulator."""
    return firestore.Client()

class TestSagaGCSIntegration:
    """Integration tests with GCS emulator."""
    
    def test_copy_compensation_restores_source(self, gcs_client, firestore_client):
        """
        Scenario: GCS delete fails after copy.
        Expected: Source file is restored.
        """
        bucket = gcs_client.bucket("test-bucket")
        
        # Setup: Create source file
        source_blob = bucket.blob("input/test.pdf")
        source_blob.upload_from_string(b"test content")
        
        # Mock: Make delete fail
        with patch.object(storage.Blob, 'delete', side_effect=Exception("GCS unavailable")):
            from core.saga import persist_document
            
            result = persist_document(
                doc_hash="test-hash",
                validated_json={"management_id": "TEST-001"},
                source_path="gs://test-bucket/input/test.pdf",
                dest_path="gs://test-bucket/output/TEST-001.pdf",
                schema_version="v2"
            )
        
        # Assert: Source file still exists (compensation worked)
        assert source_blob.exists()
        
        # Assert: Status is FAILED
        doc = firestore_client.collection("processed_documents").document("test-hash").get()
        assert doc.to_dict()["status"] == "FAILED"
    
    def test_bigquery_failure_rolls_back_gcs(self, gcs_client, firestore_client):
        """
        Scenario: BigQuery insert fails after GCS copy.
        Expected: GCS destination file is deleted.
        """
        bucket = gcs_client.bucket("test-bucket")
        
        # Setup: Create source file
        source_blob = bucket.blob("input/test.pdf")
        source_blob.upload_from_string(b"test content")
        
        # Mock: Make BigQuery fail
        with patch("google.cloud.bigquery.Client.insert_rows_json", 
                   side_effect=Exception("BigQuery unavailable")):
            from core.saga import persist_document
            
            result = persist_document(
                doc_hash="test-hash",
                validated_json={"management_id": "TEST-001"},
                source_path="gs://test-bucket/input/test.pdf",
                dest_path="gs://test-bucket/output/TEST-001.pdf",
                schema_version="v2"
            )
        
        # Assert: Destination file was cleaned up
        dest_blob = bucket.blob("output/TEST-001.pdf")
        assert not dest_blob.exists()
        
        # Assert: Source file still exists
        assert source_blob.exists()
```

### 8.3 Chaos Testing (Production-like)

```python
# tests/chaos/test_saga_resilience.py
"""
Chaos tests - run against staging environment.

These tests inject real failures to verify compensation works
in production-like conditions.
"""
import pytest
from toxiproxy import Toxiproxy

@pytest.fixture
def toxiproxy():
    """Toxiproxy for network failure injection."""
    tp = Toxiproxy()
    yield tp
    tp.reset()

class TestSagaChaos:
    """Chaos engineering tests for Saga resilience."""
    
    @pytest.mark.chaos
    def test_network_partition_during_copy(self, toxiproxy):
        """
        Inject network partition during GCS copy.
        Verify saga handles timeout and compensates.
        """
        # Add latency to GCS
        gcs_proxy = toxiproxy.create_proxy("gcs", 
            upstream="storage.googleapis.com:443")
        gcs_proxy.add_toxic("latency", latency=30000)  # 30s latency
        
        # Run saga (should timeout and compensate)
        # ... test implementation
    
    @pytest.mark.chaos
    def test_firestore_unavailable_mid_saga(self, toxiproxy):
        """
        Make Firestore unavailable after step 2.
        Verify compensation still attempts to run.
        """
        # ... test implementation
```

### 8.4 Test Coverage Requirements

| Component | Target | Required Tests |
|-----------|--------|----------------|
| `SagaOrchestrator` | 100% | All paths |
| Step execution | 100% | Success, failure at each step |
| Compensation | 100% | Reverse order, partial failure |
| `persist_document` | 90% | Happy path, each step failure |
| `quarantine_failed` | 90% | File operations, DB update |
| `resume_saga` | 90% | From FAILED state |

### 8.5 Running Tests

```bash
# Unit tests (fast, no dependencies)
pytest tests/unit/test_saga.py -v

# Integration tests (requires emulators)
# Start emulators first:
# gcloud emulators firestore start
# fake-gcs-server -scheme http -port 9023
pytest tests/integration/test_saga_gcs.py -v

# Chaos tests (staging only, marked)
pytest tests/chaos/ -v -m chaos --env=staging
```

---

## 9. Monitoring

### Metrics

| Metric | Alert Threshold |
|--------|-----------------|
| Saga success rate | <95% |
| Compensation triggered | >5/hour |
| Compensation failures | Any |
| Quarantine growth | >10/day |

### Log Events

```python
log_processing_event("saga_started", doc_hash=hash, steps=4)
log_processing_event("saga_step_completed", doc_hash=hash, step="gcs_copy")
log_processing_event("saga_step_failed", doc_hash=hash, step="gcs_copy", error="...")
log_processing_event("saga_compensating", doc_hash=hash, steps_to_rollback=2)
log_processing_event("saga_completed", doc_hash=hash, status="COMPLETED")
log_processing_event("saga_failed", doc_hash=hash, status="FAILED")
```
