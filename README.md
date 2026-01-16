# AI-OCR Smart Pipeline

**Version**: 2.2.0
**Status**: 🚧 In Development (Phase 5: Hardening)
**Last Updated**: 2025-01-16

---

## Overview

Serverless AI-native pipeline that automates classification, renaming, and filing of non-standard business documents (delivery notes, invoices). Extracts Management ID, Company Name, and Date, organizes files into structured folders, and builds a queryable database.

### Key Features

- **AI-Powered Extraction**: Gemini 2.0 Flash + Pro escalation
- **Smart Retry Logic**: Syntax → Flash retry, Semantic → Pro escalation
- **Conditional Vision**: Attaches images only when confidence < 0.85
- **Two-Tier Validation**: Gate (immutable) + Quality (configurable) linters
- **Schema Versioning**: Automatic migration with defaulted field tracking
- **Review UI**: React + FastAPI for human review and corrections
- **Cost Efficient**: ~¥170/month for 100 documents

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| OCR | Document AI (Layout Parser) |
| Reasoning | Gemini 2.0 Flash / 1.5 Pro |
| Validation | Pydantic v2 + Custom Linters |
| Storage | Cloud Storage + Firestore + BigQuery |
| Backend | Python 3.11 + FastAPI |
| Frontend | React + Vite + Tailwind + shadcn/ui |
| Deployment | Cloud Functions 2nd Gen + Cloud Run |

---

## Project Structure

```
AI-OCR-Smart-Pipeline/
├── src/
│   ├── core/                 # Business logic
│   │   ├── schemas.py        # ✅ Pydantic models + registry
│   │   ├── linters/
│   │   │   ├── gate.py       # Immutable validation
│   │   │   └── quality.py    # Configurable validation
│   │   ├── prompts.py        # Gemini prompts
│   │   ├── extraction.py     # Model selection + image logic
│   │   ├── lock.py           # Distributed lock
│   │   ├── budget.py         # Pro API budget
│   │   └── saga.py           # File operation saga
│   ├── functions/            # Cloud Function entry
│   ├── api/                  # FastAPI backend
│   └── ui/                   # React frontend
├── tests/
│   ├── unit/                 # ✅ Unit tests (≥90% coverage)
│   └── integration/          # Integration tests
├── docs/
│   ├── ARCHITECTURE.md       # System design
│   ├── IMPLEMENTATION_PLAN.md # ✅ Detailed task breakdown
│   └── specs/                # 12 detailed specifications
├── config/                   # YAML configurations
├── ci/                       # CI/CD pipelines
├── pyproject.toml            # ✅ Project config + dependencies
└── README.md                 # This file
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Google Cloud Platform account
- Document AI API enabled
- Gemini API access (Vertex AI)

### Installation

```bash
# Clone repository
git clone https://github.com/Otemotosan/AI-OCR-Smart-Pipeline.git
cd AI-OCR-Smart-Pipeline

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Verify installation
pytest --version
mypy --version
ruff --version
```

### Running Tests

```bash
# Run all unit tests
pytest tests/unit -v

# Run with coverage
pytest tests/unit --cov=src/core --cov-report=html

# Type checking
mypy src/core --strict

# Linting
ruff check src tests
black src tests --check
```

### Code Quality Standards

All code must pass:
- **Ruff**: Linting (complexity ≤10, security checks)
- **Black**: Formatting (line length 100)
- **MyPy**: Strict type checking
- **Pytest**: ≥90% coverage for `src/core/`, ≥80% for `src/api/`, ≥70% for `src/ui/`

---

## Implementation Progress

**Current Phase**: Phase 5 (Hardening) - 6/7 tasks complete (86%)

| Phase | Status | Progress | Duration |
|-------|--------|----------|----------|
| Phase 1: Foundation | ✅ Complete | 7/7 | Week 1-2 |
| Phase 2: Core Pipeline | ✅ Complete | 7/7 | Week 3-4 |
| Phase 3: Integration | ✅ Complete | 7/7 | Week 5-6 |
| Phase 4: Review UI | ✅ Complete | 10/10 | Week 7-8 |
| Phase 5: Hardening | 🔄 In Progress | 6/7 | Week 9-10 |

**Total Progress**: 37/38 tasks (97%)

**Phase 5 Progress**:
- ✅ Task 5.1: Structured Logging
- ✅ Task 5.2: Monitoring Dashboard (Metrics Module)
- ✅ Task 5.3: Alerting System
- ✅ Task 5.4: Security Audit
- ✅ Task 5.5: Performance Testing
- ✅ Task 5.6: Documentation
- 🔄 Task 5.7: Production Deployment

See [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) for detailed task breakdown.

---

## Documentation

### Core Documentation
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System design and key decisions
- **[IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)** - 38 detailed tasks with checkboxes
- **[OPERATIONS.md](docs/OPERATIONS.md)** - Deployment, monitoring, troubleshooting guide
- **[USER_GUIDE.md](docs/USER_GUIDE.md)** - Review UI user manual
- **[CLAUDE.md](CLAUDE.md)** - Instructions for Claude Code

### Specifications (12 documents)
1. **[Idempotency](docs/specs/01_idempotency.md)** - SHA-256 hashing, Firestore locks
2. **[Retry Logic](docs/specs/02_retry.md)** - Error classification, model selection
3. **[Saga Pattern](docs/specs/03_saga.md)** - File operation atomicity
4. **[Confidence](docs/specs/04_confidence.md)** - Image attachment logic
5. **[Schema](docs/specs/05_schema.md)** - Registry design, versioning
6. **[Linters](docs/specs/06_linters.md)** - Gate/Quality separation
7. **[Monitoring](docs/specs/07_monitoring.md)** - Metrics, alerts, logging
8. **[Security](docs/specs/08_security.md)** - IAM, CMEK, audit logs
9. **[Review UI](docs/specs/09_review_ui.md)** - React/FastAPI architecture
10. **[Auto-save](docs/specs/10_autosave.md)** - Draft recovery
11. **[Conflict Detection](docs/specs/11_conflict.md)** - Optimistic locking
12. **[Alerting](docs/specs/12_alerting.md)** - Dead letter queue, health checks

---

## Development Workflow

### Session Start
```bash
# 1. Load context
cat docs/IMPLEMENTATION_PLAN.md | grep -A 5 "Progress Overview"
git log --oneline -5

