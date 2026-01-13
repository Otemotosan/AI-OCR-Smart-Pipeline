"""Gate Linter - Immutable validation rules for physical operations.

Gate Linter enforces invariants that affect file naming, folder routing,
and database operations. Failures block document persistence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from core.schemas import SCHEMA_REGISTRY


@dataclass
class GateLinterResult:
    """Result of Gate Linter validation."""

    passed: bool
    errors: list[str]


class GateLinter:
    """Immutable validation rules affecting physical operations.

    These rules are hardcoded — they define system invariants.
    Pure functions only — no side effects.

    Rules:
        G1: management_id non-empty
        G2: management_id format valid (6-20 alphanumeric + hyphens/underscores)
        G3: company_name non-empty
        G4: issue_date valid date
        G5: issue_date not future
        G6: document_type in registry
    """

    # Management ID pattern: 6-20 alphanumeric with hyphens/underscores
    ID_PATTERN = re.compile(r"^[A-Za-z0-9\-_]{6,20}$")

    @classmethod
    def validate(cls, data: dict) -> GateLinterResult:
        """Validate data against all Gate rules.

        Args:
            data: Extracted document data dictionary

        Returns:
            GateLinterResult with passed flag and error list

        Examples:
            >>> data = {
            ...     "management_id": "INV-2025-001",
            ...     "company_name": "テスト株式会社",
            ...     "issue_date": "2025-01-13",
            ...     "document_type": "delivery_note"
            ... }
            >>> result = GateLinter.validate(data)
            >>> result.passed
            True
            >>> result.errors
            []
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
                errors.append(f"issue_date: Future date not allowed ({parsed_date})")

        # G6: document_type in registry
        document_type = data.get("document_type", "")
        if document_type and document_type not in SCHEMA_REGISTRY:
            available = list(SCHEMA_REGISTRY.keys())
            errors.append(
                f"document_type: Unknown type '{document_type}'. "
                f"Valid types: {available}"
            )

        return GateLinterResult(passed=len(errors) == 0, errors=errors)

    @staticmethod
    def _parse_date(value: date | datetime | str | None) -> date | None:
        """Parse various date formats.

        Args:
            value: Date value in various formats

        Returns:
            Parsed date object or None if parsing fails

        Supported formats:
            - date object (returns as-is)
            - datetime object (extracts date)
            - ISO format: "YYYY-MM-DD"
            - Slash format: "YYYY/MM/DD"
            - Japanese format: "YYYY年MM月DD日"

        Examples:
            >>> GateLinter._parse_date("2025-01-13")
            date(2025, 1, 13)
            >>> GateLinter._parse_date("2025/01/13")
            date(2025, 1, 13)
            >>> GateLinter._parse_date("invalid")
            None
        """
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
