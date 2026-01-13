"""Unit tests for Quality Linter."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from core.linters.quality import (
    QualityLinter,
    QualityLinterResult,
    QualityRule,
    QualityWarning,
)


# ============================================================
# YAML Loading Tests
# ============================================================


class TestYAMLLoading:
    """Test YAML configuration loading."""

    def test_load_existing_config(self) -> None:
        """Test loading existing quality_rules.yaml."""
        linter = QualityLinter("config/quality_rules.yaml")

        assert len(linter.rules) > 0
        assert all(isinstance(rule, QualityRule) for rule in linter.rules)

    def test_load_nonexistent_config(self) -> None:
        """Test graceful handling of missing config file."""
        linter = QualityLinter("nonexistent_file.yaml")

        assert linter.rules == []

    def test_parse_rule_structure(self) -> None:
        """Test that rules are parsed correctly."""
        linter = QualityLinter("config/quality_rules.yaml")

        if linter.rules:
            rule = linter.rules[0]
            assert hasattr(rule, "id")
            assert hasattr(rule, "name")
            assert hasattr(rule, "description")
            assert hasattr(rule, "field")
            assert hasattr(rule, "condition")
            assert hasattr(rule, "severity")
            assert hasattr(rule, "params")

    def test_load_custom_config(self) -> None:
        """Test loading custom YAML configuration."""
        yaml_content = """
version: "1.0"
description: "Test rules"
rules:
  - id: TEST1
    name: "Test Rule"
    description: "Test description"
    field: "test_field"
    condition: "range_check"
    severity: "warning"
    params:
      min: 0
      max: 100
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            linter = QualityLinter(temp_path)

            assert len(linter.rules) == 1
            assert linter.rules[0].id == "TEST1"
            assert linter.rules[0].condition == "range_check"
        finally:
            Path(temp_path).unlink()


# ============================================================
# Date Sequence Validation Tests
# ============================================================


class TestDateSequenceValidation:
    """Test date_sequence condition."""

    def test_valid_date_sequence(self) -> None:
        """Test that valid date sequence passes."""
        yaml_content = """
version: "1.0"
rules:
  - id: Q1
    name: "Date Sequence"
    description: "Test"
    field: "dates"
    condition: "date_sequence"
    severity: "warning"
    params:
      fields: ["issue_date", "delivery_date", "payment_due_date"]
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            linter = QualityLinter(temp_path)
            data = {
                "issue_date": date(2025, 1, 1),
                "delivery_date": date(2025, 1, 10),
                "payment_due_date": date(2025, 1, 31),
            }
            result = linter.validate(data)

            assert result.passed is True
            assert len(result.warnings) == 0
        finally:
            Path(temp_path).unlink()

    def test_invalid_date_sequence(self) -> None:
        """Test that invalid date sequence produces warning."""
        yaml_content = """
version: "1.0"
rules:
  - id: Q1
    name: "Date Sequence"
    description: "Test"
    field: "dates"
    condition: "date_sequence"
    severity: "warning"
    params:
      fields: ["issue_date", "delivery_date"]
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            linter = QualityLinter(temp_path)
            data = {
                "issue_date": date(2025, 1, 15),  # After delivery_date
                "delivery_date": date(2025, 1, 10),
            }
            result = linter.validate(data)

            assert result.passed is False
            assert len(result.warnings) == 1
            assert "should not be after" in result.warnings[0].message
        finally:
            Path(temp_path).unlink()

    def test_date_sequence_with_missing_dates(self) -> None:
        """Test date sequence when some dates are missing."""
        yaml_content = """
version: "1.0"
rules:
  - id: Q1
    name: "Date Sequence"
    description: "Test"
    field: "dates"
    condition: "date_sequence"
    severity: "warning"
    params:
      fields: ["issue_date", "delivery_date", "payment_due_date"]
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            linter = QualityLinter(temp_path)
            data = {
                "issue_date": date(2025, 1, 1),
                # delivery_date missing
                "payment_due_date": date(2025, 1, 31),
            }
            result = linter.validate(data)

            # Should pass because missing dates are skipped
            assert result.passed is True
        finally:
            Path(temp_path).unlink()


# ============================================================
# Range Check Tests
# ============================================================


class TestRangeCheck:
    """Test range_check condition."""

    def test_value_within_range(self) -> None:
        """Test that value within range passes."""
        yaml_content = """
