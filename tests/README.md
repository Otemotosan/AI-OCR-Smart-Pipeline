# Test Infrastructure

## Directory Structure

```
tests/
├── conftest.py           # Shared pytest fixtures and configuration
├── unit/                 # Unit tests (fast, isolated, no external dependencies)
│   ├── test_schemas.py
│   ├── test_gate_linter.py
│   ├── test_quality_linter.py
│   ├── test_lock.py
│   └── test_budget.py
└── integration/          # Integration tests (require external services)
    └── __init__.py
```

## Running Tests

### All Unit Tests
```bash
pytest tests/unit -v
```

### With Coverage
```bash
pytest tests/unit --cov=src/core --cov-report=term-missing --cov-fail-under=90
```

### Specific Test File
```bash
pytest tests/unit/test_schemas.py -v
```

### Integration Tests (requires emulators)
```bash
pytest tests/integration -m integration -v
```

## Shared Fixtures

The `conftest.py` provides common fixtures for all tests:

### Mock Clients
- `mock_firestore_client` - Mock Firestore client with collection/document chains
- `mock_gcs_client` - Mock GCS client with bucket/blob chains

### Sample Data
- `sample_delivery_note_v2` - Valid delivery note data
- `sample_invoice_v1` - Valid invoice data  
- `sample_markdown_output` - Document AI markdown output
- `sample_gemini_response` - Gemini JSON response

### Test Helpers
- `create_mock_snapshot` - Factory for creating mock Firestore snapshots

## Coverage Standards

- **Unit Tests**: ≥90% coverage required for `src/core/`
- **Integration Tests**: Focus on end-to-end workflows, not coverage metrics

## CI/CD

Tests run automatically on:
- Every push to `main` branch
- Every pull request
- Multiple Python versions (3.11, 3.12)

See `.github/workflows/ci.yml` for CI configuration.

## Current Status

**Unit Test Coverage**: 87.60% (Target: 90%)

Areas needing improvement:
- `lock.py`: 47% coverage - needs Firestore transaction mocking refactoring
- Full integration test suite pending (Phase 2)

## Adding New Tests

1. Create test file in `tests/unit/test_<module>.py`
2. Use fixtures from `conftest.py`
3. Follow naming convention: `test_<description>`
4. Group related tests in classes: `class TestFeatureName:`
5. Add docstrings explaining what each test validates
