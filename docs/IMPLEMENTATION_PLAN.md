# AI-OCR Smart Pipeline - Implementation Plan

**Version**: 1.0
**Status**: 🚧 In Progress
**Started**: 2025-01-13
**Last Updated**: 2025-01-13

---

## Progress Overview

| Phase | Status | Progress | Duration |
|-------|--------|----------|----------|
| Phase 1: Foundation | 🔄 In Progress | 5/7 | Week 1-2 |
| Phase 2: Core Pipeline | ⏳ Pending | 0/7 | Week 3-4 |
| Phase 3: Escalation | ⏳ Pending | 0/7 | Week 5-6 |
| Phase 4: Review UI | ⏳ Pending | 0/10 | Week 7-8 |
| Phase 5: Hardening | ⏳ Pending | 0/7 | Week 9-10 |

**Total Progress**: 5/38 tasks (13%)

---

## Phase 1: Foundation (Week 1-2)

**Goal**: Establish core infrastructure and validation framework

**Deliverables**: Schema registry, Gate Linter, Firestore lock, basic test framework

### 1.1 Project Setup

- [x] Create `src/core/` directory structure
- [x] Set up `pyproject.toml` with dependencies
  - [x] pydantic >= 2.0
  - [x] google-cloud-firestore
  - [x] google-cloud-storage
  - [x] google-cloud-documentai
  - [x] google-generativeai
  - [x] tenacity
  - [x] structlog
- [x] Configure pytest with coverage
- [x] Set up mypy strict type checking
- [x] Configure ruff linter

**Completion Criteria**: `pytest --version` runs, all tools installed

**Dependencies**: None

**Status**: ✅ Completed (2025-01-13)

---

### 1.2 Schema Registry (`src/core/schemas.py`)

**📖 Read First**: `docs/specs/05_schema.md`

- [x] Define schema structures (dataclasses + Pydantic models)
- [x] Implement `DeliveryNoteV1` schema
- [x] Implement `DeliveryNoteV2` schema (current)
- [x] Implement `InvoiceV1` schema
- [x] Create `SCHEMA_REGISTRY` with SchemaConfig
- [x] Implement `get_schema()` function
- [x] Implement `migrate_data()` for version migrations
- [x] Implement `migrate_delivery_note_v1_to_v2()`
- [x] Add `validate_new_document()` for deprecation checks
- [x] Add `list_schemas()` utility
- [x] Add `generate_schema_description()` for prompts
- [x] Write comprehensive unit tests (≥90% coverage)
  - [x] Test schema validation
  - [x] Test registry lookup
  - [x] Test version mismatch errors
  - [x] Test migration functions
  - [x] Test error handling

**Completion Criteria**:
- All tests pass ✅
- `mypy src/core/schemas.py --strict` passes ✅
- Can instantiate and validate schemas ✅

**Dependencies**: None

**Status**: ✅ Completed (2025-01-13)

---

### 1.3 Gate Linter (`src/core/linters/gate.py`)

**📖 Read First**: `docs/specs/06_linters.md`

- [x] Create `GateLinterResult` dataclass
  - [x] `passed: bool`
  - [x] `errors: list[str]`
- [x] Implement `GateLinter` class with 6 immutable rules
  - [x] G1: management_id non-empty
  - [x] G2: management_id format (6-20 alphanumeric + hyphens/underscores)
  - [x] G3: company_name non-empty
  - [x] G4: issue_date valid date format
  - [x] G5: issue_date not future
  - [x] G6: document_type in registry
- [x] Add `validate(data: dict) -> GateLinterResult` method
- [x] Add `_parse_date()` helper for multiple date formats
- [x] Write comprehensive unit tests (≥90% coverage)
  - [x] Test each rule individually (G1-G6)
  - [x] Test edge cases and boundary values
  - [x] Test multiple failures
  - [x] Test date parsing variations
  - [x] Test valid ID formats

**Completion Criteria**:
- All immutable rules implemented ✅
- Tests achieve ≥90% coverage ✅
- No false positives on valid data ✅

**Dependencies**: 1.2 (schemas.py)

**Status**: ✅ Completed (2025-01-13)

---

### 1.4 Quality Linter (`src/core/linters/quality.py`)

**📖 Read First**: `docs/specs/06_linters.md`, `config/quality_rules.yaml`

- [x] Create dataclasses (QualityRule, QualityWarning, QualityLinterResult)
- [x] Implement `QualityLinter` class
  - [x] `_load_rules()` - Parse YAML configuration
  - [x] `validate()` - Run all rules on data
  - [x] `_evaluate_rule()` - Dispatch to condition handlers
  - [x] `_check_date_sequence()` - Validate chronological order
  - [x] `_check_vendor_exists()` - Vendor master lookup (placeholder)
  - [x] `_check_range()` - Min/max value validation
  - [x] Vendor caching for performance
- [x] Write comprehensive unit tests (≥80% coverage)
  - [x] Test YAML loading (existing + missing files)
  - [x] Test date sequence validation
  - [x] Test range checks (min/max/custom message)
  - [x] Test vendor existence check
  - [x] Test multiple warnings
  - [x] Test unknown conditions (graceful handling)
  - [x] Test dataclass structures

