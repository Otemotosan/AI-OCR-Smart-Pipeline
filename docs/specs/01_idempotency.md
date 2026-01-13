# Idempotency & Duplicate Prevention

**Spec ID**: 01  
**Status**: Final  
**Dependencies**: Firestore

---

## 1. Problem Statement

Webhooks deliver "at least once." Without idempotency guards:
- Duplicate files in output folders
- Duplicate records in BigQuery
- Wasted Gemini API costs

---

## 2. Design

### 2.1 Processing Key

**SHA-256 file hash** — survives file renames, guarantees content identity.

```python
import hashlib

def compute_file_hash(content: bytes) -> str:
    """Compute SHA-256 hash of file content."""
    return f"sha256:{hashlib.sha256(content).hexdigest()}"
```

### 2.2 Lock Store

**Firestore** — serverless, transactional, cost-effective for low volume.

### 2.3 Document Schema

```python
# Collection: processed_documents
{
    "hash": "sha256:abc123...",           # Document ID
    "status": "PENDING|COMPLETED|FAILED",
    "gcs_source_path": "gs://bucket/input/file.pdf",
    "gcs_output_path": "gs://bucket/output/ID_Company_Date.pdf",
    "created_at": "2025-01-09T10:00:00Z",
    "updated_at": "2025-01-09T10:05:00Z",
    "lock_expires_at": "2025-01-09T10:10:00Z",
    "error_message": null
}
```

---

## 3. Lock Acquisition

### 3.1 Basic Lock

```python
from google.cloud import firestore
from datetime import datetime, timedelta

LOCK_TTL_SECONDS = 600  # 10 minutes

def acquire_lock(file_hash: str, ttl_seconds: int = LOCK_TTL_SECONDS) -> bool:
    """
    Atomically acquire processing lock.
    Returns True if lock acquired, False if already processed/processing.
    """
    db = firestore.Client()
    doc_ref = db.collection("processed_documents").document(file_hash)
    
    @firestore.transactional
    def _acquire(transaction):
        snapshot = doc_ref.get(transaction=transaction)
        now = datetime.utcnow()
        
        if snapshot.exists:
            data = snapshot.to_dict()
            
            # Already completed — skip
            if data["status"] == "COMPLETED":
                return False
            
            # Lock held by another instance — check expiry
            if data["status"] == "PENDING":
                expires_at = data.get("lock_expires_at")
                if expires_at and expires_at > now:
                    return False  # Lock still valid
                # Lock expired — take over
        
        # Acquire lock
        transaction.set(doc_ref, {
            "hash": file_hash,
            "status": "PENDING",
            "lock_expires_at": now + timedelta(seconds=ttl_seconds),
            "created_at": now if not snapshot.exists else data.get("created_at"),
            "updated_at": now,
        }, merge=True)
        return True
    
    return _acquire(db.transaction())
```

---

## 4. Heartbeat Extension (Zombie Prevention)

### 4.1 Problem

If Gemini Pro escalation hits rate limits (429) and exponential backoff exceeds 10 minutes, the lock expires and a duplicate webhook triggers re-processing.

### 4.2 Solution

Extend lock periodically during long-running operations.

```python
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

LOCK_TTL_SECONDS = 600
HEARTBEAT_INTERVAL = 120  # Extend every 2 minutes

class LockNotAcquiredError(Exception):
    """Raised when lock cannot be acquired."""
    pass

@asynccontextmanager
async def distributed_lock(doc_hash: str):
    """
    Distributed lock with automatic heartbeat extension.
    
    Usage:
        async with distributed_lock("sha256:abc123"):
            await process_document(...)
    """
    db = firestore.Client()
    doc_ref = db.collection("processed_documents").document(doc_hash)
    heartbeat_task: Optional[asyncio.Task] = None
    
    async def _heartbeat():
        """Periodically extend lock TTL."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                doc_ref.update({
                    "lock_expires_at": datetime.utcnow() + timedelta(seconds=LOCK_TTL_SECONDS),
                    "updated_at": datetime.utcnow()
                })
            except Exception as e:
                # Log but don't crash — lock will eventually expire
                logger.warning(f"Heartbeat failed for {doc_hash}: {e}")
    
    try:
        # Acquire lock
        acquired = acquire_lock(doc_hash, LOCK_TTL_SECONDS)
        if not acquired:
            raise LockNotAcquiredError(
                f"Document {doc_hash} is already being processed or completed"
            )
        
        # Start heartbeat background task
        heartbeat_task = asyncio.create_task(_heartbeat())
        
        yield doc_ref
        
    finally:
        # Stop heartbeat
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
```

### 4.3 Usage in Pipeline

```python
async def process_document(file_content: bytes, source_path: str):
    """Main document processing entry point."""
    file_hash = compute_file_hash(file_content)
    
    try:
        async with distributed_lock(file_hash) as doc_ref:
            # Update source path
            doc_ref.update({"gcs_source_path": source_path})
            
            # Process (may take >10 minutes with Pro escalation)
            result = await extract_with_self_correction(...)
            
            # Persist via Saga
            await persist_document(file_hash, result, ...)
            
    except LockNotAcquiredError:
        logger.info(f"Skipping duplicate: {file_hash}")
        return
```

---

## 5. Lock State Transitions

```
                    ┌─────────────┐
                    │   (none)    │
                    └──────┬──────┘
                           │ acquire_lock()
                           ▼
                    ┌─────────────┐
            ┌───────│   PENDING   │───────┐
            │       └─────────────┘       │
            │              │              │
    heartbeat()      processing      lock_expires
            │              │              │
            ▼              ▼              ▼
     ┌───────────┐  ┌───────────┐  ┌───────────┐
     │  PENDING  │  │ COMPLETED │  │  (none)   │
     │ (extended)│  └───────────┘  │  or stale │
     └───────────┘                 └───────────┘
                           │
                   saga failed
                           │
                           ▼
                    ┌───────────┐
                    │  FAILED   │
                    └───────────┘
```

---

## 6. Edge Cases

| Scenario | Behavior |
|----------|----------|
| Duplicate webhook within TTL | Lock check fails, skip processing |
| Duplicate webhook after TTL (no heartbeat) | Lock takeover, potential duplicate |
| Duplicate webhook after TTL (with heartbeat) | Lock still valid, skip processing |
| Cloud Function crash | Lock expires, retry picks up |
| Firestore unavailable | Fail-open with error log, human intervention |

---

## 7. Monitoring

### Metrics to Track

| Metric | Alert Threshold |
|--------|-----------------|
| Lock acquisition failures/hour | >10 |
| Heartbeat failures/hour | >5 |
| Stale locks (PENDING > 30 min) | >3 |

### Log Events

```python
log_processing_event("lock_acquired", doc_hash=file_hash)
log_processing_event("lock_skipped_duplicate", doc_hash=file_hash)
log_processing_event("heartbeat_extended", doc_hash=file_hash)
log_processing_event("lock_released", doc_hash=file_hash, status="COMPLETED")
```
