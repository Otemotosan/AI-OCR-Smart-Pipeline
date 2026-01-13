# Validation Layer: Gate & Quality Linters

**Spec ID**: 06  
**Status**: Final  
**Dependencies**: Pydantic, Cloud SQL (for vendor master)

---

## 1. Design Philosophy

**Two-Tier Validation**

| Linter | Purpose | Mutability | On Failure |
|--------|---------|------------|------------|
| **Gate** | Physical world consistency | Immutable | Block persistence |
| **Quality** | Business judgment | Configurable | Warning only |

Gate Linter is the "Gatekeeper" — if it fails, the document cannot be filed.
Quality Linter is the "Advisor" — it flags issues but doesn't block.

---

## 2. Gate Linter (Invariants)

### 2.1 Scope

Rules that affect **physical operations**:
- File naming (`{ID}_{Company}_{Date}.pdf`)
- Folder routing (`/delivery_note/2025/01/`)
- Database insertion (primary keys)

If these are wrong, the system creates garbage.

### 2.2 Rules

| Rule | Field | Condition | Error Message |
|------|-------|-----------|---------------|
| G1 | `management_id` | Non-empty | "Required field is empty" |
| G2 | `management_id` | Format valid | "Invalid format (expected 6-20 alphanumeric)" |
| G3 | `company_name` | Non-empty | "Required field is empty" |
| G4 | `issue_date` | Valid date | "Invalid date format" |
| G5 | `issue_date` | Not future | "Future date not allowed" |
| G6 | `document_type` | In registry | "Unknown document type" |

### 2.3 Implementation

```python
# core/linters/gate.py
from dataclasses import dataclass
from datetime import date, datetime
from typing import List
import re

@dataclass
class GateLinterResult:
    """Result of Gate Linter validation."""
    passed: bool
    errors: List[str]

class GateLinter:
    """
    Immutable validation rules affecting physical operations.
    
    These rules are hardcoded — they define system invariants.
    Pure functions only — no side effects.
    """
    
    # Management ID pattern: 6-20 alphanumeric with hyphens/underscores
    ID_PATTERN = re.compile(r'^[A-Za-z0-9\-_]{6,20}$')
    
    @classmethod
    def validate(cls, data: dict) -> GateLinterResult:
        """
        Validate data against all Gate rules.
        
        Args:
            data: Extracted document data
            
        Returns:
            GateLinterResult with pass/fail and error list
        """
        errors = []
        
        # G1: management_id required
        management_id = data.get("management_id", "")
        if not management_id or not str(management_id).strip():
            errors.append("management_id: Required field is empty")
        
        # G2: management_id format
        elif not cls.ID_PATTERN.match(str(management_id)):
            errors.append(
                f"management_id: Invalid format '{management_id}' "
                f"(expected 6-20 alphanumeric characters, hyphens, underscores)"
            )
        
        # G3: company_name required
        company_name = data.get("company_name", "")
        if not company_name or not str(company_name).strip():
            errors.append("company_name: Required field is empty")
        
        # G4 & G5: issue_date validation
        issue_date = data.get("issue_date")
        if not issue_date:
            errors.append("issue_date: Required field is missing")
        else:
            parsed_date = cls._parse_date(issue_date)
            if parsed_date is None:
                errors.append(f"issue_date: Invalid date format '{issue_date}'")
            elif parsed_date > date.today():
                errors.append(
                    f"issue_date: Future date not allowed ({parsed_date})"
                )
        
        # G6: document_type in registry
        document_type = data.get("document_type", "")
        if document_type and document_type not in SCHEMA_REGISTRY:
            available = list(SCHEMA_REGISTRY.keys())
            errors.append(
                f"document_type: Unknown type '{document_type}'. "
                f"Valid types: {available}"
            )
        
        return GateLinterResult(
            passed=len(errors) == 0,
            errors=errors
        )
    
    @staticmethod
    def _parse_date(value) -> date | None:
        """Parse various date formats."""
        if isinstance(value, date):
            return value
        
        if isinstance(value, datetime):
            return value.date()
        
        if isinstance(value, str):
            # Try ISO format first
            for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"]:
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
        
        return None
```

### 2.4 Unit Tests