**Completion Criteria**:
- Can load rules from YAML ✅
- Warning-only failures (never blocks) ✅
- Tests pass ✅

**Dependencies**: 1.2 (schemas.py), 1.3 (gate.py)

**Status**: ✅ Completed (2025-01-13)

---

### 1.5 Distributed Lock (`src/core/lock.py`)

**📖 Read First**: `docs/specs/01_idempotency.md`

- [x] Implement `DistributedLock` class
  - [x] `acquire()` context manager with Firestore transaction
  - [x] `release()` with final status update
  - [x] `compute_file_hash()` static method for SHA-256
  - [x] Heartbeat mechanism with threading
- [x] Add Firestore backend
  - [x] Collection: `processed_documents`
  - [x] Document fields: `{hash, status, lock_expires_at, created_at, updated_at}`
  - [x] Atomic lock acquisition with transaction
- [x] Implement context manager
  - [x] `__enter__` acquires lock with automatic heartbeat start
  - [x] `__exit__` stops heartbeat and releases lock
  - [x] Exception handling and cleanup
- [x] Add heartbeat thread (every 120s by default)
  - [x] Background thread with stop event
  - [x] Automatic TTL extension
  - [x] Graceful error handling
- [x] Write comprehensive unit tests with mocks
  - [x] Test file hash computation and consistency
  - [x] Test lock acquisition (new, completed, active, expired)
  - [x] Test heartbeat lifecycle (start, stop, extend)
  - [x] Test context manager behavior and cleanup
  - [x] Test release with COMPLETED/FAILED status
  - [x] Test integration scenarios

**Completion Criteria**:
- Lock prevents duplicate processing ✅
- Heartbeat extends TTL automatically ✅
- Tests pass with comprehensive coverage ✅

**Dependencies**: None (uses mock objects for testing)

**Status**: ✅ Completed (2025-01-13)

---

### 1.6 Budget Manager (`src/core/budget.py`)

**📖 Read First**: `docs/specs/02_retry.md` §4

- [ ] Implement `BudgetManager` class
  - [ ] `check_pro_budget() -> bool`
  - [ ] `increment_pro_usage() -> None`
  - [ ] `get_daily_usage() -> int`
  - [ ] `get_monthly_usage() -> int`
  - [ ] `reset_if_needed() -> None` (daily/monthly)
- [ ] Add Firestore backend
  - [ ] Collection: `budget`
  - [ ] Document: `{date, count}` for daily
  - [ ] Document: `{month, count}` for monthly
- [ ] Set timezone to `Asia/Tokyo`
- [ ] Add constants
  - [ ] `PRO_DAILY_LIMIT = 50`
  - [ ] `PRO_MONTHLY_LIMIT = 1000`
- [ ] Write unit tests
  - [ ] Test daily/monthly counting
  - [ ] Test reset logic
  - [ ] Test timezone handling (JST)
  - [ ] Test budget enforcement

**Completion Criteria**:
- Pro calls blocked when budget exceeded
- Resets correctly at JST midnight/month-start
- Tests pass

**Dependencies**: None

---

### 1.7 Test Infrastructure

- [ ] Set up pytest configuration
  - [ ] Add `pytest.ini` with coverage settings
  - [ ] Configure test discovery
- [ ] Create `tests/unit/` structure
- [ ] Create `tests/integration/` structure
- [ ] Add test fixtures
  - [ ] Sample schemas
  - [ ] Mock Firestore client
  - [ ] Mock GCS client
- [ ] Set up CI/CD pipeline
  - [ ] Add GitHub Actions workflow
  - [ ] Run tests on PR
  - [ ] Enforce coverage thresholds

**Completion Criteria**:
- `pytest tests/unit --cov=src/core --cov-fail-under=90` passes
- CI runs automatically on push

**Dependencies**: All 1.x tasks

---

## Phase 2: Core Pipeline (Week 3-4)

**Goal**: Implement Document AI and Gemini integration with self-correction

**Deliverables**: OCR extraction, Gemini prompts, model selection, retry logic

### 2.1 Document AI Integration (`src/core/docai.py`)

**📖 Read First**: `docs/specs/04_confidence.md` §1-2

- [ ] Implement `DocumentAIClient` class
  - [ ] `process_document(gcs_uri: str) -> DocumentAIResult`
  - [ ] `extract_markdown(result) -> str`
  - [ ] `calculate_confidence(result) -> float`
  - [ ] `detect_document_type(result) -> str | None`
- [ ] Create `DocumentAIResult` dataclass
  - [ ] `markdown: str`
  - [ ] `confidence: float`
  - [ ] `page_count: int`
  - [ ] `detected_type: str | None`
- [ ] Add fragile document type detection
  - [ ] `FRAGILE_TYPES = {"fax", "handwritten", "thermal_receipt", "carbon_copy"}`
- [ ] Write integration tests
  - [ ] Test with sample PDFs
  - [ ] Test confidence calculation
  - [ ] Test type detection

**Completion Criteria**:
- Can process PDF from GCS
- Returns structured markdown
- Confidence scores accurate

**Dependencies**: None (GCP credentials needed)

