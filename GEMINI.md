# GEMINI.md

AI-OCR Smart Pipeline — Instructions for Claude Code

---
# Role
あなたはGCP環境に精通したシニアエンジニアです。

# Context
- このプロジェクトは [Python / Node.js等] で構成されています。
- 現在、GCPの [Cloud Shell / VM] 上で実行しています。
- GitのMainブランチはここ（GCP）にあります。

# Standard Rules
- コードを修正したら、必ず `python3 test.py` 等で動作確認をすること。
- エラーが出た場合は、ログを確認し、自己修正を試みること。
- GCPリソースの操作が必要な場合は `gcloud` コマンドを提案・実行すること。
- 作業が終わったら、変更内容を Git にコミットすること。

## Project Overview

Serverless pipeline that extracts Management ID, Company Name, and Date from non-standard business documents (delivery notes, invoices), organizes files into structured folders, and builds a queryable database.

**Stack**: Python 3.11 / Cloud Functions 2nd Gen / Document AI / Gemini API / Firestore / BigQuery / React + FastAPI

**Cost**: ~¥170/month for 100 documents (well under ¥3,000/month budget)

---

## Directory Structure

```
src/
├── core/                    # Business logic (critical)
│   ├── schemas.py           # Pydantic + SCHEMA_REGISTRY
│   ├── linters/
│   │   ├── gate.py          # Immutable validation
│   │   └── quality.py       # Config-driven validation
│   ├── prompts.py           # Gemini prompts + MULTIMODAL_SYSTEM_PROMPT
│   ├── extraction.py        # Model selection + image attachment logic
│   ├── lock.py              # Firestore distributed lock + heartbeat
│   ├── budget.py            # Pro API budget management
│   ├── saga.py              # Saga orchestrator
│   └── autosave.py          # Draft auto-save logic
├── functions/               # Cloud Function entry point
├── api/                     # FastAPI (Review UI backend)
└── ui/                      # React (Vite + Tailwind + shadcn/ui)

docs/specs/                  # Detailed specs (READ BEFORE IMPLEMENTING)
config/                      # YAML configuration files
ci/                          # CI/CD configuration
```

---

## Required Reading Before Implementation

| Task | Read This First |
|------|-----------------|
| Lock / Idempotency | `docs/specs/01_idempotency.md` |
| Retry / Escalation / Model Selection | `docs/specs/02_retry.md` |
| File Persistence | `docs/specs/03_saga.md` |
| Gemini API / Image Attachment | `docs/specs/04_confidence.md` |
| Schema Add/Change | `docs/specs/05_schema.md` |
| Validation | `docs/specs/06_linters.md` |
| Logging / Monitoring | `docs/specs/07_monitoring.md` |
| Security | `docs/specs/08_security.md` |
| Review UI | `docs/specs/09_review_ui.md` |
| Auto-save / Draft Recovery | `docs/specs/10_autosave.md` |
| Concurrent Edit Control | `docs/specs/11_conflict.md` |
| Failure Alerting | `docs/specs/12_alerting.md` |

**Do not implement without reading the relevant spec.**

---

## Model Selection Logic

```
Document Input
     │
     ▼
┌─────────────┐
│ Gemini Flash│ ◀── Default (cost-efficient)
└──────┬──────┘
       │
  ┌────┴────┐
  │         │
SUCCESS   FAILURE
  │         │
  ▼         ▼
DONE    Error Type?
          │
    ┌─────┼─────┐
    │     │     │
 SYNTAX SEMANTIC HTTP
    │     │     │
    ▼     ▼     ▼
 Flash   Pro   Flash
 Retry  Escal  Retry
 (x2)         (x3-5)
```

### Decision Table

| Error Type | Condition | Action |
|------------|-----------|--------|
| Syntax | JSON parse failed, schema mismatch | Flash retry (max 2) |
| Semantic | Gate Linter failed (missing fields, bad format) | Pro escalation |
| HTTP 429 | Rate limit | Flash retry with exponential backoff (max 5) |
| HTTP 5xx | Server error | Flash retry with fixed interval (max 3) |
| Pro Failure | Pro also failed Gate Linter | Human review (FAILED) |

### Implementation

```python
# core/extraction.py

def select_model(error_type: str, flash_attempts: int) -> str:
    """
    Select model based on error type and attempt count.
    
    Returns: "flash" | "pro" | "human"
    """
    if error_type == "syntax" and flash_attempts < 2:
        return "flash"
    
    if error_type == "http_429" and flash_attempts < 5:
        return "flash"
    
    if error_type == "http_5xx" and flash_attempts < 3:
        return "flash"
    
    if error_type == "semantic":
        if check_pro_budget():  # 50/day, 1000/month
            return "pro"
        else:
            return "human"
    
    return "human"
```

