"""
GCS Storage Operations.

Provides reliable file operations for the Saga pattern with proper
error handling and retry logic for transient failures.

See: docs/specs/03_saga.md
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from google.api_core import retry
    from google.api_core.exceptions import GoogleAPIError, NotFound
    from google.cloud import storage
else:
    try:
        from google.api_core import retry
        from google.api_core.exceptions import GoogleAPIError, NotFound
        from google.cloud import storage
    except ImportError:
        # Mock for testing without google-cloud-storage installed
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        class GoogleAPIError(Exception):  # type: ignore[no-redef]
            """Mock GoogleAPIError for testing."""

        class NotFoundError(Exception):  # type: ignore[no-redef]
            """Mock NotFound for testing."""

        NotFound = NotFoundError  # Alias to match google.api_core.exceptions

        storage = SimpleNamespace()  # type: ignore[assignment]
        storage.Client = MagicMock

        # Mock retry module
        retry = SimpleNamespace()  # type: ignore[assignment]
        retry.Retry = MagicMock
        retry.if_transient_error = MagicMock()

logger = structlog.get_logger(__name__)

# Default retry configuration for transient errors
DEFAULT_RETRY = retry.Retry(
    predicate=retry.if_transient_error,
    initial=1.0,
    maximum=60.0,
    multiplier=2.0,
    deadline=300.0,
)


class StorageError(Exception):
    """Base exception for storage operations."""

    pass


class InvalidGCSPathError(StorageError):
    """Raised when a GCS path is malformed."""

    def __init__(self, path: str, reason: str = "") -> None:
        self.path = path
        self.reason = reason
        message = f"Invalid GCS path: {path}"
        if reason:
            message += f" ({reason})"
        super().__init__(message)


class FileNotFoundError(StorageError):
    """Raised when a file is not found in GCS."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(f"File not found: {path}")


def parse_gcs_path(path: str) -> tuple[str, str]:
    """
    Parse a GCS URI into bucket name and blob path.

    Args:
        path: GCS URI in format gs://bucket/path/to/file

    Returns:
        Tuple of (bucket_name, blob_path)

    Raises:
        InvalidGCSPathError: If path format is invalid
    """
    if not path:
        raise InvalidGCSPathError(path, "empty path")

    if not path.startswith("gs://"):
        raise InvalidGCSPathError(path, "must start with gs://")

    # Remove gs:// prefix
    stripped = path[5:]

    if "/" not in stripped:
        raise InvalidGCSPathError(path, "missing blob path")

    parts = stripped.split("/", 1)
    bucket_name = parts[0]
    blob_path = parts[1] if len(parts) > 1 else ""

    if not bucket_name:
        raise InvalidGCSPathError(path, "empty bucket name")

    if not blob_path:
        raise InvalidGCSPathError(path, "empty blob path")

    return bucket_name, blob_path


def copy_blob(
    client: storage.Client,
    source_path: str,
    dest_path: str,
    retry_config: retry.Retry | None = None,
) -> None:
    """
    Copy a blob from source to destination.

    Uses rewrite API for large files (>5GB automatic handling).

    Args:
        client: GCS storage client
        source_path: Source GCS URI (gs://bucket/path/to/source)
        dest_path: Destination GCS URI (gs://bucket/path/to/dest)
        retry_config: Optional retry configuration

    Raises:
        FileNotFoundError: If source file does not exist
        StorageError: If copy operation fails
    """
    if retry_config is None:
        retry_config = DEFAULT_RETRY

    source_bucket_name, source_blob_name = parse_gcs_path(source_path)
    dest_bucket_name, dest_blob_name = parse_gcs_path(dest_path)

    logger.info(
        "gcs_copy_starting",
        source=source_path,
        dest=dest_path,
    )

    try:
        source_bucket = client.bucket(source_bucket_name)
        source_blob = source_bucket.blob(source_blob_name)

        # Check source exists
        if not source_blob.exists():
            raise FileNotFoundError(source_path)

        dest_bucket = client.bucket(dest_bucket_name)
        dest_blob = dest_bucket.blob(dest_blob_name)

        # Use rewrite for large files (handles >5GB automatically)
        rewrite_token = None
        while True:
            rewrite_token, bytes_rewritten, total_bytes = dest_blob.rewrite(
                source_blob, token=rewrite_token
            )
            if rewrite_token is None:
                break

            progress_pct = round(bytes_rewritten / total_bytes * 100, 1) if total_bytes > 0 else 0
            logger.debug(
                "gcs_copy_progress",
                bytes_rewritten=bytes_rewritten,
                total_bytes=total_bytes,
                progress_pct=progress_pct,
            )

        logger.info(
            "gcs_copy_completed",
            source=source_path,
            dest=dest_path,
        )

    except NotFound as e:
        raise FileNotFoundError(source_path) from e
    except GoogleAPIError as e:
        logger.error(
            "gcs_copy_failed",
            source=source_path,
            dest=dest_path,
            error=str(e),
        )
        raise StorageError(f"Failed to copy {source_path} to {dest_path}: {e}") from e