---

### 2.2 Gemini Prompts (`src/core/prompts.py`)

**📖 Read First**: `docs/specs/04_confidence.md` §4

- [ ] Define `MULTIMODAL_SYSTEM_PROMPT`
  - [ ] Vision/Markdown priority rules
  - [ ] Output JSON schema instructions
  - [ ] Confidence scoring guidelines
- [ ] Define `MARKDOWN_ONLY_PROMPT`
- [ ] Define `RETRY_PROMPT_TEMPLATE`
  - [ ] Include previous error message
  - [ ] Include linter feedback
- [ ] Add few-shot examples (3-5 golden examples)
- [ ] Write tests
  - [ ] Test prompt rendering
  - [ ] Test variable substitution

**Completion Criteria**:
- Prompts are complete and tested
- Few-shot examples included

**Dependencies**: 1.2 (schemas.py)

---

### 2.3 Image Attachment Logic (`src/core/extraction.py`)

**📖 Read First**: `docs/specs/04_confidence.md` §3

- [ ] Implement `should_attach_image()` function
  - [ ] Check confidence < 0.85
  - [ ] Check gate_failed flag
  - [ ] Check retry attempt > 0
  - [ ] Check doc_type in FRAGILE_TYPES
- [ ] Return tuple `(should_attach: bool, reason: str)`
- [ ] Add constants
  - [ ] `CONFIDENCE_THRESHOLD = 0.85`
- [ ] Write unit tests
  - [ ] Test each condition independently
  - [ ] Test combined conditions
  - [ ] Test edge cases (confidence = 0.85)

**Completion Criteria**:
- Logic matches decision table in spec
- All conditions tested
- Reason logging included

**Dependencies**: 2.1 (docai.py)

---

### 2.4 Model Selection Logic (`src/core/extraction.py`)

**📖 Read First**: `docs/specs/02_retry.md` §2-3

- [ ] Implement `classify_error()` function
  - [ ] Detect syntax errors (JSON parse, schema mismatch)
  - [ ] Detect semantic errors (Gate Linter failed)
  - [ ] Detect HTTP errors (429, 5xx)
- [ ] Implement `select_model()` function
  - [ ] Syntax error → Flash retry (max 2)
  - [ ] HTTP 429 → Flash retry (max 5, exponential backoff)
  - [ ] HTTP 5xx → Flash retry (max 3, fixed interval)
  - [ ] Semantic error → Pro escalation (if budget available)
  - [ ] Pro failure → Human review
- [ ] Add constants
  - [ ] `FLASH_SYNTAX_RETRIES = 2`
  - [ ] `FLASH_HTTP429_RETRIES = 5`
  - [ ] `FLASH_HTTP5XX_RETRIES = 3`
- [ ] Write unit tests
  - [ ] Test error classification
  - [ ] Test model selection for each error type
  - [ ] Test budget checks

**Completion Criteria**:
- Matches decision table in spec
- Budget enforcement working
- Tests cover all error types

**Dependencies**: 1.6 (budget.py)

---

### 2.5 Gemini API Client (`src/core/gemini.py`)

**📖 Read First**: `docs/specs/02_retry.md`

- [ ] Implement `GeminiClient` class
  - [ ] `call_flash(prompt: str, image: bytes | None) -> dict`
  - [ ] `call_pro(prompt: str, image: bytes | None) -> dict`
  - [ ] `parse_json_response(response: str) -> dict`
- [ ] Add retry logic with Tenacity
  - [ ] Exponential backoff for 429
  - [ ] Fixed retry for 5xx
- [ ] Add structured logging
  - [ ] Log model used
  - [ ] Log token count
  - [ ] Log cost estimate
- [ ] Write integration tests
  - [ ] Test Flash call
  - [ ] Test Pro call
  - [ ] Test retry behavior
  - [ ] Mock API responses

**Completion Criteria**:
- Can call both Flash and Pro
- Retry logic working
- Costs logged accurately

**Dependencies**: 2.2 (prompts.py), 1.6 (budget.py)

---

### 2.6 Self-Correction Loop (`src/core/extraction.py`)

**📖 Read First**: `docs/specs/02_retry.md` §5

- [ ] Implement `extract_with_retry()` function
  - [ ] Initial Flash attempt
  - [ ] Classify error on failure
  - [ ] Select model based on error type
  - [ ] Attach image if conditions met
  - [ ] Retry with updated prompt
  - [ ] Escalate to Pro if semantic error
  - [ ] Return FAILED status if all retries exhausted
- [ ] Add `ExtractionResult` dataclass
  - [ ] `schema: BaseDocumentSchema | None`
  - [ ] `status: Literal["SUCCESS", "FAILED"]`
  - [ ] `attempts: list[dict]` (audit trail)
  - [ ] `final_model: str`
- [ ] Write integration tests
  - [ ] Test successful first attempt
  - [ ] Test syntax error → Flash retry → success
  - [ ] Test semantic error → Pro escalation → success
  - [ ] Test exhausted retries → FAILED
- [ ] Add cost tracking
  - [ ] Log token usage per attempt
  - [ ] Calculate total cost