version: "1.0"
rules:
  - id: Q4
    name: "Amount Range"
    description: "Test"
    field: "total_amount"
    condition: "range_check"
    severity: "info"
    params:
      min: 0
      max: 100000000
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            linter = QualityLinter(temp_path)
            data = {"total_amount": 50000}
            result = linter.validate(data)

            assert result.passed is True
            assert len(result.warnings) == 0
        finally:
            Path(temp_path).unlink()

    def test_value_exceeds_max(self) -> None:
        """Test that value exceeding max produces warning."""
        yaml_content = """
version: "1.0"
rules:
  - id: Q4
    name: "Amount Range"
    description: "Test"
    field: "total_amount"
    condition: "range_check"
    severity: "info"
    params:
      max: 100000000
      message: "Amount exceeds typical range"
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            linter = QualityLinter(temp_path)
            data = {"total_amount": 200000000}  # Exceeds max
            result = linter.validate(data)

            assert result.passed is False
            assert len(result.warnings) == 1
            assert "Amount exceeds typical range" in result.warnings[0].message
        finally:
            Path(temp_path).unlink()

    def test_value_below_min(self) -> None:
        """Test that value below min produces warning."""
        yaml_content = """
version: "1.0"
rules:
  - id: Q4
    name: "Amount Range"
    description: "Test"
    field: "total_amount"
    condition: "range_check"
    severity: "warning"
    params:
      min: 100
      max: 100000000
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            linter = QualityLinter(temp_path)
            data = {"total_amount": 50}  # Below min
            result = linter.validate(data)

            assert result.passed is False
            assert len(result.warnings) == 1
            assert "below minimum" in result.warnings[0].message.lower()
        finally:
            Path(temp_path).unlink()

    def test_missing_value_skipped(self) -> None:
        """Test that missing value is skipped."""
        yaml_content = """
version: "1.0"
rules:
  - id: Q4
    name: "Amount Range"
    description: "Test"
    field: "total_amount"
    condition: "range_check"
    severity: "info"
    params:
      min: 0
      max: 100000000
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            linter = QualityLinter(temp_path)
            data = {}  # total_amount missing
            result = linter.validate(data)

            # Should pass because None values are skipped
            assert result.passed is True
        finally:
            Path(temp_path).unlink()


# ============================================================
# Vendor Existence Check Tests
# ============================================================


class TestVendorExistenceCheck:
    """Test vendor_exists condition."""

    def test_vendor_exists_placeholder(self) -> None:
        """Test vendor existence check (placeholder always returns True)."""
        yaml_content = """
version: "1.0"
rules:
  - id: Q3
    name: "Vendor Master"
    description: "Test"
    field: "company_name"
    condition: "vendor_exists"
    severity: "warning"
    params:
      master_table: "vendors"
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            linter = QualityLinter(temp_path)
            data = {"company_name": "テスト株式会社"}
            result = linter.validate(data)

            # Placeholder implementation always returns True
            assert result.passed is True
        finally:
            Path(temp_path).unlink()

    def test_vendor_check_caching(self) -> None:
        """Test that vendor checks are cached."""
        yaml_content = """
version: "1.0"
rules:
  - id: Q3
    name: "Vendor Master"
    description: "Test"
    field: "company_name"
    condition: "vendor_exists"
    severity: "warning"
    params: {}
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            linter = QualityLinter(temp_path)

            # First call
            data1 = {"company_name": "TestCompany"}
            linter.validate(data1)
            assert "TestCompany" in linter._vendor_cache

            # Second call with same company (should use cache)
            data2 = {"company_name": "TestCompany"}
            linter.validate(data2)

            # Cache should still contain entry
            assert "TestCompany" in linter._vendor_cache
        finally:
            Path(temp_path).unlink()


# ============================================================
# Multiple Rules Tests
# ============================================================


class TestMultipleRules:
    """Test validation with multiple rules."""

    def test_multiple_warnings(self) -> None:
        """Test that multiple warnings are collected."""
        yaml_content = """
