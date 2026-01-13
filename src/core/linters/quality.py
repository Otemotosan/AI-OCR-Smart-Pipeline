"""Quality Linter - Configurable validation rules for business judgment.

Quality Linter provides warnings for business logic issues but does not
block document persistence. Rules are defined in YAML configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class QualityRule:
    """A single quality validation rule."""

    id: str
    name: str
    description: str
    field: str
    condition: str
    severity: str  # "warning" | "info"
    params: dict[str, Any]


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
    warnings: list[QualityWarning]


class QualityLinter:
    """Configurable validation rules for business judgment.

    Rules loaded from YAML configuration. Unlike Gate Linter,
    these rules produce warnings that don't block persistence.

    Supported Conditions:
        - date_sequence: Validate chronological order of dates
        - vendor_exists: Check company name in vendor master
        - range_check: Validate value within expected range
    """

    def __init__(self, config_path: str = "config/quality_rules.yaml") -> None:
        """Initialize Quality Linter with configuration.

        Args:
            config_path: Path to YAML configuration file

        Examples:
            >>> linter = QualityLinter()
            >>> linter = QualityLinter("custom_rules.yaml")
        """
        self.rules = self._load_rules(config_path)
        self._vendor_cache: dict[str, bool] = {}

    def _load_rules(self, path: str) -> list[QualityRule]:
        """Load rules from YAML file.

        Args:
            path: Path to YAML configuration file

        Returns:
            List of QualityRule objects

        Notes:
            Returns empty list if file doesn't exist (graceful degradation)
        """
        config_file = Path(path)

        if not config_file.exists():
            return []

        with config_file.open(encoding="utf-8") as f:
            config = yaml.safe_load(f)

        rules = []
        for rule_dict in config.get("rules", []):
            rules.append(
                QualityRule(
                    id=rule_dict["id"],
                    name=rule_dict["name"],
                    description=rule_dict["description"],
                    field=rule_dict["field"],
                    condition=rule_dict["condition"],
                    severity=rule_dict["severity"],
                    params=rule_dict.get("params", {}),
                )
            )

        return rules

    def validate(self, data: dict) -> QualityLinterResult:
        """Validate data against all Quality rules.

        Args:
            data: Document data dictionary

        Returns:
            QualityLinterResult with warnings

        Examples:
            >>> data = {
            ...     "issue_date": "2025-01-13",
            ...     "delivery_date": "2025-01-10"  # Before issue_date
            ... }
            >>> result = linter.validate(data)
            >>> result.passed
            False
            >>> len(result.warnings)
            1
        """
        warnings = []

        for rule in self.rules:
            result = self._evaluate_rule(rule, data)
            if result:
                warnings.append(result)

        return QualityLinterResult(passed=len(warnings) == 0, warnings=warnings)

    def _evaluate_rule(self, rule: QualityRule, data: dict) -> QualityWarning | None:
        """Evaluate a single rule.

        Args:
            rule: Quality rule to evaluate
            data: Document data

        Returns:
            QualityWarning if rule failed, None otherwise
        """
        if rule.condition == "date_sequence":
            return self._check_date_sequence(rule, data)
        elif rule.condition == "vendor_exists":
            return self._check_vendor_exists(rule, data)
        elif rule.condition == "range_check":
            return self._check_range(rule, data)

        return None

    def _check_date_sequence(self, rule: QualityRule, data: dict) -> QualityWarning | None:
        """Validate: dates follow chronological order.

        Args:
            rule: Rule with params containing 'fields' list
            data: Document data

        Returns:
            QualityWarning if dates are out of order

        Examples:
            Rule params: {"fields": ["issue_date", "delivery_date", "payment_due_date"]}
            Expected: issue_date ≤ delivery_date ≤ payment_due_date
        """
        fields = rule.params.get("fields", [])
        dates = []

        # Collect non-null dates
        for field in fields:
            value = data.get(field)
            if value is None:
                continue
            dates.append((field, value))

        # Check sequential ordering
        for i in range(len(dates) - 1):
            field1, date1 = dates[i]
            field2, date2 = dates[i + 1]

            if date1 > date2:
                return QualityWarning(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    field=f"{field1}, {field2}",
                    message=f"{field1} ({date1}) should not be after {field2} ({date2})",
                    severity=rule.severity,
                )

        return None

    def _check_vendor_exists(self, rule: QualityRule, data: dict) -> QualityWarning | None:
        """Validate company_name exists in vendor master.

        Args:
            rule: Rule configuration
            data: Document data

        Returns:
            QualityWarning if vendor not found

        Notes:
            Uses in-memory cache to avoid repeated database queries.
            Actual database query is a placeholder for now.
        """
        company_name = data.get("company_name", "")

        if not company_name:
            return None

        # Check cache first
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
                severity=rule.severity,
            )

        return None

    def _check_range(self, rule: QualityRule, data: dict) -> QualityWarning | None:
        """Check value within expected range.

        Args:
            rule: Rule with params containing 'min' and 'max'
            data: Document data

        Returns:
            QualityWarning if value outside range

        Examples:
            Rule params: {"min": 0, "max": 100000000, "message": "Amount exceeds typical range"}
        """
        value = data.get(rule.field)

        if value is None:
            return None

        min_val = rule.params.get("min")
        max_val = rule.params.get("max")

        if min_val is not None and value < min_val:
            return QualityWarning(
                rule_id=rule.id,
                rule_name=rule.name,
                field=rule.field,
                message=rule.params.get("message", f"Value {value} below minimum {min_val}"),
                severity=rule.severity,
            )

        if max_val is not None and value > max_val:
            return QualityWarning(
                rule_id=rule.id,
                rule_name=rule.name,
                field=rule.field,
                message=rule.params.get("message", f"Value {value} exceeds {max_val}"),
                severity=rule.severity,
            )

        return None

    def _query_vendor_master(self, company_name: str) -> bool:
        """Query Cloud SQL for vendor existence.

        Args:
            company_name: Company name to look up

        Returns:
            True if vendor exists, False otherwise

        Notes:
            Placeholder implementation - always returns True.
            TODO: Implement actual Cloud SQL connection in Phase 3.
        """
        # Placeholder - implement with actual DB connection in Phase 3
        return True