**Completion Criteria**:
- Self-correction loop working end-to-end
- All retry paths tested
- Audit trail complete

**Dependencies**: 2.3, 2.4, 2.5

---

### 2.7 Integration Testing

- [ ] Create end-to-end test pipeline
  - [ ] Mock GCS document upload
  - [ ] Call Document AI
  - [ ] Call Gemini with retry
  - [ ] Validate with linters
  - [ ] Assert final schema correct
- [ ] Test with real documents (3-5 samples)
- [ ] Measure success rate
- [ ] Measure average cost per document

**Completion Criteria**:
- ≥90% success rate on test documents
- Average cost < ¥2 per document

**Dependencies**: All 2.x tasks

---

## Phase 3: Escalation & Persistence (Week 5-6)

**Goal**: Add Pro escalation, Saga pattern, and database persistence

**Deliverables**: BigQuery integration, GCS file operations, Saga orchestrator

### 3.1 Saga Pattern (`src/core/saga.py`)

**📖 Read First**: `docs/specs/03_saga.md`

- [ ] Define `SagaStep` protocol
  - [ ] `execute() -> None`
  - [ ] `compensate() -> None`
- [ ] Implement `SagaOrchestrator` class
  - [ ] `add_step(step: SagaStep)`
  - [ ] `execute_all() -> bool`
  - [ ] `compensate_all() -> None` (reverse order)
- [ ] Create concrete steps
  - [ ] `UpdateDatabaseStep` (status → PROCESSING)
  - [ ] `CopyToDestinationStep` (GCS copy)
  - [ ] `DeleteSourceStep` (GCS delete)
  - [ ] `FinalizeStatusStep` (status → COMPLETED/FAILED)
- [ ] Write unit tests
  - [ ] Test successful execution
  - [ ] Test compensation on failure
  - [ ] Test partial execution rollback

**Completion Criteria**:
- Saga ensures atomicity
- Compensation works correctly
- No orphaned files

**Dependencies**: None

---

### 3.2 GCS Operations (`src/core/storage.py`)

**📖 Read First**: `docs/specs/03_saga.md` §3

- [ ] Implement `StorageClient` class
  - [ ] `copy_file(src_uri: str, dst_uri: str) -> None`
  - [ ] `delete_file(uri: str) -> None`
  - [ ] `generate_destination_path(schema, timestamp) -> str`
    - Format: `YYYYMM/管理ID_会社名_YYYYMMDD.pdf`
  - [ ] `file_exists(uri: str) -> bool`
- [ ] Add error handling
  - [ ] Retry on transient errors
  - [ ] Raise on permissions errors
- [ ] Write tests
  - [ ] Test copy operation
  - [ ] Test delete operation
  - [ ] Test path generation

**Completion Criteria**:
- File operations reliable
- Destination paths correct
- Tests pass

**Dependencies**: 1.2 (schemas.py for path generation)

---

### 3.3 Database Schema (Firestore/Cloud SQL)

**📖 Read First**: `docs/specs/07_monitoring.md` §2

- [ ] Design `documents` collection schema
  - [ ] `document_id: str` (SHA-256)
  - [ ] `status: str` (PENDING/PROCESSING/COMPLETED/FAILED)
  - [ ] `source_uri: str`
  - [ ] `destination_uri: str | None`
  - [ ] `extracted_data: dict` (JSON)
  - [ ] `attempts: list[dict]`
  - [ ] `created_at: datetime`
  - [ ] `updated_at: datetime`
  - [ ] `processed_at: datetime | None`
- [ ] Design `audit_log` collection
  - [ ] `document_id: str`
  - [ ] `event: str` (CREATED/EXTRACTED/CORRECTED/FAILED)
  - [ ] `details: dict`
  - [ ] `timestamp: datetime`
- [ ] Create indexes
  - [ ] `status + created_at` (for queue monitoring)
  - [ ] `document_id` (for lookups)
- [ ] Write migration script

**Completion Criteria**:
- Schema documented
- Indexes created
- Migration tested

**Dependencies**: None

---

### 3.4 Database Client (`src/core/database.py`)

- [ ] Implement `DatabaseClient` class
  - [ ] `create_document(doc_id, source_uri) -> None`
  - [ ] `update_status(doc_id, status) -> None`
  - [ ] `save_extraction(doc_id, schema, attempts) -> None`
  - [ ] `get_document(doc_id) -> dict | None`
  - [ ] `log_audit_event(doc_id, event, details) -> None`
- [ ] Add optimistic locking
  - [ ] Check `updated_at` before update
  - [ ] Raise conflict error if modified
- [ ] Write unit tests
  - [ ] Test CRUD operations
  - [ ] Test optimistic locking
  - [ ] Test audit logging

**Completion Criteria**:
- Database operations working
- Optimistic locking prevents conflicts
- Audit trail complete

**Dependencies**: 3.3 (database schema)

---

### 3.5 BigQuery Integration (`src/core/bigquery_client.py`)

**📖 Read First**: `docs/specs/07_monitoring.md` §3

- [ ] Design BigQuery table schema
  - [ ] `extraction_results` table
    - Partitioned by `document_date`
    - Clustered by `document_type`
  - [ ] `corrections` table
    - Append-only audit trail