---

## Image Attachment Logic

```
Document AI Output
       │
       ▼
┌────────────────────────────┐
│ Check Conditions (OR)      │
│                            │
│ □ confidence < 0.85        │
│ □ Gate Linter failed       │
│ □ Retry attempt > 0        │
│ □ Fragile document type    │
└─────────────┬──────────────┘
              │
     ┌────────┴────────┐
     │                 │
  ANY TRUE         ALL FALSE
     │                 │
     ▼                 ▼
┌──────────┐    ┌──────────┐
│ Markdown │    │ Markdown │
│ + Image  │    │ Only     │
│ (~10K)   │    │ (~2K)    │
└──────────┘    └──────────┘
```

### Decision Table

| Condition | Threshold | Reason |
|-----------|-----------|--------|
| Low Confidence | `min(page, block) < 0.85` | OCR quality uncertain |
| Gate Failed | Previous attempt rejected | Structure not recognized |
| Retry | `attempt > 0` | First attempt failed |
| Fragile Type | `fax`, `handwritten`, `thermal_receipt` | Known OCR-difficult |

### Implementation

```python
# core/extraction.py

CONFIDENCE_THRESHOLD = 0.85
FRAGILE_TYPES = {"fax", "handwritten", "thermal_receipt", "carbon_copy"}

def should_attach_image(
    confidence: float,
    gate_failed: bool,
    attempt: int,
    doc_type: str | None
) -> tuple[bool, str]:
    """
    Returns (should_attach, reason).
    """
    if confidence < CONFIDENCE_THRESHOLD:
        return True, f"low_confidence:{confidence:.3f}"
    
    if gate_failed:
        return True, "gate_linter_failed"
    
    if attempt > 0:
        return True, f"retry:{attempt}"
    
    if doc_type in FRAGILE_TYPES:
        return True, f"fragile:{doc_type}"
    
    return False, "markdown_only"
```

---

## Vision/Markdown Priority (Prompt)

When both Markdown and Image are sent, conflicts may occur. Priority rules in system prompt:

| Aspect | Trust | Reason |
|--------|-------|--------|
| Structure (table layout, field position) | Markdown | Doc AI spatial analysis reliable |
| Text details (characters, smudges) | Image | Visual inspection needed |
| Minor diff (1-2 chars) | Image | OCR misread |
| Structural diff | Markdown | Re-read text from image |
| Ambiguous | Flag with `confidence=0.5` | Human review |

See `docs/specs/04_confidence.md` §4 for full prompt.

---

## Operational Requirements (Critical)

### 1. Auto-save (Prevent Data Loss)

```typescript
// Save draft every 30 seconds
// 1. localStorage (immediate)
// 2. Firestore draft (async backup)
// On page load: prompt to restore if draft exists
```

See `docs/specs/10_autosave.md`.

### 2. Concurrent Edit Control

```python
# Optimistic locking with updated_at
# If conflict detected: "Document modified by another user. Reload."
```

See `docs/specs/11_conflict.md`.

### 3. Failure Alerting

```yaml
# Dead Letter Queue for failed documents
# Slack notification on permanent failure
# Health check every 15 minutes
```

See `docs/specs/12_alerting.md`.

### 4. Audit Trail

```python
# Log all corrections: before/after/user/timestamp
# Append-only collection (no updates/deletes)
# Required for compliance
```

See `docs/specs/08_security.md` §5.

---

## Cost Breakdown (100 docs/month)

| Service | Monthly Cost |
|---------|--------------|
| Document AI | ¥150 |
| Gemini API | ¥17 |
| Cloud Functions | ¥0 (free tier) |
| Cloud Storage | ¥2 |
| Firestore | ¥2 |
| BigQuery | ¥0 (free tier) |
| Cloud Run | ¥2 |
| **Total** | **~¥170** |

**7-year projection**: ~¥15,000 (well under ¥252,000 budget)

**Risk**: Pro escalation rate increase. If 5% → 20%, monthly cost triples.

---

## Coding Standards

### Python

```bash
# Enforced in CI/CD
ruff check . --fix      # Linter
black .                 # Formatter
mypy src/ --strict      # Type checking
```

**Required**:
- Type hints mandatory (`def func(x: str) -> int:`)
- Function complexity ≤ 10 (mccabe)
- Docstrings required for public functions
- Use `from __future__ import annotations`

**Forbidden**:
- Overuse of `Any` type
- `# type: ignore` without justification
- Global variables
- `print()` — use `structlog` instead

### TypeScript/React

- Functional components only
- Props type definitions required
- Use Tailwind CSS (no inline styles)
- Prefer shadcn/ui components