# 2. Identify next task
# → Check first unchecked task in IMPLEMENTATION_PLAN.md

# 3. Read spec (if applicable)
# → Follow "📖 Read First" links

# 4. Start implementation
pytest tests/unit --cov=src/core -v
```

### Before Commit
```bash
# Run quality checks
ruff check . --fix
black .
mypy src/ --strict

# Run tests
pytest tests/unit --cov=src/core --cov-fail-under=90

# Commit with progress
git add .
git commit -m "feat(core): complete task X.Y

<description>

Progress: Phase X - Y/Z tasks complete"
```

---

## Key Design Decisions

### 1. Model Selection Strategy
- **Default**: Gemini Flash (cost-efficient)
- **Escalate to Pro**: Only on semantic errors (Gate Linter failed)
- **Never escalate**: Syntax/HTTP errors → retry Flash instead

### 2. Image Attachment Logic
- **Default**: Markdown only (2K tokens)
- **Attach image**: Low confidence OR failure OR retry (10K tokens)
- **Trigger conditions**: confidence < 0.85, Gate failed, retry > 0, fragile doc type

### 3. Two-Tier Linter
- **Gate Linter**: Immutable rules, failure → blocks persistence
- **Quality Linter**: Configurable rules (YAML), failure → warning only

### 4. Schema Versioning
- Every record carries schema version
- Migration metadata tracks defaulted fields
- Read-time transformation for historical data
- Deprecated versions blocked for new documents

---

## Cost Breakdown (100 docs/month)

| Service | Monthly Cost (JPY) |
|---------|-------------------|
| Document AI | ¥150 |
| Gemini API | ¥17 |
| Cloud Functions | ¥0 (free tier) |
| Cloud Storage | ¥2 |
| Firestore | ¥2 |
| BigQuery | ¥0 (free tier) |
| Cloud Run | ¥2 |
| **Total** | **~¥170** |

**7-year projection**: ~¥15,000 (well under ¥252,000 budget)

---

## Contributing

### Code Standards
- Use `from __future__ import annotations` for type hints
- Function complexity ≤ 10 (mccabe)
- Docstrings required for public functions
- Type hints mandatory
- No `print()` — use `structlog` instead

### Commit Message Format
```
<type>(<scope>): <subject>

<body>

Progress: Phase X - Y/Z tasks complete

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

**Types**: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
**Scopes**: `core`, `api`, `ui`, `ci`, `config`

---

## Deployment

### Prerequisites

1. **GCP Project** with billing enabled
2. **APIs Enabled**:
   - Document AI API
   - Vertex AI API (Gemini)
   - Cloud Functions API
   - Cloud Run API
   - Cloud Storage API
   - Firestore API
   - BigQuery API
   - Cloud Monitoring API
   - Cloud Logging API

### Quick Deployment

```bash
# 1. Set environment variables
export GCP_PROJECT_ID=your-project-id
export GCP_REGION=asia-northeast1

# 2. Authenticate
gcloud auth login
gcloud config set project $GCP_PROJECT_ID

# 3. Deploy infrastructure
cd deploy
./deploy.sh

# 4. Verify deployment
gcloud functions describe ocr-processor --region=$GCP_REGION
```

### Manual Deployment Steps

1. **Create GCS Buckets**
   ```bash
   gsutil mb -l $GCP_REGION gs://${GCP_PROJECT_ID}-input
   gsutil mb -l $GCP_REGION gs://${GCP_PROJECT_ID}-output
   gsutil mb -l $GCP_REGION gs://${GCP_PROJECT_ID}-quarantine
   ```

2. **Deploy Cloud Function**
   ```bash
   gcloud functions deploy ocr-processor \
     --gen2 \
     --runtime python311 \
     --region $GCP_REGION \
     --memory 1024MB \
     --timeout 540s \
     --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
     --trigger-event-filters="bucket=${GCP_PROJECT_ID}-input"
   ```

3. **Deploy Review UI**
   ```bash
   gcloud run deploy review-ui \
     --source src/api \
     --region $GCP_REGION \
     --allow-unauthenticated
   ```

See [`docs/OPERATIONS.md`](docs/OPERATIONS.md) for detailed deployment and operations guide.

---

## License

Proprietary - All rights reserved

---

## Support

- **Issues**: [GitHub Issues](https://github.com/Otemotosan/AI-OCR-Smart-Pipeline/issues)
- **Documentation**: [`docs/`](docs/) directory
- **Claude Code**: See [`CLAUDE.md`](CLAUDE.md) for AI pair programming instructions

---

**Built with ❤️ using Claude Code**