- [ ] Implement `BigQueryClient` class
  - [ ] `insert_extraction(schema) -> None`
  - [ ] `insert_correction(before, after, user) -> None`
  - [ ] `query_by_date_range(start, end) -> list[dict]`
- [ ] Write tests
  - [ ] Test insertion
  - [ ] Test queries
  - [ ] Mock BigQuery client

**Completion Criteria**:
- Can insert and query data
- Partitioning/clustering working
- Tests pass

**Dependencies**: 1.2 (schemas.py)

---

### 3.6 Cloud Function Entry Point (`src/functions/processor/main.py`)

**📖 Read First**: All specs

- [ ] Implement `process_document(event, context)` function
  - [ ] Extract GCS URI from event
  - [ ] Acquire distributed lock
  - [ ] Check if already processed (idempotency)
  - [ ] Call Document AI
  - [ ] Call extraction with retry
  - [ ] Validate with Gate/Quality Linters
  - [ ] Execute Saga (copy + delete + update DB)
  - [ ] Insert into BigQuery
  - [ ] Release lock
  - [ ] Handle errors with structured logging
- [ ] Add timeout handling (540s max)
- [ ] Add heartbeat refresh in long operations
- [ ] Write integration tests
  - [ ] Test complete happy path
  - [ ] Test failure scenarios
  - [ ] Test timeout handling

**Completion Criteria**:
- Cloud Function deploys successfully
- End-to-end processing works
- Error handling robust

**Dependencies**: All Phase 1-3 tasks

---

### 3.7 Deployment Configuration

- [ ] Create `cloudbuild.yaml` for CI/CD
- [ ] Create Cloud Function deployment script
- [ ] Set up environment variables
  - [ ] GCP project ID
  - [ ] GCS buckets
  - [ ] API keys (in Secret Manager)
- [ ] Configure IAM permissions
  - [ ] Service account for Cloud Function
  - [ ] Minimal permissions (least privilege)
- [ ] Deploy to staging environment
- [ ] Run smoke tests

**Completion Criteria**:
- Deployment automated
- Staging environment working
- Smoke tests pass

**Dependencies**: 3.6

---

## Phase 4: Review UI (Week 7-8)

**Goal**: Build web interface for human review and correction

**Deliverables**: React frontend, FastAPI backend, approval workflow

### 4.1 FastAPI Backend Setup (`src/api/main.py`)

**📖 Read First**: `docs/specs/09_review_ui.md`

- [ ] Set up FastAPI project
  - [ ] Add dependencies: fastapi, uvicorn, pydantic
  - [ ] Configure CORS for React frontend
- [ ] Implement authentication
  - [ ] Google OAuth integration
  - [ ] Session management
- [ ] Add structured logging
- [ ] Write health check endpoint
- [ ] Deploy to Cloud Run
  - [ ] Configure IAP (Identity-Aware Proxy)
  - [ ] Set up custom domain

**Completion Criteria**:
- FastAPI app runs locally
- Authentication working
- Deployed to Cloud Run

**Dependencies**: None

---

### 4.2 API Endpoints - Document Listing

**📖 Read First**: `docs/specs/09_review_ui.md` §3

- [ ] `GET /api/documents` - List documents
  - [ ] Query params: status, date_range, page, limit
  - [ ] Return paginated results
  - [ ] Include extraction data and linter results
- [ ] Add filtering logic
  - [ ] By status (FAILED, COMPLETED, etc.)
  - [ ] By date range
  - [ ] By company name
- [ ] Add sorting
  - [ ] By created_at (default)
  - [ ] By confidence score
- [ ] Write tests
  - [ ] Test pagination
  - [ ] Test filtering
  - [ ] Test sorting

**Completion Criteria**:
- Endpoint returns correct data
- Pagination working
- Tests pass

**Dependencies**: 4.1, 3.4 (database.py)

---

### 4.3 API Endpoints - Document Details

- [ ] `GET /api/documents/{doc_id}` - Get document details
  - [ ] Return full extraction data
  - [ ] Return linter results (Gate + Quality)
  - [ ] Return audit log
  - [ ] Return source/destination URIs
- [ ] `GET /api/documents/{doc_id}/image` - Get document image
  - [ ] Stream PDF from GCS
  - [ ] Add authentication check
- [ ] Write tests
  - [ ] Test successful retrieval
  - [ ] Test 404 for missing documents
  - [ ] Test authentication

**Completion Criteria**:
- Can retrieve document details
- Image streaming working
- Tests pass

**Dependencies**: 4.1, 3.4

---

### 4.4 API Endpoints - Correction & Approval

**📖 Read First**: `docs/specs/09_review_ui.md` §4

- [ ] `PUT /api/documents/{doc_id}` - Update extraction
  - [ ] Accept corrected schema
  - [ ] Validate with Gate/Quality Linters
  - [ ] Check optimistic lock (updated_at)
  - [ ] Save to database
  - [ ] Log correction to audit trail
  - [ ] Update BigQuery
- [ ] `POST /api/documents/{doc_id}/approve` - Approve document
  - [ ] Mark as APPROVED
  - [ ] Trigger downstream processes