def delete_blob(
    client: storage.Client,
    path: str,
    ignore_not_found: bool = True,
    retry_config: retry.Retry | None = None,
) -> bool:
    """
    Delete a blob from GCS.

    Args:
        client: GCS storage client
        path: GCS URI (gs://bucket/path/to/blob)
        ignore_not_found: If True, don't raise on missing blob
        retry_config: Optional retry configuration

    Returns:
        True if file was deleted, False if not found (and ignore_not_found=True)

    Raises:
        FileNotFoundError: If file not found and ignore_not_found=False
        StorageError: If delete operation fails
    """
    if retry_config is None:
        retry_config = DEFAULT_RETRY

    bucket_name, blob_name = parse_gcs_path(path)

    logger.info("gcs_delete_starting", path=path)

    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete(retry=retry_config)

        logger.info("gcs_delete_completed", path=path)
        return True

    except NotFound as exc:
        if ignore_not_found:
            logger.info("gcs_delete_not_found", path=path)
            return False
        raise FileNotFoundError(path) from exc

    except GoogleAPIError as e:
        logger.error(
            "gcs_delete_failed",
            path=path,
            error=str(e),
        )
        raise StorageError(f"Failed to delete {path}: {e}") from e


def file_exists(client: storage.Client, path: str) -> bool:
    """
    Check if a file exists in GCS.

    Args:
        client: GCS storage client
        path: GCS URI (gs://bucket/path/to/blob)

    Returns:
        True if file exists, False otherwise
    """
    bucket_name, blob_name = parse_gcs_path(path)

    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        return blob.exists()

    except GoogleAPIError as e:
        logger.error(
            "gcs_exists_check_failed",
            path=path,
            error=str(e),
        )
        # On error, assume file doesn't exist
        return False


def generate_destination_path(
    schema_data: dict[str, Any],
    timestamp: datetime,
    output_bucket: str,
) -> str:
    """
    Generate destination path from schema data.

    Standard format: gs://bucket/YYYYMM/管理ID_会社名_YYYYMMDD.pdf
    Generic fallback: gs://bucket/YYYYMM/unknown/{document_id}_{YYYYMMDD}.pdf

    Args:
        schema_data: Validated extraction data
        timestamp: Processing timestamp for folder organization
        output_bucket: Target GCS bucket name

    Returns:
        Full GCS URI for destination
    """
    document_type = schema_data.get("document_type", "generic")
    folder = timestamp.strftime("%Y%m")
    date_str = timestamp.strftime("%Y%m%d")

    # Handle generic document type (fallback)
    if document_type == "generic":
        document_id = schema_data.get("document_id", "unknown")
        safe_id = _sanitize_filename(document_id, max_length=30)
        filename = f"{safe_id}_{date_str}.pdf"
        return f"gs://{output_bucket}/{folder}/unknown/{filename}"

    # Standard document types (delivery_note, invoice)
    management_id = schema_data.get("management_id") or schema_data.get("invoice_number")
    company_name = schema_data.get("company_name")
    issue_date = schema_data.get("issue_date")

    # Fallback to generic if required fields are missing
    if not management_id or not company_name:
        document_id = schema_data.get("document_id", "unknown")
        safe_id = _sanitize_filename(document_id or "unknown", max_length=30)
        filename = f"{safe_id}_{date_str}.pdf"
        return f"gs://{output_bucket}/{folder}/unknown/{filename}"

    # Sanitize filename components
    safe_management_id = _sanitize_filename(management_id)
    safe_company_name = _sanitize_filename(company_name)

    # Parse date for filename
    if issue_date:
        if isinstance(issue_date, str):
            date_str = issue_date.replace("-", "").replace("/", "")[:8]
        elif isinstance(issue_date, datetime):
            date_str = issue_date.strftime("%Y%m%d")
        else:
            date_str = str(issue_date).replace("-", "")[:8]

    # Construct filename
    filename = f"{safe_management_id}_{safe_company_name}_{date_str}.pdf"

    return f"gs://{output_bucket}/{folder}/{filename}"