---

## Test Requirements

| Layer | Coverage Target | Tools |
|-------|-----------------|-------|
| `src/core/` | ≥90% | pytest + hypothesis |
| `src/api/` | ≥80% | pytest + httpx |
| `src/ui/` | ≥70% | vitest + testing-library |

```bash
pytest tests/unit --cov=src/core --cov-fail-under=90
```

**Required Tests**:
- All Gate Linter rules
- Schema migration functions
- Saga compensation transactions
- Model selection logic
- Image attachment conditions
- Optimistic lock conflict handling

---

## Commit Messages

```
<type>(<scope>): <subject>

<body>
```

**type**: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`  
**scope**: `core`, `api`, `ui`, `ci`, `config`

Example:
```
feat(core): add heartbeat to distributed lock

Prevents zombie locks during long Pro escalations.
See docs/specs/01_idempotency.md §4
```

---

## Key Design Decisions

### 1. Gate Linter vs Quality Linter

- **Gate**: Failure → Block persistence (affects file naming)
- **Quality**: Failure → Warning only (flagged in UI)

Be careful when modifying Gate Linter rules. Changes may break consistency with existing files.

### 2. Schema Changes

1. Define new version (`DeliveryNoteV3`)
2. Create migration function (`migrate_v2_to_v3`)
3. Track defaulted values with `_migration_metadata`
4. Add old version to `deprecated` list

**Always** follow the checklist in `docs/specs/05_schema.md` §8.

### 3. Model Selection

- Default: Flash (cost-efficient)
- Escalate to Pro: Only on semantic errors (Gate Linter failed)
- Never escalate on syntax/HTTP errors (retry Flash instead)
- Always check budget before Pro call

### 4. Image Attachment

- Default: Markdown only (2K tokens)
- Attach image: Low confidence OR failure OR retry (10K tokens)
- Cost impact: 5x token increase when image attached

### 5. Learning Cycle (Correction Data)

- **NOT automatic**: Corrections are saved to BigQuery
- **Manual curation**: Engineer selects 10-20 golden examples monthly
- **Few-shot update**: Manually add to prompt, not auto-injection
- **Future**: Fine-tuning or RAG when data volume grows

---

## Do NOT Do These

| ❌ Forbidden | ✅ Alternative |
|--------------|---------------|
| Allow document_type not in `SCHEMA_REGISTRY` | Fail-fast with `UnsupportedDocumentTypeError` |
| Externalize Gate Linter rules to config | Gate Linter rules stay immutable in code |
| Return early from Saga steps | Always execute all steps OR compensate |
| File operations without lock | Use `distributed_lock` context manager |
| Call Gemini Pro without budget check | Always call `check_pro_budget()` first |
| Escalate to Pro on syntax errors | Retry Flash (syntax errors are random) |
| Attach image on every request | Only when conditions met (cost control) |
| Log production data (PII, amounts) | Mask sensitive fields |
| Edit `requirements.txt` directly | Edit `pyproject.toml` dependencies |
| Assume auto-learning from corrections | Manual curation required |

---

## Debug Commands

```bash
# Run Cloud Function locally
functions-framework --target=main --debug

# Firestore emulator
gcloud emulators firestore start

# Type check
mypy src/ --strict

# Security scan
bandit -r src/ -ll

# Test model selection
pytest tests/unit/test_extraction.py -v

# Test image attachment logic
pytest tests/unit/test_confidence.py -v
```

---

## Implementation Progress Management

### 📋 Implementation Plan

**Current Status**: Phase 1 (Foundation) - 0/15 tasks complete

**Primary Document**: [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)

This file contains:
- 62 detailed tasks across 5 phases (10 weeks)
- Checkbox tracking for each task
- Dependencies and completion criteria
- Risk management and assumptions
- Session recovery instructions

**Progress Tracking**:
- Update checkboxes in `IMPLEMENTATION_PLAN.md` as you complete tasks
- Commit changes after each significant milestone
- Use Serena memory to checkpoint progress every 30 minutes

### 🔄 Session Recovery Protocol

When starting a new Claude Code session:

1. **Load Context**
   ```bash
   # Read implementation plan to see current progress
   cat docs/IMPLEMENTATION_PLAN.md | grep -A 5 "Progress Overview"

   # Restore Serena memory (if available)
   /sc:load
   ```

2. **Check Git Status**
   ```bash
   git status
   git log --oneline -5
   ```

3. **Review Last Checkpoint**
   - Check Serena memory keys: `plan_phase`, `plan_task`, `plan_checkpoint`
   - Read "Last Session" section at bottom of IMPLEMENTATION_PLAN.md
   - Review last commit message for context

4. **Resume Work**
   - Identify next unchecked task in implementation plan
   - Read relevant spec docs (📖 Read First links)
   - Continue implementation with TodoWrite tracking

### 💾 Checkpointing Strategy

**Every 30 minutes during implementation**:
```python
# Use Serena to save checkpoint
write_memory("plan_checkpoint", {
    "phase": "1",
    "task": "1.2",
    "description": "Implementing BaseDocumentSchema",
    "timestamp": "2025-01-13T10:30:00+09:00",
    "next_steps": ["Add validation tests", "Test registry lookup"]
})
```

**After completing a task**:
1. Mark checkbox in IMPLEMENTATION_PLAN.md
2. Run tests and ensure they pass
3. Commit with descriptive message (see format below)
4. Update Serena memory with new checkpoint
5. Push to GitHub

**Commit Message Format for Progress**:
```
feat(core): implement distributed lock with heartbeat