- [ ] Write tests
  - [ ] Test successful update
  - [ ] Test validation errors
  - [ ] Test optimistic locking
  - [ ] Test approval workflow

**Completion Criteria**:
- Corrections saved correctly
- Audit trail complete
- Tests pass

**Dependencies**: 4.1, 3.4, 3.5

---

### 4.5 Auto-save Implementation

**📖 Read First**: `docs/specs/10_autosave.md`

- [ ] `POST /api/documents/{doc_id}/draft` - Save draft
  - [ ] Accept partial schema
  - [ ] Save to Firestore `drafts` collection
  - [ ] Don't validate (draft may be incomplete)
- [ ] `GET /api/documents/{doc_id}/draft` - Get draft
  - [ ] Return saved draft or null
- [ ] `DELETE /api/documents/{doc_id}/draft` - Delete draft
  - [ ] Called after approval
- [ ] Add timestamp tracking
  - [ ] `created_at`, `updated_at`
- [ ] Write tests
  - [ ] Test save/retrieve/delete
  - [ ] Test multiple drafts per user

**Completion Criteria**:
- Draft persistence working
- No validation on save
- Tests pass

**Dependencies**: 4.1

---

### 4.6 React Frontend Setup (`src/ui/`)

**📖 Read First**: `docs/specs/09_review_ui.md`

- [ ] Initialize Vite + React + TypeScript project
- [ ] Add dependencies
  - [ ] React Router
  - [ ] Tailwind CSS
  - [ ] shadcn/ui components
  - [ ] React Query (data fetching)
  - [ ] Axios (HTTP client)
- [ ] Set up project structure
  - [ ] `src/components/`
  - [ ] `src/pages/`
  - [ ] `src/hooks/`
  - [ ] `src/api/`
- [ ] Configure Tailwind CSS
- [ ] Add shadcn/ui base components
- [ ] Set up routing
- [ ] Configure API client with authentication

**Completion Criteria**:
- Vite dev server runs
- Routing working
- Tailwind CSS configured

**Dependencies**: None

---

### 4.7 Document List Page

**📖 Read First**: `docs/specs/09_review_ui.md` §5

- [ ] Create `DocumentListPage` component
  - [ ] Fetch documents from API
  - [ ] Display in table (shadcn/ui Table)
  - [ ] Show status badges
  - [ ] Show confidence scores
  - [ ] Add pagination controls
- [ ] Add filters
  - [ ] Status dropdown
  - [ ] Date range picker
  - [ ] Company name search
- [ ] Add sorting
  - [ ] Click column headers to sort
- [ ] Handle loading/error states
- [ ] Write tests (Vitest + Testing Library)

**Completion Criteria**:
- List displays correctly
- Filters working
- Tests pass (≥70% coverage)

**Dependencies**: 4.6, 4.2 (API endpoint)

---

### 4.8 Document Editor Page

**📖 Read First**: `docs/specs/09_review_ui.md` §6, `docs/specs/10_autosave.md`

- [ ] Create `DocumentEditorPage` component
  - [ ] Display document image (PDF viewer)
  - [ ] Display extraction results in form
  - [ ] Show Gate/Quality Linter errors
  - [ ] Allow field editing
- [ ] Add form validation
  - [ ] Client-side validation (Zod schema)
  - [ ] Real-time linter feedback
- [ ] Implement auto-save
  - [ ] Save draft every 30 seconds
  - [ ] Save to localStorage (immediate)
  - [ ] Save to server (async backup)
  - [ ] Show "Saved" indicator
- [ ] Add restore prompt
  - [ ] Check for draft on page load
  - [ ] Prompt user to restore
- [ ] Add approval button
  - [ ] Validate before approval
  - [ ] Confirm with dialog
- [ ] Write tests

**Completion Criteria**:
- Editor functional
- Auto-save working
- Draft restore working
- Tests pass

**Dependencies**: 4.6, 4.3, 4.4, 4.5

---

### 4.9 Conflict Detection

**📖 Read First**: `docs/specs/11_conflict.md`

- [ ] Implement optimistic locking UI
  - [ ] Store `updated_at` from initial load
  - [ ] Send `updated_at` with PUT request
  - [ ] Handle 409 Conflict response
- [ ] Add conflict resolution dialog
  - [ ] Show "Document modified by another user"
  - [ ] Offer options: Reload | Force Save
  - [ ] Show diff of changes (optional)
- [ ] Write tests
  - [ ] Simulate conflict scenario
  - [ ] Test reload behavior
  - [ ] Test force save (if implemented)

**Completion Criteria**:
- Conflicts detected
- User notified clearly
- No data loss

**Dependencies**: 4.8

---

### 4.10 UI Testing & Polish

- [ ] Add loading skeletons
- [ ] Add error boundaries
- [ ] Improve accessibility (ARIA labels, keyboard nav)
- [ ] Test on mobile (responsive design)
- [ ] Add dark mode support (optional)
- [ ] Write E2E tests (Playwright)
  - [ ] Login flow
  - [ ] List → Edit → Save flow
  - [ ] Filter and search
- [ ] Optimize bundle size
- [ ] Deploy to Cloud Run (static hosting)