def _sanitize_filename(value: str, max_length: int = 50) -> str:
    """
    Sanitize a string for use in filenames.

    - Replaces invalid characters with underscores
    - Truncates to max_length
    - Removes leading/trailing whitespace and underscores

    Args:
        value: String to sanitize
        max_length: Maximum length of result

    Returns:
        Sanitized string safe for filenames
    """
    # Replace characters that are problematic in filenames
    # Keep alphanumeric, Japanese characters, hyphens, underscores
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)

    # Replace multiple consecutive underscores
    sanitized = re.sub(r"_+", "_", sanitized)

    # Strip whitespace and underscores from ends
    sanitized = sanitized.strip().strip("_")

    # Truncate if needed
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].rstrip("_")

    return sanitized


def upload_string(
    client: storage.Client,
    path: str,
    content: str,
    content_type: str = "text/plain",
) -> None:
    """
    Upload a string as a blob.

    Args:
        client: GCS storage client
        path: GCS URI for destination
        content: String content to upload
        content_type: MIME type for the content
    """
    bucket_name, blob_name = parse_gcs_path(path)

    logger.info(
        "gcs_upload_starting",
        path=path,
        content_type=content_type,
        size=len(content),
    )

    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(content, content_type=content_type)

        logger.info("gcs_upload_completed", path=path)

    except GoogleAPIError as e:
        logger.error(
            "gcs_upload_failed",
            path=path,
            error=str(e),
        )
        raise StorageError(f"Failed to upload to {path}: {e}") from e


def download_as_bytes(client: storage.Client, path: str) -> bytes:
    """
    Download a blob as bytes.

    Args:
        client: GCS storage client
        path: GCS URI of the file

    Returns:
        File content as bytes

    Raises:
        FileNotFoundError: If file does not exist
        StorageError: If download fails
    """
    bucket_name, blob_name = parse_gcs_path(path)

    logger.info("gcs_download_starting", path=path)

    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        if not blob.exists():
            raise FileNotFoundError(path)

        content = blob.download_as_bytes()

        logger.info(
            "gcs_download_completed",
            path=path,
            size=len(content),
        )
        return content

    except NotFound as e:
        raise FileNotFoundError(path) from e
    except GoogleAPIError as e:
        logger.error(
            "gcs_download_failed",
            path=path,
            error=str(e),
        )
        raise StorageError(f"Failed to download {path}: {e}") from e


def list_blobs(
    client: storage.Client,
    bucket_name: str,
    prefix: str = "",
    max_results: int | None = None,
) -> list[str]:
    """
    List blobs in a bucket with optional prefix filter.

    Args:
        client: GCS storage client
        bucket_name: Name of the bucket
        prefix: Optional prefix to filter blobs
        max_results: Maximum number of results to return

    Returns:
        List of blob names (not full paths)
    """
    try:
        bucket = client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix=prefix, max_results=max_results)
        return [blob.name for blob in blobs]

    except GoogleAPIError as e:
        logger.error(
            "gcs_list_failed",
            bucket=bucket_name,
            prefix=prefix,
            error=str(e),
        )
        raise StorageError(f"Failed to list blobs in {bucket_name}: {e}") from e


class StorageClient:
    """
    High-level storage client wrapping GCS operations.

    Provides a cleaner interface for the most common operations.
    """

    def __init__(self, client: storage.Client | None = None) -> None:
        """
        Initialize storage client.

        Args:
            client: Optional GCS client. If not provided, creates a new one.
        """
        self._client = client or storage.Client()

    @property
    def client(self) -> storage.Client:
        """Get the underlying GCS client."""
        return self._client

    def copy_file(self, source_uri: str, dest_uri: str) -> None:
        """Copy a file from source to destination."""
        copy_blob(self._client, source_uri, dest_uri)

    def delete_file(self, uri: str, ignore_not_found: bool = True) -> bool:
        """Delete a file."""
        return delete_blob(self._client, uri, ignore_not_found=ignore_not_found)

    def file_exists(self, uri: str) -> bool:
        """Check if a file exists."""
        return file_exists(self._client, uri)

    def generate_destination_path(
        self,
        schema_data: dict[str, Any],
        timestamp: datetime,
        output_bucket: str,
    ) -> str:
        """Generate destination path from schema data."""
        return generate_destination_path(schema_data, timestamp, output_bucket)

    def upload_string(
        self,
        uri: str,
        content: str,
        content_type: str = "text/plain",
    ) -> None:
        """Upload a string as a blob."""
        upload_string(self._client, uri, content, content_type)

    def download_as_bytes(self, uri: str) -> bytes:
        """Download a blob as bytes."""
        return download_as_bytes(self._client, uri)
