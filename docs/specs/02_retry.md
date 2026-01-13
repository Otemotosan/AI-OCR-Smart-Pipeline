# Retry & Escalation Strategy

**Spec ID**: 02  
**Status**: Final  
**Dependencies**: Tenacity, Firestore

---

## 1. Design Philosophy

Not all errors are equal. Retry strategy must match error characteristics:
- **Transient**: Will likely succeed on retry (network, rate limits)
- **Syntax**: AI output malformed, try again with same model
- **Semantic**: AI doesn't understand, escalate to smarter model

---

## 2. Error Classification

| Error Type | Example | Strategy | Max Attempts |
|------------|---------|----------|--------------|
| HTTP 429 | Gemini rate limit | Exponential backoff + jitter | 5 |
| HTTP 5xx | Transient server error | Fixed interval | 3 |
| Syntax | JSON parse failure | Immediate retry (Flash) | 2 |
| Semantic | Missing required fields | Escalate to Pro | 1 |
| Pro Failure | Pro can't extract | Human escalation | 0 |

---

## 3. Tenacity Configuration

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
    wait_random,
    retry_if_exception_type,
)
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable

# Custom exceptions
class SyntaxValidationError(Exception):
    """Raised when Gemini output is not valid JSON."""
    pass

class SemanticValidationError(Exception):
    """Raised when extracted data fails Gate Linter."""
    pass

class ProBudgetExhaustedError(Exception):
    """Raised when Pro call budget is exceeded."""
    pass


# === Rate Limit Handler ===
retry_rate_limit = retry(
    retry=retry_if_exception_type(ResourceExhausted),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=32) + wait_random(0, 2),
    reraise=True
)

# === Transient Error Handler ===
retry_transient = retry(
    retry=retry_if_exception_type(ServiceUnavailable),
    stop=stop_after_attempt(3),
    wait=wait_fixed(2),
    reraise=True
)

# === Syntax Error Handler ===
retry_syntax = retry(
    retry=retry_if_exception_type(SyntaxValidationError),
    stop=stop_after_attempt(2),
    wait=wait_fixed(0),  # Immediate retry
    reraise=True
)
```

---

## 4. Escalation Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     ESCALATION FLOW                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Document Input                                              │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────┐                                        │
│  │  Gemini Flash   │◀──────────────────┐                    │
│  └────────┬────────┘                   │                    │
│           │                            │                    │
│    ┌──────┼──────┐                     │                    │
│    │      │      │                     │                    │
│    ▼      ▼      ▼                     │                    │
│  ┌───┐ ┌─────┐ ┌────────┐              │                    │
│  │ ✓ │ │Syntax│ │Semantic│              │                    │
│  └─┬─┘ │Error │ │ Error  │              │                    │
│    │   └──┬──┘ └───┬────┘              │                    │
│    │      │        │                    │                    │
│    │      │        ▼                    │                    │
│    │      │   ┌──────────┐              │                    │
│    │      │   │ Check Pro│              │                    │
│    │      │   │  Budget  │              │                    │
│    │      │   └────┬─────┘              │                    │
│    │      │        │                    │                    │
│    │      │   ┌────┴────┐               │                    │
│    │      │   │         │               │                    │
│    │      │   ▼         ▼               │                    │
│    │      │ Budget    Budget            │                    │
│    │      │  OK       Exceeded          │                    │
│    │      │   │         │               │                    │
│    │      │   ▼         ▼               │                    │
│    │      │ ┌─────┐  ┌────────┐         │                    │
│    │      │ │ Pro │  │ FAILED │         │                    │
│    │      │ └──┬──┘  │→ Human │         │                    │
│    │      │    │     └────────┘         │                    │
│    │      │    │                        │                    │
│    │      │ ┌──┴──┐                     │                    │
│    │      │ │     │                     │                    │
│    │      │ ▼     ▼                     │                    │
│    │      │ ✓   Failed                  │                    │
│    │      │ │     │                     │                    │
│    │      │ │     ▼                     │                    │
│    │      │ │  ┌────────┐               │                    │
│    │      │ │  │ FAILED │               │                    │
│    │      │ │  │→ Human │               │                    │
│    │      │ │  └────────┘               │                    │
│    │      │ │                           │                    │
│    │      └─┼───── retry < 2? ──────────┘                    │
│    │        │                                                │
│    ▼        ▼                                                │
│  ┌─────────────────┐                                        │
│  │   Gate Linter   │                                        │
│  └─────────────────┘                                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Pro Budget Enforcement

### 5.1 Budget Limits

| Limit | Value | Rationale |
|-------|-------|-----------|
| Daily | 50 calls | Cost control (~$1/day max) |
| Monthly | 1,000 calls | Budget ceiling |

### 5.2 Implementation

```python
from google.cloud import firestore
from datetime import datetime

DAILY_LIMIT = 50
MONTHLY_LIMIT = 1000

def check_pro_budget() -> bool:
    """
    Check if Pro calls are within budget.
    Returns True if budget available, False otherwise.
    """
    db = firestore.Client()
    budget_ref = db.collection("system_config").document("pro_budget")
    
    doc = budget_ref.get()
    if not doc.exists:
        return True  # No usage yet
    
    data = doc.to_dict()
    today = datetime.utcnow().date().isoformat()
    month = datetime.utcnow().strftime("%Y-%m")
    
    daily_count = data.get("daily", {}).get(today, 0)
    monthly_count = data.get("monthly", {}).get(month, 0)
    
    if daily_count >= DAILY_LIMIT:
        logger.warning(f"Pro daily limit reached: {daily_count}/{DAILY_LIMIT}")
        return False
    
    if monthly_count >= MONTHLY_LIMIT:
        logger.warning(f"Pro monthly limit reached: {monthly_count}/{MONTHLY_LIMIT}")
        return False
    
    return True