**Completion Criteria**:
- UI polished and accessible
- E2E tests pass
- Deployed to production

**Dependencies**: All 4.x tasks

---

## Phase 5: Hardening (Week 9-10)

**Goal**: Production readiness - monitoring, security, performance

**Deliverables**: Monitoring dashboard, alerting, security audit, load testing

### 5.1 Structured Logging

**📖 Read First**: `docs/specs/07_monitoring.md` §1

- [ ] Set up `structlog` across all modules
- [ ] Define log levels
  - [ ] DEBUG: Detailed diagnostics
  - [ ] INFO: Normal operations
  - [ ] WARNING: Recoverable issues
  - [ ] ERROR: Failures requiring attention
  - [ ] CRITICAL: System-wide failures
- [ ] Add context processors
  - [ ] Request ID
  - [ ] Document ID
  - [ ] User ID (for UI)
  - [ ] Timestamp (UTC)
- [ ] Configure Cloud Logging integration
- [ ] Add sensitive data masking
  - [ ] Mask `management_id` in logs
  - [ ] Mask amounts
  - [ ] Mask company names (optional)
- [ ] Write log analysis queries

**Completion Criteria**:
- All modules use structlog
- Sensitive data masked
- Logs queryable in Cloud Logging

**Dependencies**: None

---

### 5.2 Monitoring Dashboard

**📖 Read First**: `docs/specs/07_monitoring.md` §2, `config/alerts.yaml`

- [ ] Create Cloud Monitoring dashboard
  - [ ] Processing rate (docs/hour)
  - [ ] Success rate (%)
  - [ ] Average processing time
  - [ ] Flash vs Pro usage
  - [ ] Pro budget consumption
  - [ ] Queue backlog size
  - [ ] Error rate by type
- [ ] Add custom metrics
  - [ ] Extraction confidence scores
  - [ ] Linter failure rate
  - [ ] Cost per document
- [ ] Set up log-based metrics
  - [ ] Extract from structured logs
- [ ] Create uptime checks
  - [ ] Review UI health endpoint
  - [ ] API availability

**Completion Criteria**:
- Dashboard displays all key metrics
- Metrics update in real-time
- Uptime checks configured

**Dependencies**: 5.1

---

### 5.3 Alerting System

**📖 Read First**: `docs/specs/12_alerting.md`, `config/alerts.yaml`

- [ ] Configure Cloud Monitoring alerts
  - [ ] P0: Queue backlog >100 docs
  - [ ] P0: Failure rate >5% in 1 hour
  - [ ] P1: Pro budget >80% (daily)
  - [ ] P2: Average confidence <0.7
- [ ] Set up notification channels
  - [ ] Slack integration
  - [ ] PagerDuty (for P0 only)
  - [ ] Email (for P1/P2)
- [ ] Create Dead Letter Queue
  - [ ] GCS bucket for permanently failed docs
  - [ ] Alert when document moved to DLQ
- [ ] Add health check endpoint
  - [ ] Check every 15 minutes
  - [ ] Alert if unhealthy >3 checks
- [ ] Write runbook for each alert
  - [ ] Investigation steps
  - [ ] Resolution procedures

**Completion Criteria**:
- All alerts configured
- Notifications working
- Runbooks documented

**Dependencies**: 5.2

---

### 5.4 Security Audit

**📖 Read First**: `docs/specs/08_security.md`

- [ ] Review IAM permissions
  - [ ] Service accounts follow least privilege
  - [ ] Remove unnecessary roles
  - [ ] Document all permissions
- [ ] Enable Customer-Managed Encryption (CMEK)
  - [ ] Create Cloud KMS keyring
  - [ ] Encrypt GCS buckets
  - [ ] Encrypt Firestore
  - [ ] Encrypt BigQuery datasets
- [ ] Configure Identity-Aware Proxy (IAP)
  - [ ] Protect Review UI
  - [ ] Configure allowed users/groups
  - [ ] Test access control
- [ ] Run security scan
  - [ ] `bandit -r src/ -ll` (Python)
  - [ ] Check for hardcoded secrets
  - [ ] Validate HTTPS everywhere
- [ ] Enable audit logging
  - [ ] Admin activity logs
  - [ ] Data access logs (for corrections)
- [ ] Create security documentation
  - [ ] Threat model
  - [ ] Incident response plan

**Completion Criteria**:
- Security scan passes
- CMEK enabled
- IAP protecting UI
- Documentation complete

**Dependencies**: None

---

### 5.5 Performance Testing

- [ ] Create load testing script
  - [ ] Simulate 100 docs/hour upload rate
  - [ ] Measure processing time
  - [ ] Measure cost per document
- [ ] Run load test in staging
- [ ] Identify bottlenecks
  - [ ] Document AI latency
  - [ ] Gemini API latency
  - [ ] Database write latency
- [ ] Optimize if needed
  - [ ] Increase Cloud Function concurrency
  - [ ] Optimize database queries
  - [ ] Cache frequent lookups
- [ ] Document performance characteristics
  - [ ] Max throughput
  - [ ] Average latency
  - [ ] Cost at scale

