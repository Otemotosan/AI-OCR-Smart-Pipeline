"""
Unit tests for GCS Storage Operations.

See: docs/specs/03_saga.md
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch

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
    DEFAULT_RETRY,
    InvalidGCSPathError,
    StorageClient,
    StorageError,
    _sanitize_filename,
    copy_blob,
    delete_blob,
    download_as_bytes,
    file_exists,
    generate_destination_path,
    list_blobs,
    parse_gcs_path,
    upload_string,
)
from src.core.storage import (  # noqa: E402
    FileNotFoundError as GCSFileNotFoundError,
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

    def test_empty_blob_path_raises(self) -> None:
        """Test that empty blob path raises error."""
        with pytest.raises(InvalidGCSPathError) as exc_info:
            parse_gcs_path("gs://bucket/")

        assert "empty blob path" in str(exc_info.value)


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

    def test_path_with_slash_date_format(self) -> None:
        """Test path generation with slash date format."""
        schema_data = {
            "management_id": "TEST-002",
            "company_name": "Test Corp",
            "issue_date": "2025/04/25",
        }
        timestamp = datetime(2025, 4, 25, tzinfo=UTC)

        result = generate_destination_path(schema_data, timestamp, "bucket")

        assert "20250425" in result

    def test_path_with_numeric_issue_date(self) -> None:
        """Test path generation with numeric issue_date."""
        schema_data = {
            "management_id": "TEST-003",
            "company_name": "Test Inc",
            "issue_date": 20250515,  # numeric format
        }
        timestamp = datetime(2025, 5, 15, tzinfo=UTC)

        result = generate_destination_path(schema_data, timestamp, "bucket")

        assert "20250515" in result

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

    def test_missing_issue_date_raises(self) -> None:
        """Test that missing issue_date raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            generate_destination_path(
                {"management_id": "ID-001", "company_name": "Test"},
                datetime.now(UTC),
                "bucket",
            )

        assert "issue_date" in str(exc_info.value)

    def test_empty_management_id_raises(self) -> None:
        """Test that empty management_id raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            generate_destination_path(
                {"management_id": "", "company_name": "Test", "issue_date": "2025-01-01"},
                datetime.now(UTC),
                "bucket",
            )

        assert "management_id" in str(exc_info.value)

    def test_empty_company_name_raises(self) -> None:
        """Test that empty company_name raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            generate_destination_path(
                {"management_id": "ID-001", "company_name": "", "issue_date": "2025-01-01"},
                datetime.now(UTC),
                "bucket",
            )

        assert "company_name" in str(exc_info.value)

    def test_empty_issue_date_raises(self) -> None:
        """Test that empty issue_date raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            generate_destination_path(
                {"management_id": "ID-001", "company_name": "Test", "issue_date": ""},
                datetime.now(UTC),
                "bucket",
            )

        assert "issue_date" in str(exc_info.value)


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

    def test_strips_leading_trailing_underscores(self) -> None:
        """Test stripping of leading/trailing underscores."""
        result = _sanitize_filename("__Test__")
        assert not result.startswith("_")
        assert not result.endswith("_")

    def test_strips_whitespace(self) -> None:
        """Test stripping of whitespace."""
        result = _sanitize_filename("  Test  ")
        assert result == "Test"

    def test_removes_control_characters(self) -> None:
        """Test removal of control characters."""
        result = _sanitize_filename("Test\x00\x1fName")
        assert "\x00" not in result
        assert "\x1f" not in result

    def test_truncate_removes_trailing_underscore(self) -> None:
        """Test that truncation removes trailing underscores."""
        # Create a name where truncation would leave trailing underscore
        result = _sanitize_filename("Test<>Name" * 10, max_length=10)
        assert not result.endswith("_")


class TestExceptionClasses:
    """Tests for exception classes."""

    def test_invalid_gcs_path_error(self) -> None:
        """Test InvalidGCSPathError."""
        error = InvalidGCSPathError("bad-path", "missing prefix")
        assert "bad-path" in str(error)
        assert "missing prefix" in str(error)

    def test_invalid_gcs_path_error_no_reason(self) -> None:
        """Test InvalidGCSPathError without reason."""
        error = InvalidGCSPathError("bad-path")
        assert "bad-path" in str(error)
        assert error.path == "bad-path"
        assert error.reason == ""

    def test_storage_error(self) -> None:
        """Test StorageError."""
        error = StorageError("Test storage error")
        assert "Test storage error" in str(error)

    def test_file_not_found_error(self) -> None:
        """Test FileNotFoundError."""
        error = GCSFileNotFoundError("gs://bucket/missing.pdf")
        assert "gs://bucket/missing.pdf" in str(error)
        assert error.path == "gs://bucket/missing.pdf"


class TestCopyBlob:
    """Tests for copy_blob function."""

    def test_copy_blob_success(self) -> None:
        """Test successful blob copy."""
        mock_client = MagicMock()
        mock_source_bucket = MagicMock()
        mock_dest_bucket = MagicMock()
        mock_source_blob = MagicMock()
        mock_dest_blob = MagicMock()

        mock_client.bucket.side_effect = [mock_source_bucket, mock_dest_bucket]
        mock_source_bucket.blob.return_value = mock_source_blob
        mock_dest_bucket.blob.return_value = mock_dest_blob
        mock_source_blob.exists.return_value = True
        mock_dest_blob.rewrite.return_value = (None, 1000, 1000)  # Complete in one call

        copy_blob(
            mock_client,
            "gs://source-bucket/source.pdf",
            "gs://dest-bucket/dest.pdf",
        )

        mock_dest_blob.rewrite.assert_called_once()

    def test_copy_blob_with_progress(self) -> None:
        """Test blob copy with multiple rewrite calls (large file)."""
        mock_client = MagicMock()
        mock_source_bucket = MagicMock()
        mock_dest_bucket = MagicMock()
        mock_source_blob = MagicMock()
        mock_dest_blob = MagicMock()

        mock_client.bucket.side_effect = [mock_source_bucket, mock_dest_bucket]
        mock_source_bucket.blob.return_value = mock_source_blob
        mock_dest_bucket.blob.return_value = mock_dest_blob
        mock_source_blob.exists.return_value = True
        # Simulate multi-part rewrite
        mock_dest_blob.rewrite.side_effect = [
            ("token1", 500, 1000),
            ("token2", 800, 1000),
            (None, 1000, 1000),  # Complete
        ]

        copy_blob(
            mock_client,
            "gs://source-bucket/large.pdf",
            "gs://dest-bucket/large.pdf",
        )

        assert mock_dest_blob.rewrite.call_count == 3

    def test_copy_blob_source_not_found(self) -> None:
        """Test copy_blob raises FileNotFoundError when source doesn't exist."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = False

        with pytest.raises(GCSFileNotFoundError):
            copy_blob(
                mock_client,
                "gs://bucket/missing.pdf",
                "gs://bucket/dest.pdf",
            )

    def test_copy_blob_not_found_exception(self) -> None:
        """Test copy_blob handles NotFound exception."""
        mock_client = MagicMock()
        mock_source_bucket = MagicMock()
        mock_dest_bucket = MagicMock()
        mock_source_blob = MagicMock()
        mock_dest_blob = MagicMock()

        mock_client.bucket.side_effect = [mock_source_bucket, mock_dest_bucket]
        mock_source_bucket.blob.return_value = mock_source_blob
        mock_dest_bucket.blob.return_value = mock_dest_blob
        mock_source_blob.exists.return_value = True
        mock_dest_blob.rewrite.side_effect = NotFound("Not found")

        with pytest.raises(GCSFileNotFoundError):
            copy_blob(
                mock_client,
                "gs://bucket/source.pdf",
                "gs://bucket/dest.pdf",
            )

    def test_copy_blob_google_api_error(self) -> None:
        """Test copy_blob handles GoogleAPIError."""
        mock_client = MagicMock()
        mock_source_bucket = MagicMock()
        mock_dest_bucket = MagicMock()
        mock_source_blob = MagicMock()
        mock_dest_blob = MagicMock()

        mock_client.bucket.side_effect = [mock_source_bucket, mock_dest_bucket]
        mock_source_bucket.blob.return_value = mock_source_blob
        mock_dest_bucket.blob.return_value = mock_dest_blob
        mock_source_blob.exists.return_value = True
        mock_dest_blob.rewrite.side_effect = GoogleAPIError("API error")

        with pytest.raises(StorageError) as exc_info:
            copy_blob(
                mock_client,
                "gs://bucket/source.pdf",
                "gs://bucket/dest.pdf",
            )

        assert "Failed to copy" in str(exc_info.value)

    def test_copy_blob_with_custom_retry(self) -> None:
        """Test copy_blob with custom retry config."""
        mock_client = MagicMock()
        mock_source_bucket = MagicMock()
        mock_dest_bucket = MagicMock()
        mock_source_blob = MagicMock()
        mock_dest_blob = MagicMock()
        mock_retry = MagicMock()

        mock_client.bucket.side_effect = [mock_source_bucket, mock_dest_bucket]
        mock_source_bucket.blob.return_value = mock_source_blob
        mock_dest_bucket.blob.return_value = mock_dest_blob
        mock_source_blob.exists.return_value = True
        mock_dest_blob.rewrite.return_value = (None, 1000, 1000)

        copy_blob(
            mock_client,
            "gs://bucket/source.pdf",
            "gs://bucket/dest.pdf",
            retry_config=mock_retry,
        )

        mock_dest_blob.rewrite.assert_called_once()

    def test_copy_blob_zero_total_bytes(self) -> None:
        """Test copy_blob handles zero total bytes (empty file)."""
        mock_client = MagicMock()
        mock_source_bucket = MagicMock()
        mock_dest_bucket = MagicMock()
        mock_source_blob = MagicMock()
        mock_dest_blob = MagicMock()

        mock_client.bucket.side_effect = [mock_source_bucket, mock_dest_bucket]
        mock_source_bucket.blob.return_value = mock_source_blob
        mock_dest_bucket.blob.return_value = mock_dest_blob
        mock_source_blob.exists.return_value = True
        mock_dest_blob.rewrite.return_value = (None, 0, 0)

        # Should not raise division by zero
        copy_blob(
            mock_client,
            "gs://bucket/empty.pdf",
            "gs://bucket/dest.pdf",
        )