```python
# tests/unit/test_gate_linter.py
import pytest
from core.linters.gate import GateLinter

class TestGateLinter:
    
    def test_valid_document_passes(self):
        data = {
            "management_id": "INV-2025-001",
            "company_name": "株式会社山田商事",
            "issue_date": "2025-01-09",
            "document_type": "delivery_note"
        }
        result = GateLinter.validate(data)
        assert result.passed is True
        assert len(result.errors) == 0
    
    def test_empty_management_id_fails(self):
        data = {
            "management_id": "",
            "company_name": "Test",
            "issue_date": "2025-01-09",
            "document_type": "delivery_note"
        }
        result = GateLinter.validate(data)
        assert result.passed is False
        assert any("management_id" in e for e in result.errors)
    
    @pytest.mark.parametrize("invalid_id", [
        "AB",           # Too short
        "A" * 25,       # Too long
        "INV 001",      # Contains space
        "INV@001",      # Invalid character
        "日本語ID",      # Non-ASCII
    ])
    def test_invalid_id_formats(self, invalid_id):
        data = {
            "management_id": invalid_id,
            "company_name": "Test",
            "issue_date": "2025-01-09",
            "document_type": "delivery_note"
        }
        result = GateLinter.validate(data)
        assert result.passed is False
    
    def test_future_date_fails(self):
        data = {
            "management_id": "INV-2025-001",
            "company_name": "Test",
            "issue_date": "2099-12-31",
            "document_type": "delivery_note"
        }
        result = GateLinter.validate(data)
        assert result.passed is False
        assert any("future" in e.lower() for e in result.errors)
```

---

## 3. Quality Linter (Variables)

### 3.1 Scope

Rules that affect **business judgment**:
- Amount reasonableness
- Date sequence logic
- Master data validation
- Cross-field consistency

These evolve with business requirements.

### 3.2 Configuration-Driven

Rules are defined in YAML, not code.

```yaml
# config/quality_rules.yaml
version: "1.0"
description: "Quality validation rules for document extraction"

rules:
  - id: Q1
    name: "Date Sequence Validation"
    description: "Ensure dates follow logical order"
    field: "dates"
    condition: "date_sequence"
    severity: "warning"
    params:
      fields:
        - "issue_date"
        - "delivery_date"
        - "payment_due_date"
  
  - id: Q2
    name: "Amount Strict Match"
    description: "No tolerance for amount discrepancies"
    field: "total_amount"
    condition: "amount_tolerance"
    severity: "warning"
    params:
      tolerance: 0
      unit: "JPY"
  
  - id: Q3
    name: "Vendor Master Validation"
    description: "Company must exist in master database"
    field: "company_name"
    condition: "vendor_exists"
    severity: "warning"
    params:
      master_table: "vendors"
      match_field: "name"
      fuzzy_threshold: 0.95
  
  - id: Q4
    name: "Amount Reasonableness"
    description: "Flag unusually large amounts"
    field: "total_amount"
    condition: "range_check"
    severity: "info"
    params:
      min: 0
      max: 100000000  # 100M JPY
      message: "Amount exceeds typical range"
```

### 3.3 Implementation