**Completion Criteria**:
- Can handle 100 docs/hour
- <5 min average processing time
- Cost < ¥2 per document

**Dependencies**: All previous tasks

---

### 5.6 Documentation

- [ ] Update `README.md` with deployment instructions
- [ ] Create operations manual
  - [ ] How to deploy
  - [ ] How to monitor
  - [ ] How to troubleshoot
- [ ] Document API endpoints (OpenAPI spec)
- [ ] Create user guide for Review UI
- [ ] Add architecture diagrams
  - [ ] System flow
  - [ ] Data flow
  - [ ] Deployment architecture
- [ ] Write disaster recovery plan
  - [ ] Backup procedures
  - [ ] Restore procedures
  - [ ] RPO/RTO targets

**Completion Criteria**:
- All documentation complete
- Ops team can deploy independently

**Dependencies**: None

---

### 5.7 Production Deployment

- [ ] Create production GCP project
- [ ] Deploy all infrastructure
  - [ ] Terraform scripts (optional)
  - [ ] Cloud Function
  - [ ] Cloud Run (API + UI)
  - [ ] Databases (Firestore, BigQuery)
  - [ ] Storage buckets
  - [ ] Monitoring & Alerting
- [ ] Run smoke tests in production
- [ ] Monitor for 24 hours
- [ ] Perform manual acceptance testing
  - [ ] Process 5-10 real documents
  - [ ] Verify file organization
  - [ ] Test Review UI corrections
  - [ ] Confirm alerts fire correctly
- [ ] Hand off to operations team

**Completion Criteria**:
- Production system live
- All smoke tests pass
- Team trained and ready

**Dependencies**: All Phase 5 tasks

---

## Risk Management

### High-Risk Items

| Risk | Impact | Mitigation | Status |
|------|--------|------------|--------|
| Gemini API quota exceeded | Pipeline stalls | Monitor Pro budget, implement queuing | ⏳ Pending |
| Document AI accuracy <85% | Manual review overhead | Test with real docs early, tune prompts | ⏳ Pending |
| Lock contention under load | Processing delays | Optimize lock TTL, add monitoring | ⏳ Pending |
| Schema migration breaks old data | Data loss | Test migrations thoroughly, maintain backward compat | ⏳ Pending |
| IAP misconfiguration | Security breach | Security audit, access control tests | ⏳ Pending |

---

## Assumptions & Dependencies

### External Dependencies
- Google Cloud Platform account with billing enabled
- Document AI API enabled
- Gemini API access (Vertex AI)
- GitHub repository access
- Slack workspace (for alerts)
- PagerDuty account (optional, for P0 alerts)

### Technical Prerequisites
- Python 3.11+
- Node.js 18+ (for UI)
- Terraform (optional, for IaC)
- `gcloud` CLI configured

### Team Skills Required
- Python backend development
- React/TypeScript frontend development
- GCP services (Cloud Functions, Firestore, BigQuery)
- API design (REST, FastAPI)
- CI/CD (GitHub Actions, Cloud Build)

---

## Daily Checklist

Before starting work:
- [ ] Run `git pull` to sync latest changes
- [ ] Check if any dependencies updated
- [ ] Review today's tasks in this plan
- [ ] Update TODO status (mark in-progress)

After completing work:
- [ ] Update TODO checkboxes in this file
- [ ] Run tests: `pytest tests/ --cov=src`
- [ ] Run linters: `ruff check . && black . && mypy src/`
- [ ] Commit changes with descriptive message
- [ ] Push to GitHub
- [ ] Update Serena memory checkpoint

---

## How to Use This Plan

1. **Session Start**: Read relevant spec docs (📖 Read First links)
2. **Implementation**: Follow task checklist, mark items as you complete
3. **Testing**: Write tests BEFORE marking task complete
4. **Documentation**: Update this plan with any deviations or learnings
5. **Checkpointing**: Save progress to Serena memory every 30 minutes

**Commit Message Format**:
```
feat(core): implement distributed lock with heartbeat

Complete task 1.5 from implementation plan.
- Add Firestore-backed locking
- Implement heartbeat refresh thread
- Add unit tests with emulator

Refs: docs/specs/01_idempotency.md
Progress: Phase 1 - 5/15 tasks complete
```

---

## Session Recovery

If Claude Code session is interrupted:

1. Read this file to see current progress
2. Run: `/sc:load` to restore Serena memory
3. Check git status for uncommitted work
4. Review last completed task checkpoint
5. Continue from next unchecked task

**Memory Keys**:
- `plan_phase`: Current phase number
- `plan_task`: Current task ID (e.g., "1.5")
- `plan_checkpoint`: Last completed milestone
- `plan_blockers`: Any active impediments

---

**Last Session**: 2025-01-13 15:30 JST
**Current Phase**: Phase 1 (Foundation)
**Current Task**: 1.6 (Budget Manager)
**Completed**:
- 1.1 (Project Setup) ✅
- 1.2 (Schema Registry) ✅
- 1.3 (Gate Linter) ✅
- 1.4 (Quality Linter) ✅
- 1.5 (Distributed Lock) ✅
**Next Milestone**: Complete Budget Manager for Pro API limits (1.6)