class TestDeleteBlob:
    """Tests for delete_blob function."""

    def test_delete_blob_success(self) -> None:
        """Test successful blob deletion."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        result = delete_blob(mock_client, "gs://bucket/file.pdf")

        assert result is True
        mock_blob.delete.assert_called_once()

    def test_delete_blob_not_found_ignored(self) -> None:
        """Test delete_blob with ignore_not_found=True (default)."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.delete.side_effect = NotFound("Not found")

        result = delete_blob(mock_client, "gs://bucket/missing.pdf")

        assert result is False

    def test_delete_blob_not_found_raises(self) -> None:
        """Test delete_blob with ignore_not_found=False."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.delete.side_effect = NotFound("Not found")

        with pytest.raises(GCSFileNotFoundError):
            delete_blob(mock_client, "gs://bucket/missing.pdf", ignore_not_found=False)

    def test_delete_blob_google_api_error(self) -> None:
        """Test delete_blob handles GoogleAPIError."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.delete.side_effect = GoogleAPIError("API error")

        with pytest.raises(StorageError) as exc_info:
            delete_blob(mock_client, "gs://bucket/file.pdf")

        assert "Failed to delete" in str(exc_info.value)

    def test_delete_blob_with_custom_retry(self) -> None:
        """Test delete_blob with custom retry config."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_retry = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        result = delete_blob(
            mock_client,
            "gs://bucket/file.pdf",
            retry_config=mock_retry,
        )

        assert result is True
        mock_blob.delete.assert_called_once_with(retry=mock_retry)


class TestFileExists:
    """Tests for file_exists function."""

    def test_file_exists_true(self) -> None:
        """Test file_exists returns True when file exists."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = True

        result = file_exists(mock_client, "gs://bucket/existing.pdf")

        assert result is True

    def test_file_exists_false(self) -> None:
        """Test file_exists returns False when file doesn't exist."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = False

        result = file_exists(mock_client, "gs://bucket/missing.pdf")

        assert result is False

    def test_file_exists_api_error_returns_false(self) -> None:
        """Test file_exists returns False on API error."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.side_effect = GoogleAPIError("API error")

        result = file_exists(mock_client, "gs://bucket/file.pdf")

        assert result is False


