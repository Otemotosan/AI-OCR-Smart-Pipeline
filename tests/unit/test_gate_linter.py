"""Unit tests for Gate Linter."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from core.linters.gate import GateLinter, GateLinterResult

# ============================================================
# Happy Path Tests
# ============================================================


class TestGateLinterHappyPath:
    """Test successful validation scenarios."""

    def test_valid_delivery_note_passes(self) -> None:
        """Test that valid delivery note data passes all rules."""
        data = {
            "management_id": "INV-2025-001",
            "company_name": "株式会社山田商事",
            "issue_date": "2025-01-09",
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is True
        assert len(result.errors) == 0

    def test_valid_invoice_passes(self) -> None:
        """Test that valid invoice data passes all rules."""
        data = {
            "management_id": "INV-2025-001",
            "company_name": "テスト株式会社",
            "issue_date": date.today(),
            "document_type": "invoice",
        }
        result = GateLinter.validate(data)

        assert result.passed is True
        assert result.errors == []

    def test_various_valid_id_formats(self) -> None:
        """Test various valid management_id formats."""
        valid_ids = [
            "ABC123",  # Simple alphanumeric
            "INV-2025-001",  # With hyphens
            "INV_2025_001",  # With underscores
            "A1-B2_C3",  # Mixed
            "123456",  # Only numbers
            "ABCDEF",  # Only letters
            "A" * 20,  # Maximum length
            "A" * 6,  # Minimum length
        ]

        for valid_id in valid_ids:
            data = {
                "management_id": valid_id,
                "company_name": "Test Company",
                "issue_date": "2025-01-13",
                "document_type": "delivery_note",
            }
            result = GateLinter.validate(data)

            assert result.passed is True, f"Failed for ID: {valid_id}"


# ============================================================
# G1: management_id Required
# ============================================================


class TestManagementIdRequired:
    """Test G1: management_id must be non-empty."""

    def test_missing_management_id(self) -> None:
        """Test that missing management_id fails."""
        data = {
            "company_name": "Test",
            "issue_date": "2025-01-13",
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is False
        assert any("management_id" in e and "empty" in e.lower() for e in result.errors)

    def test_empty_string_management_id(self) -> None:
        """Test that empty string management_id fails."""
        data = {
            "management_id": "",
            "company_name": "Test",
            "issue_date": "2025-01-13",
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is False
        assert any("management_id" in e for e in result.errors)

    def test_whitespace_only_management_id(self) -> None:
        """Test that whitespace-only management_id fails."""
        data = {
            "management_id": "   ",
            "company_name": "Test",
            "issue_date": "2025-01-13",
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is False
        assert any("management_id" in e for e in result.errors)


# ============================================================
# G2: management_id Format
# ============================================================


class TestManagementIdFormat:
    """Test G2: management_id format validation."""

    @pytest.mark.parametrize(
        "invalid_id",
        [
            "AB",  # Too short (< 6)
            "ABCDE",  # Too short (5 chars)
            "A" * 21,  # Too long (> 20)
            "A" * 25,  # Way too long
            "INV 001",  # Contains space
            "INV@001",  # Invalid character @
            "INV#001",  # Invalid character #
            "INV.001",  # Invalid character .
            "日本語ID",  # Non-ASCII characters
            "INV/001",  # Invalid character /
            "INV\\001",  # Invalid character \
        ],
    )
    def test_invalid_id_formats(self, invalid_id: str) -> None:
        """Test that invalid management_id formats fail."""
        data = {
            "management_id": invalid_id,
            "company_name": "Test",
            "issue_date": "2025-01-13",
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is False, f"Should fail for ID: {invalid_id}"
        assert any("format" in e.lower() for e in result.errors)


# ============================================================
# G3: company_name Required
# ============================================================


class TestCompanyNameRequired:
    """Test G3: company_name must be non-empty."""

    def test_missing_company_name(self) -> None:
        """Test that missing company_name fails."""
        data = {
            "management_id": "INV-001",
            "issue_date": "2025-01-13",
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is False
        assert any("company_name" in e and "empty" in e.lower() for e in result.errors)

    def test_empty_string_company_name(self) -> None:
        """Test that empty string company_name fails."""
        data = {
            "management_id": "INV-001",
            "company_name": "",
            "issue_date": "2025-01-13",
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is False
        assert any("company_name" in e for e in result.errors)

    def test_whitespace_only_company_name(self) -> None:
        """Test that whitespace-only company_name fails."""
        data = {
            "management_id": "INV-001",
            "company_name": "   ",
            "issue_date": "2025-01-13",
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is False


# ============================================================
# G4 & G5: issue_date Validation
# ============================================================


class TestIssueDateValidation:
    """Test G4 & G5: issue_date format and future check."""

    def test_missing_issue_date(self) -> None:
        """Test that missing issue_date fails."""
        data = {
            "management_id": "INV-001",
            "company_name": "Test",
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is False
        assert any("issue_date" in e and "missing" in e.lower() for e in result.errors)

    def test_none_issue_date(self) -> None:
        """Test that None issue_date fails."""
        data = {
            "management_id": "INV-001",
            "company_name": "Test",
            "issue_date": None,
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is False
        assert any("issue_date" in e for e in result.errors)

    @pytest.mark.parametrize(
        "invalid_date",
        [
            "2025-13-01",  # Invalid month
            "2025-01-32",  # Invalid day
            "invalid-date",  # Not a date
            "2025/13/01",  # Invalid month (slash format)
            "20250101",  # No separators
            "01-13-2025",  # Wrong order
        ],
    )
    def test_invalid_date_formats(self, invalid_date: str) -> None:
        """Test that invalid date formats fail."""
        data = {
            "management_id": "INV-001",
            "company_name": "Test",
            "issue_date": invalid_date,
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is False
        assert any("invalid" in e.lower() for e in result.errors)

    def test_future_date_fails(self) -> None:
        """Test that future dates fail."""
        future_date = (date.today() + timedelta(days=30)).isoformat()

        data = {
            "management_id": "INV-001",
            "company_name": "Test",
            "issue_date": future_date,
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is False
        assert any("future" in e.lower() for e in result.errors)

    def test_far_future_date_fails(self) -> None:
        """Test that far future dates fail."""
        data = {
            "management_id": "INV-001",
            "company_name": "Test",
            "issue_date": "2099-12-31",
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is False
        assert any("future" in e.lower() for e in result.errors)

    def test_today_date_passes(self) -> None:
        """Test that today's date passes."""
        data = {
            "management_id": "INV-001",
            "company_name": "Test",
            "issue_date": date.today(),
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is True

    def test_past_date_passes(self) -> None:
        """Test that past dates pass."""
        data = {
            "management_id": "INV-001",
            "company_name": "Test",
            "issue_date": "2020-01-01",
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is True


# ============================================================
# G6: document_type in Registry
# ============================================================


class TestDocumentTypeValidation:
    """Test G6: document_type must be in registry."""

    def test_unknown_document_type(self) -> None:
        """Test that unknown document_type fails."""
        data = {
            "management_id": "INV-001",
            "company_name": "Test",
            "issue_date": "2025-01-13",
            "document_type": "unknown_type",
        }
        result = GateLinter.validate(data)

        assert result.passed is False
        assert any("unknown" in e.lower() for e in result.errors)
        assert any("valid types" in e.lower() for e in result.errors)

    def test_empty_document_type_skipped(self) -> None:
        """Test that empty document_type is skipped (not checked)."""
        data = {
            "management_id": "INV-001",
            "company_name": "Test",
            "issue_date": "2025-01-13",
            "document_type": "",
        }
        result = GateLinter.validate(data)

        # Should pass because empty document_type is not checked by G6
        assert result.passed is True


# ============================================================
# Date Parsing Tests
# ============================================================


class TestDateParsing:
    """Test _parse_date helper function."""

    def test_parse_date_object(self) -> None:
        """Test parsing date object."""
        today = date.today()
        parsed = GateLinter._parse_date(today)

        assert parsed == today

    def test_parse_datetime_object(self) -> None:
        """Test parsing datetime object."""
        now = datetime.now()
        parsed = GateLinter._parse_date(now)

        assert parsed == now.date()

    def test_parse_iso_format(self) -> None:
        """Test parsing ISO format string."""
        parsed = GateLinter._parse_date("2025-01-13")

        assert parsed == date(2025, 1, 13)

    def test_parse_slash_format(self) -> None:
        """Test parsing slash format string."""
        parsed = GateLinter._parse_date("2025/01/13")

        assert parsed == date(2025, 1, 13)

    def test_parse_japanese_format(self) -> None:
        """Test parsing Japanese format string."""
        parsed = GateLinter._parse_date("2025年01月13日")

        assert parsed == date(2025, 1, 13)

    def test_parse_invalid_format(self) -> None:
        """Test parsing invalid format returns None."""
        parsed = GateLinter._parse_date("invalid-date")

        assert parsed is None

    def test_parse_none(self) -> None:
        """Test parsing None returns None."""
        parsed = GateLinter._parse_date(None)

        assert parsed is None


# ============================================================
# Multiple Errors Tests
# ============================================================


class TestMultipleErrors:
    """Test validation with multiple errors."""

    def test_all_fields_invalid(self) -> None:
        """Test that all errors are reported together."""
        data = {
            "management_id": "AB",  # Too short
            "company_name": "",  # Empty
            "issue_date": "invalid",  # Bad format
            "document_type": "unknown",  # Not in registry
        }
        result = GateLinter.validate(data)

        assert result.passed is False
        assert len(result.errors) == 4  # All 4 errors reported

    def test_two_errors(self) -> None:
        """Test that multiple errors are collected."""
        data = {
            "management_id": "",  # Empty
            "company_name": "",  # Empty
            "issue_date": "2025-01-13",
            "document_type": "delivery_note",
        }
        result = GateLinter.validate(data)

        assert result.passed is False
        assert len(result.errors) == 2


# ============================================================
# GateLinterResult Tests
# ============================================================


class TestGateLinterResult:
    """Test GateLinterResult dataclass."""

    def test_result_structure(self) -> None:
        """Test result dataclass structure."""
        result = GateLinterResult(passed=True, errors=[])

        assert result.passed is True
        assert result.errors == []

    def test_result_with_errors(self) -> None:
        """Test result with errors."""
        errors = ["Error 1", "Error 2"]
        result = GateLinterResult(passed=False, errors=errors)

        assert result.passed is False
        assert result.errors == errors
        assert len(result.errors) == 2
