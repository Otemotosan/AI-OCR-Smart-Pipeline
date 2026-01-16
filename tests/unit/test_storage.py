"""
Unit tests for GCS Storage Operations.

See: docs/specs/03_saga.md
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

# Mock Google Cloud modules before importing storage
sys.modules["google.cloud"] = Mock()
sys.modules["google.cloud.storage"] = Mock()
sys.modules["google.api_core"] = Mock()
sys.modules["google.api_core.retry"] = Mock()
sys.modules["google.api_core.exceptions"] = Mock()

# Create mock exceptions
NotFound = type("NotFound", (Exception,), {})
GoogleAPIError = type("GoogleAPIError", (Exception,), {})
sys.modules["google.api_core.exceptions"].NotFound = NotFound
sys.modules["google.api_core.exceptions"].GoogleAPIError = GoogleAPIError

from src.core.storage import (  # noqa: E402
    FileNotFoundError as GCSFileNotFoundError,
)
from src.core.storage import (  # noqa: E402
    InvalidGCSPathError,
    StorageError,
    _sanitize_filename,
    generate_destination_path,
    parse_gcs_path,
)


class TestParseGCSPath:
    """Tests for parse_gcs_path function."""

    def test_valid_path(self) -> None:
        """Test parsing a valid GCS path."""
        bucket, blob = parse_gcs_path("gs://my-bucket/path/to/file.pdf")

        assert bucket == "my-bucket"
        assert blob == "path/to/file.pdf"

    def test_valid_path_single_level(self) -> None:
        """Test parsing a GCS path with single level."""
        bucket, blob = parse_gcs_path("gs://bucket/file.pdf")

        assert bucket == "bucket"
        assert blob == "file.pdf"

    def test_empty_path_raises(self) -> None:
        """Test that empty path raises InvalidGCSPathError."""
        with pytest.raises(InvalidGCSPathError) as exc_info:
            parse_gcs_path("")

        assert "empty path" in str(exc_info.value)

    def test_missing_gs_prefix_raises(self) -> None:
        """Test that path without gs:// prefix raises error."""
        with pytest.raises(InvalidGCSPathError) as exc_info:
            parse_gcs_path("bucket/path/file.pdf")

        assert "must start with gs://" in str(exc_info.value)

    def test_missing_blob_path_raises(self) -> None:
        """Test that path without blob raises error."""
        with pytest.raises(InvalidGCSPathError) as exc_info:
            parse_gcs_path("gs://bucket")

        assert "missing blob path" in str(exc_info.value)

    def test_empty_bucket_raises(self) -> None:
        """Test that empty bucket name raises error."""
        with pytest.raises(InvalidGCSPathError) as exc_info:
            parse_gcs_path("gs:///path/to/file.pdf")

        assert "empty bucket" in str(exc_info.value)


class TestGenerateDestinationPath:
    """Tests for generate_destination_path function."""

    def test_valid_path_generation(self) -> None:
        """Test generating a valid destination path."""
        schema_data = {
            "management_id": "INV-2025-001",
            "company_name": "山田商事",
            "issue_date": "2025-01-15",
        }
        timestamp = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

        result = generate_destination_path(schema_data, timestamp, "output-bucket")

        assert result == "gs://output-bucket/202501/INV-2025-001_山田商事_20250115.pdf"

    def test_path_with_datetime_issue_date(self) -> None:
        """Test path generation with datetime issue_date."""
        schema_data = {
            "management_id": "TEST-001",
            "company_name": "Test Co",
            "issue_date": datetime(2025, 3, 20),
        }
        timestamp = datetime(2025, 3, 20, tzinfo=UTC)

        result = generate_destination_path(schema_data, timestamp, "bucket")

        assert "20250320" in result

    def test_missing_management_id_raises(self) -> None:
        """Test that missing management_id raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            generate_destination_path(
                {"company_name": "Test", "issue_date": "2025-01-01"},
                datetime.now(UTC),
                "bucket",
            )

        assert "management_id" in str(exc_info.value)

    def test_missing_company_name_raises(self) -> None:
        """Test that missing company_name raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            generate_destination_path(
                {"management_id": "ID-001", "issue_date": "2025-01-01"},
                datetime.now(UTC),
                "bucket",
            )

        assert "company_name" in str(exc_info.value)


class TestSanitizeFilename:
    """Tests for _sanitize_filename function."""

    def test_basic_sanitization(self) -> None:
        """Test basic filename sanitization."""
        result = _sanitize_filename("Normal Text")
        assert result == "Normal Text"

    def test_removes_invalid_characters(self) -> None:
        """Test removal of invalid characters."""
        result = _sanitize_filename('File<>:"/\\|?*Name')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result

    def test_preserves_japanese_characters(self) -> None:
        """Test that Japanese characters are preserved."""
        result = _sanitize_filename("山田商事株式会社")
        assert result == "山田商事株式会社"

    def test_truncates_long_names(self) -> None:
        """Test truncation of long names."""
        long_name = "A" * 100
        result = _sanitize_filename(long_name, max_length=50)
        assert len(result) <= 50

    def test_removes_multiple_underscores(self) -> None:
        """Test removal of consecutive underscores."""
        result = _sanitize_filename("Test___Multiple___Underscores")
        assert "___" not in result


class TestExceptionClasses:
    """Tests for exception classes."""

    def test_invalid_gcs_path_error(self) -> None:
        """Test InvalidGCSPathError."""
        error = InvalidGCSPathError("bad-path", "missing prefix")
        assert "bad-path" in str(error)
        assert "missing prefix" in str(error)

    def test_storage_error(self) -> None:
        """Test StorageError."""
        error = StorageError("Test storage error")
        assert "Test storage error" in str(error)

    def test_file_not_found_error(self) -> None:
        """Test FileNotFoundError."""
        error = GCSFileNotFoundError("gs://bucket/missing.pdf")
        assert "gs://bucket/missing.pdf" in str(error)