class TestUploadString:
    """Tests for upload_string function."""

    def test_upload_string_success(self) -> None:
        """Test successful string upload."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        upload_string(mock_client, "gs://bucket/test.txt", "Hello, World!")

        mock_blob.upload_from_string.assert_called_once_with(
            "Hello, World!", content_type="text/plain"
        )

    def test_upload_string_with_content_type(self) -> None:
        """Test string upload with custom content type."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        upload_string(
            mock_client,
            "gs://bucket/data.json",
            '{"key": "value"}',
            content_type="application/json",
        )

        mock_blob.upload_from_string.assert_called_once_with(
            '{"key": "value"}', content_type="application/json"
        )

    def test_upload_string_google_api_error(self) -> None:
        """Test upload_string handles GoogleAPIError."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.upload_from_string.side_effect = GoogleAPIError("API error")

        with pytest.raises(StorageError) as exc_info:
            upload_string(mock_client, "gs://bucket/test.txt", "content")

        assert "Failed to upload" in str(exc_info.value)


class TestDownloadAsBytes:
    """Tests for download_as_bytes function."""

    def test_download_as_bytes_success(self) -> None:
        """Test successful bytes download."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = True
        mock_blob.download_as_bytes.return_value = b"Hello, World!"

        result = download_as_bytes(mock_client, "gs://bucket/test.txt")

        assert result == b"Hello, World!"

    def test_download_as_bytes_not_found(self) -> None:
        """Test download_as_bytes raises FileNotFoundError when file missing."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = False

        with pytest.raises(GCSFileNotFoundError):
            download_as_bytes(mock_client, "gs://bucket/missing.txt")

    def test_download_as_bytes_not_found_exception(self) -> None:
        """Test download_as_bytes handles NotFound exception."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = True
        mock_blob.download_as_bytes.side_effect = NotFound("Not found")

        with pytest.raises(GCSFileNotFoundError):
            download_as_bytes(mock_client, "gs://bucket/missing.txt")

    def test_download_as_bytes_google_api_error(self) -> None:
        """Test download_as_bytes handles GoogleAPIError."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = True
        mock_blob.download_as_bytes.side_effect = GoogleAPIError("API error")

        with pytest.raises(StorageError) as exc_info:
            download_as_bytes(mock_client, "gs://bucket/file.txt")

        assert "Failed to download" in str(exc_info.value)


class TestListBlobs:
    """Tests for list_blobs function."""

    def test_list_blobs_success(self) -> None:
        """Test successful blob listing."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob1 = MagicMock()
        mock_blob2 = MagicMock()
        mock_blob1.name = "file1.pdf"
        mock_blob2.name = "file2.pdf"

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.list_blobs.return_value = [mock_blob1, mock_blob2]

        result = list_blobs(mock_client, "my-bucket")

        assert result == ["file1.pdf", "file2.pdf"]

    def test_list_blobs_with_prefix(self) -> None:
        """Test blob listing with prefix."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.name = "202501/test.pdf"

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.list_blobs.return_value = [mock_blob]

        result = list_blobs(mock_client, "my-bucket", prefix="202501/")

        mock_bucket.list_blobs.assert_called_once_with(prefix="202501/", max_results=None)
        assert result == ["202501/test.pdf"]

    def test_list_blobs_with_max_results(self) -> None:
        """Test blob listing with max_results."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.name = "file.pdf"

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.list_blobs.return_value = [mock_blob]

        result = list_blobs(mock_client, "my-bucket", max_results=10)

        mock_bucket.list_blobs.assert_called_once_with(prefix="", max_results=10)
        assert result == ["file.pdf"]

    def test_list_blobs_empty(self) -> None:
        """Test blob listing with no results."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.list_blobs.return_value = []

        result = list_blobs(mock_client, "my-bucket")

        assert result == []

    def test_list_blobs_google_api_error(self) -> None:
        """Test list_blobs handles GoogleAPIError."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.list_blobs.side_effect = GoogleAPIError("API error")

        with pytest.raises(StorageError) as exc_info:
            list_blobs(mock_client, "my-bucket")

        assert "Failed to list blobs" in str(exc_info.value)