```python
# core/linters/quality.py
import yaml
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path

@dataclass
class QualityRule:
    """A single quality validation rule."""
    id: str
    name: str
    description: str
    field: str
    condition: str
    severity: str  # "warning" | "info"
    params: Dict[str, Any]

@dataclass
class QualityWarning:
    """A quality issue found during validation."""
    rule_id: str
    rule_name: str
    field: str
    message: str
    severity: str

@dataclass
class QualityLinterResult:
    """Result of Quality Linter validation."""
    passed: bool  # True if no warnings
    warnings: List[QualityWarning]

class QualityLinter:
    """
    Configurable validation rules for business judgment.
    Rules loaded from YAML configuration.
    """
    
    def __init__(self, config_path: str = "config/quality_rules.yaml"):
        self.rules = self._load_rules(config_path)
        self._vendor_cache: Dict[str, bool] = {}
    
    def _load_rules(self, path: str) -> List[QualityRule]:
        """Load rules from YAML file."""
        config_file = Path(path)
        
        if not config_file.exists():
            return []
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        return [QualityRule(**rule) for rule in config.get("rules", [])]
    
    def validate(self, data: dict) -> QualityLinterResult:
        """Validate data against all Quality rules."""
        warnings = []
        
        for rule in self.rules:
            result = self._evaluate_rule(rule, data)
            if result:
                warnings.append(result)
        
        return QualityLinterResult(
            passed=len(warnings) == 0,
            warnings=warnings
        )
    
    def _evaluate_rule(self, rule: QualityRule, data: dict) -> Optional[QualityWarning]:
        """Evaluate a single rule."""
        
        if rule.condition == "date_sequence":
            return self._check_date_sequence(rule, data)
        elif rule.condition == "vendor_exists":
            return self._check_vendor_exists(rule, data)
        elif rule.condition == "range_check":
            return self._check_range(rule, data)
        
        return None
    
    def _check_date_sequence(self, rule: QualityRule, data: dict) -> Optional[QualityWarning]:
        """Validate: issue_date ≤ delivery_date ≤ payment_due_date"""
        fields = rule.params.get("fields", [])
        dates = []
        
        for field in fields:
            value = data.get(field)
            if value is None:
                continue
            dates.append((field, value))
        
        for i in range(len(dates) - 1):
            field1, date1 = dates[i]
            field2, date2 = dates[i + 1]
            
            if date1 > date2:
                return QualityWarning(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    field=f"{field1}, {field2}",
                    message=f"{field1} ({date1}) should not be after {field2} ({date2})",
                    severity=rule.severity
                )
        
        return None
    
    def _check_vendor_exists(self, rule: QualityRule, data: dict) -> Optional[QualityWarning]:
        """Validate company_name exists in vendor master."""
        company_name = data.get("company_name", "")
        
        if not company_name:
            return None
        
        if company_name in self._vendor_cache:
            exists = self._vendor_cache[company_name]
        else:
            exists = self._query_vendor_master(company_name)
            self._vendor_cache[company_name] = exists
        
        if not exists:
            return QualityWarning(
                rule_id=rule.id,
                rule_name=rule.name,
                field="company_name",
                message=f"'{company_name}' not found in vendor master",
                severity=rule.severity
            )
        
        return None
    
    def _check_range(self, rule: QualityRule, data: dict) -> Optional[QualityWarning]:
        """Check value within expected range."""
        value = data.get(rule.field)
        
        if value is None:
            return None
        
        max_val = rule.params.get("max")
        
        if max_val is not None and value > max_val:
            return QualityWarning(
                rule_id=rule.id,
                rule_name=rule.name,
                field=rule.field,
                message=rule.params.get("message", f"Value {value} exceeds {max_val}"),
                severity=rule.severity
            )
        
        return None
    
    def _query_vendor_master(self, company_name: str) -> bool:
        """Query Cloud SQL for vendor existence."""
        # Implement with actual DB connection
        return True  # Placeholder
```

---

## 4. Validation Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                  VALIDATION PIPELINE                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Gemini Output (JSON)                                        │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────────┐                                    │
│  │    GATE LINTER      │───── FAILED ────▶ Self-Correction  │
│  └──────────┬──────────┘                   or Escalation    │
│             │                                                │
│          PASSED                                              │
│             │                                                │
│             ▼                                                │
│  ┌─────────────────────┐                                    │
│  │   QUALITY LINTER    │                                    │
│  └──────────┬──────────┘                                    │
│             │                                                │
│     ┌───────┴───────┐                                       │
│     │               │                                        │
│   CLEAN         WARNINGS                                     │
│     │               │                                        │
│     ▼               ▼                                        │
│  Persist         Persist + Flag in UI                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Combined Validation

```python
def validate_document(data: dict) -> tuple[bool, List[str], List[QualityWarning]]:
    """
    Run both Gate and Quality linters.
    
    Returns:
        Tuple of (gate_passed, gate_errors, quality_warnings)
    """
    gate_result = GateLinter.validate(data)
    quality_result = QualityLinter().validate(data)
    
    return (
        gate_result.passed,
        gate_result.errors,
        quality_result.warnings
    )
```

---

## 6. Quality Warnings in UI

```tsx
// components/QualityWarnings.tsx
import { AlertCircle, Info } from "lucide-react";

interface QualityWarning {
  rule_id: string;
  field: string;
  message: string;
  severity: "warning" | "info";
}

export function QualityWarnings({ warnings }: { warnings: QualityWarning[] }) {
  if (!warnings?.length) return null;
  
  return (
    <div className="space-y-2 mb-4">
      {warnings.map((w, i) => (
        <div
          key={i}
          className={`p-3 rounded-lg flex items-start gap-3 ${
            w.severity === "warning"
              ? "bg-yellow-50 border border-yellow-200"
              : "bg-blue-50 border border-blue-200"
          }`}
        >
          {w.severity === "warning" ? (
            <AlertCircle className="h-5 w-5 text-yellow-600" />
          ) : (
            <Info className="h-5 w-5 text-blue-600" />
          )}
          <div>
            <p className="font-medium text-sm">{w.rule_id}: {w.field}</p>
            <p className="text-sm text-gray-600">{w.message}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
```

---

## 7. Monitoring

| Metric | Alert Threshold |
|--------|-----------------|
| Gate failure rate | >10% |
| Quality warning rate | >30% |
| Vendor not found rate | >5% |