def increment_pro_usage() -> None:
    """Atomically increment Pro usage counters."""
    db = firestore.Client()
    budget_ref = db.collection("system_config").document("pro_budget")
    
    today = datetime.utcnow().date().isoformat()
    month = datetime.utcnow().strftime("%Y-%m")
    
    budget_ref.set({
        f"daily.{today}": firestore.Increment(1),
        f"monthly.{month}": firestore.Increment(1),
        "last_updated": datetime.utcnow()
    }, merge=True)


def get_pro_usage() -> dict:
    """Get current Pro usage statistics."""
    db = firestore.Client()
    budget_ref = db.collection("system_config").document("pro_budget")
    
    doc = budget_ref.get()
    if not doc.exists:
        return {"daily": 0, "monthly": 0}
    
    data = doc.to_dict()
    today = datetime.utcnow().date().isoformat()
    month = datetime.utcnow().strftime("%Y-%m")
    
    return {
        "daily": data.get("daily", {}).get(today, 0),
        "monthly": data.get("monthly", {}).get(month, 0),
        "daily_limit": DAILY_LIMIT,
        "monthly_limit": MONTHLY_LIMIT
    }
```

---

## 6. Combined Retry Logic

```python
from typing import Tuple, Optional
import json

async def call_gemini_with_retry(
    prompt: str,
    image_base64: Optional[str] = None,
    model: str = "flash"
) -> str:
    """
    Call Gemini with appropriate retry strategy.
    Handles rate limits and transient errors.
    """
    
    @retry_rate_limit
    @retry_transient
    async def _call():
        if model == "flash":
            return await gemini_flash_client.generate(prompt, image_base64)
        else:
            return await gemini_pro_client.generate(prompt, image_base64)
    
    return await _call()


async def extract_with_escalation(
    markdown: str,
    image_base64: Optional[str],
    schema_class: type
) -> Tuple[dict, str]:
    """
    Extract data with self-correction and escalation.
    
    Returns:
        Tuple of (extracted_data, terminal_status)
        terminal_status: "COMPLETED" | "FAILED"
    """
    gate_linter = GateLinter()
    attempts = []
    last_errors = []
    
    # === Phase 1: Flash with self-correction ===
    for attempt in range(3):  # Initial + 2 retries
        try:
            # Build prompt
            if attempt == 0:
                prompt = build_initial_prompt(markdown, schema_class)
            else:
                prompt = build_correction_prompt(
                    markdown=markdown,
                    previous_attempts=attempts,
                    errors=last_errors
                )
            
            # Include image on retry
            img = image_base64 if attempt > 0 else None
            
            # Call Flash
            response = await call_gemini_with_retry(prompt, img, model="flash")
            
            # Parse JSON
            try:
                extracted = json.loads(response)
            except json.JSONDecodeError as e:
                raise SyntaxValidationError(f"Invalid JSON: {e}")
            
            attempts.append(extracted)
            
            # Validate with Gate Linter
            gate_result = gate_linter.validate(extracted)
            
            if gate_result.passed:
                # Validate with Pydantic
                validated = schema_class(**extracted)
                return validated.dict(), "COMPLETED"
            
            # Gate failed — semantic error
            last_errors = gate_result.errors
            
            if attempt < 2:
                continue  # Retry with correction prompt
            
            # Max Flash attempts exhausted
            raise SemanticValidationError(f"Gate validation failed: {last_errors}")
            
        except SyntaxValidationError:
            if attempt < 2:
                continue
            raise
    
    # === Phase 2: Pro Escalation ===
    if not check_pro_budget():
        logger.error("Pro budget exhausted, routing to human review")
        return attempts[-1] if attempts else {}, "FAILED"
    
    try:
        increment_pro_usage()
        
        prompt = build_correction_prompt(
            markdown=markdown,
            previous_attempts=attempts,
            errors=last_errors,
            escalation_note="Previous attempts with Flash failed. Apply deep reasoning."
        )
        
        response = await call_gemini_with_retry(prompt, image_base64, model="pro")
        extracted = json.loads(response)
        
        gate_result = gate_linter.validate(extracted)
        
        if gate_result.passed:
            validated = schema_class(**extracted)
            return validated.dict(), "COMPLETED"
        
        # Pro also failed
        logger.error(f"Pro extraction failed: {gate_result.errors}")
        return extracted, "FAILED"
        
    except Exception as e:
        logger.error(f"Pro escalation error: {e}")
        return attempts[-1] if attempts else {}, "FAILED"
```

---

## 7. Monitoring

### Metrics

| Metric | Alert Threshold |
|--------|-----------------|
| Flash retry rate | >30% of requests |
| Pro escalation rate | >20% of requests |
| Pro budget utilization | >80% daily |
| Total failure rate | >5% hourly |

### Log Events

```python
log_processing_event("gemini_flash_attempt", attempt=1, doc_hash=hash)
log_processing_event("gemini_flash_syntax_error", attempt=1, error="...")
log_processing_event("gemini_pro_escalation", doc_hash=hash, reason="semantic")
log_processing_event("gemini_pro_budget_exceeded", doc_hash=hash)
log_processing_event("extraction_failed", doc_hash=hash, attempts=3)
```