Complete task 1.5 from implementation plan.
- Add Firestore-backed locking
- Implement heartbeat refresh thread
- Add unit tests with emulator

Refs: docs/specs/01_idempotency.md
Progress: Phase 1 - 5/15 tasks complete

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

### 📊 Progress Visibility

**Quick Status Check**:
```bash
# Count completed tasks
grep -c "- \[x\]" docs/IMPLEMENTATION_PLAN.md

# View current phase progress
grep "^| Phase" docs/IMPLEMENTATION_PLAN.md
```

**Serena Memory Keys**:
- `plan_phase`: Current phase number (1-5)
- `plan_task`: Current task ID (e.g., "1.5")
- `plan_checkpoint`: Last completed milestone with timestamp
- `plan_blockers`: Any active impediments requiring attention
- `plan_decisions`: Key architectural decisions made during implementation
- `plan_deviations`: Any deviations from original plan with rationale

### ⚠️ Important Notes

- **Never skip spec reading**: Each task has "📖 Read First" links - read before implementing
- **Test before marking complete**: All tasks require tests passing
- **Update plan for deviations**: If you deviate from plan, document why in IMPLEMENTATION_PLAN.md
- **Commit frequently**: Small, incremental commits are better than large ones
- **Checkpoint regularly**: Save to Serena every 30 min to prevent losing progress

---

## When You Have Questions

1. First, read the relevant `docs/specs/*.md`
2. If still unclear, check "Key Design Decisions" above
3. If still unclear, ask about design intent in comments

---

## Quick Reference

| Constant | Value | Location |
|----------|-------|----------|
| `CONFIDENCE_THRESHOLD` | 0.85 | `core/extraction.py` |
| `LOCK_TTL_SECONDS` | 600 | `core/lock.py` |
| `HEARTBEAT_INTERVAL` | 120 | `core/lock.py` |
| `PRO_DAILY_LIMIT` | 50 | `core/budget.py` |
| `PRO_MONTHLY_LIMIT` | 1000 | `core/budget.py` |
| `FLASH_SYNTAX_RETRIES` | 2 | `core/extraction.py` |
| `FLASH_HTTP429_RETRIES` | 5 | `core/extraction.py` |
| `FLASH_HTTP5XX_RETRIES` | 3 | `core/extraction.py` |
| `AUTOSAVE_INTERVAL` | 30000 | `ui/hooks/useAutosave.ts` |
| `FRAGILE_TYPES` | fax, handwritten, thermal_receipt, carbon_copy | `core/extraction.py` |
| `BUDGET_TIMEZONE` | Asia/Tokyo | `core/budget.py` |

---

## Timezone & Internationalization

### Timezone Policy

| Context | Timezone | Rationale |
|---------|----------|-----------|
| Budget reset (daily/monthly) | JST (Asia/Tokyo) | Business day alignment |
| Log timestamps | UTC | Cloud standard |
| UI display | JST | User-facing |
| API responses | ISO 8601 with offset | Explicit |

```python
# core/budget.py
from zoneinfo import ZoneInfo

BUDGET_TIMEZONE = ZoneInfo("Asia/Tokyo")

def get_budget_date() -> str:
    """Get current date in budget timezone."""
    return datetime.now(BUDGET_TIMEZONE).date().isoformat()

def get_budget_month() -> str:
    """Get current month in budget timezone."""
    return datetime.now(BUDGET_TIMEZONE).strftime("%Y-%m")
```

### Internationalization

| Layer | Language | Notes |
|-------|----------|-------|
| Code / logs | English | Universal |
| UI labels | Japanese | Hardcoded for MVP |
| Error messages (user-facing) | Japanese | Hardcoded for MVP |
| Documentation | English | Spec files |

**Future**: Add `react-i18next` for multi-language support if needed.