version: "1.0"
rules:
  - id: Q1
    name: "Date Sequence"
    description: "Test"
    field: "dates"
    condition: "date_sequence"
    severity: "warning"
    params:
      fields: ["issue_date", "delivery_date"]
  - id: Q4
    name: "Amount Range"
    description: "Test"
    field: "total_amount"
    condition: "range_check"
    severity: "info"
    params:
      max: 1000
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            linter = QualityLinter(temp_path)
            data = {
                "issue_date": date(2025, 1, 15),
                "delivery_date": date(2025, 1, 10),  # Before issue_date
                "total_amount": 5000,  # Exceeds max
            }
            result = linter.validate(data)

            assert result.passed is False
            assert len(result.warnings) == 2
        finally:
            Path(temp_path).unlink()

    def test_no_warnings(self) -> None:
        """Test that clean data produces no warnings."""
        yaml_content = """
version: "1.0"
rules:
  - id: Q4
    name: "Amount Range"
    description: "Test"
    field: "total_amount"
    condition: "range_check"
    severity: "info"
    params:
      min: 0
      max: 100000
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            linter = QualityLinter(temp_path)
            data = {"total_amount": 5000}
            result = linter.validate(data)

            assert result.passed is True
            assert len(result.warnings) == 0
        finally:
            Path(temp_path).unlink()


# ============================================================
# Dataclass Tests
# ============================================================


class TestQualityWarning:
    """Test QualityWarning dataclass."""

    def test_warning_structure(self) -> None:
        """Test warning dataclass structure."""
        warning = QualityWarning(
            rule_id="Q1",
            rule_name="Test Rule",
            field="test_field",
            message="Test message",
            severity="warning",
        )

        assert warning.rule_id == "Q1"
        assert warning.rule_name == "Test Rule"
        assert warning.field == "test_field"
        assert warning.message == "Test message"
        assert warning.severity == "warning"


class TestQualityLinterResult:
    """Test QualityLinterResult dataclass."""

    def test_result_passed(self) -> None:
        """Test result with no warnings."""
        result = QualityLinterResult(passed=True, warnings=[])

        assert result.passed is True
        assert result.warnings == []

    def test_result_with_warnings(self) -> None:
        """Test result with warnings."""
        warnings = [
            QualityWarning("Q1", "Rule 1", "field1", "Message 1", "warning"),
            QualityWarning("Q2", "Rule 2", "field2", "Message 2", "info"),
        ]
        result = QualityLinterResult(passed=False, warnings=warnings)

        assert result.passed is False
        assert len(result.warnings) == 2


class TestQualityRule:
    """Test QualityRule dataclass."""

    def test_rule_structure(self) -> None:
        """Test rule dataclass structure."""
        rule = QualityRule(
            id="Q1",
            name="Test Rule",
            description="Test description",
            field="test_field",
            condition="range_check",
            severity="warning",
            params={"min": 0, "max": 100},
        )

        assert rule.id == "Q1"
        assert rule.name == "Test Rule"
        assert rule.condition == "range_check"
        assert rule.params["min"] == 0


# ============================================================
# Unknown Condition Tests
# ============================================================


class TestUnknownCondition:
    """Test handling of unknown conditions."""

    def test_unknown_condition_skipped(self) -> None:
        """Test that unknown conditions are skipped gracefully."""
        yaml_content = """
version: "1.0"
rules:
  - id: Q99
    name: "Unknown Rule"
    description: "Test"
    field: "test_field"
    condition: "unknown_condition"
    severity: "warning"
    params: {}
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            linter = QualityLinter(temp_path)
            data = {"test_field": "value"}
            result = linter.validate(data)

            # Unknown condition is skipped, so no warnings
            assert result.passed is True
            assert len(result.warnings) == 0
        finally:
            Path(temp_path).unlink()
