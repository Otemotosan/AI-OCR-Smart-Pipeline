# AI-OCR Smart Pipeline

**Version**: 2.1.0
**Status**: 🚧 In Development (Phase 1: Foundation)
**Last Updated**: 2025-01-13

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

**Current Phase**: Phase 1 (Foundation) - 1/7 tasks complete (14%)

| Phase | Status | Progress | Duration |
|-------|--------|----------|----------|
| Phase 1: Foundation | 🔄 In Progress | 1/7 | Week 1-2 |
| Phase 2: Core Pipeline | ⏳ Pending | 0/7 | Week 3-4 |
| Phase 3: Escalation | ⏳ Pending | 0/7 | Week 5-6 |
| Phase 4: Review UI | ⏳ Pending | 0/10 | Week 7-8 |
| Phase 5: Hardening | ⏳ Pending | 0/7 | Week 9-10 |

**Total Progress**: 1/38 tasks (3%)

**Completed**:
- ✅ Task 1.1: Project Setup
- ✅ Task 1.2: Schema Registry (in progress)

**Next**:
- 🔄 Task 1.3: Gate Linter
- ⏳ Task 1.4: Quality Linter
- ⏳ Task 1.5: Distributed Lock

See [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) for detailed task breakdown.

---

## Documentation

### Core Documentation
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System design and key decisions
- **[IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)** - 38 detailed tasks with checkboxes
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

## License

Proprietary - All rights reserved

---

## Support

- **Issues**: [GitHub Issues](https://github.com/Otemotosan/AI-OCR-Smart-Pipeline/issues)
- **Documentation**: [`docs/`](docs/) directory
- **Claude Code**: See [`CLAUDE.md`](CLAUDE.md) for AI pair programming instructions

---

**Built with ❤️ using Claude Code**