class TestStorageClient:
    """Tests for StorageClient class."""

    def test_storage_client_init_with_client(self) -> None:
        """Test StorageClient initialization with existing client."""
        mock_client = MagicMock()

        storage_client = StorageClient(client=mock_client)

        assert storage_client.client == mock_client

    def test_storage_client_init_without_client(self) -> None:
        """Test StorageClient initialization without client."""
        with patch("src.core.storage.storage.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            storage_client = StorageClient()

            assert storage_client._client is not None

    def test_storage_client_copy_file(self) -> None:
        """Test StorageClient.copy_file method."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_source_blob = MagicMock()
        mock_dest_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_source_blob
        mock_source_blob.exists.return_value = True
        mock_dest_blob.rewrite.return_value = (None, 1000, 1000)

        # Configure mock to return different blobs for source and dest
        mock_client.bucket.side_effect = [mock_bucket, mock_bucket]
        mock_bucket.blob.side_effect = [mock_source_blob, mock_dest_blob]

        storage_client = StorageClient(client=mock_client)
        storage_client.copy_file(
            "gs://bucket/source.pdf",
            "gs://bucket/dest.pdf",
        )

        mock_dest_blob.rewrite.assert_called_once()

    def test_storage_client_delete_file(self) -> None:
        """Test StorageClient.delete_file method."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        storage_client = StorageClient(client=mock_client)
        result = storage_client.delete_file("gs://bucket/file.pdf")

        assert result is True
        mock_blob.delete.assert_called_once()

    def test_storage_client_delete_file_ignore_not_found(self) -> None:
        """Test StorageClient.delete_file with ignore_not_found."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.delete.side_effect = NotFound("Not found")

        storage_client = StorageClient(client=mock_client)
        result = storage_client.delete_file("gs://bucket/file.pdf", ignore_not_found=True)

        assert result is False

    def test_storage_client_file_exists(self) -> None:
        """Test StorageClient.file_exists method."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = True

        storage_client = StorageClient(client=mock_client)
        result = storage_client.file_exists("gs://bucket/file.pdf")

        assert result is True

    def test_storage_client_generate_destination_path(self) -> None:
        """Test StorageClient.generate_destination_path method."""
        mock_client = MagicMock()

        storage_client = StorageClient(client=mock_client)
        result = storage_client.generate_destination_path(
            {
                "management_id": "ID-001",
                "company_name": "Test Co",
                "issue_date": "2025-01-15",
            },
            datetime(2025, 1, 15, tzinfo=UTC),
            "output-bucket",
        )

        assert "gs://output-bucket/202501/" in result
        assert "ID-001" in result
        assert "Test Co" in result

    def test_storage_client_upload_string(self) -> None:
        """Test StorageClient.upload_string method."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob

        storage_client = StorageClient(client=mock_client)
        storage_client.upload_string("gs://bucket/test.txt", "content", "text/plain")

        mock_blob.upload_from_string.assert_called_once_with("content", content_type="text/plain")

    def test_storage_client_download_as_bytes(self) -> None:
        """Test StorageClient.download_as_bytes method."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()

        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        mock_blob.exists.return_value = True
        mock_blob.download_as_bytes.return_value = b"content"

        storage_client = StorageClient(client=mock_client)
        result = storage_client.download_as_bytes("gs://bucket/test.txt")

        assert result == b"content"


class TestDefaultRetry:
    """Tests for DEFAULT_RETRY configuration."""

    def test_default_retry_exists(self) -> None:
        """Test that DEFAULT_RETRY is defined."""
        assert DEFAULT_RETRY is not None
