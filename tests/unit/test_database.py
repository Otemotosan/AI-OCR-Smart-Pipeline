"""
Unit tests for Database Client.

See: docs/specs/07_monitoring.md, docs/specs/11_conflict.md
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from unittest.mock import Mock

# Mock Google Cloud modules before importing database
sys.modules["google.cloud"] = Mock()
sys.modules["google.cloud.firestore"] = Mock()
sys.modules["google.api_core"] = Mock()
sys.modules["google.api_core.exceptions"] = Mock()

# Create mock exceptions
NotFound = type("NotFound", (Exception,), {})
GoogleAPIError = type("GoogleAPIError", (Exception,), {})
sys.modules["google.api_core.exceptions"].NotFound = NotFound
sys.modules["google.api_core.exceptions"].GoogleAPIError = GoogleAPIError

from src.core.database import (  # noqa: E402
    AuditEventType,
    AuditLogEntry,
    DatabaseError,
    DocumentNotFoundError,
    DocumentRecord,
    DocumentStatus,
    OptimisticLockError,
)


class TestDocumentStatus:
    """Tests for DocumentStatus enum."""

    def test_status_values(self) -> None:
        """Test all status values exist."""
        assert DocumentStatus.PENDING.value == "PENDING"
        assert DocumentStatus.PROCESSING.value == "PROCESSING"
        assert DocumentStatus.COMPLETED.value == "COMPLETED"
        assert DocumentStatus.FAILED.value == "FAILED"
        assert DocumentStatus.QUARANTINED.value == "QUARANTINED"


class TestAuditEventType:
    """Tests for AuditEventType enum."""

    def test_event_type_values(self) -> None:
        """Test all event type values exist."""
        assert AuditEventType.CREATED.value == "CREATED"
        assert AuditEventType.EXTRACTED.value == "EXTRACTED"
        assert AuditEventType.CORRECTED.value == "CORRECTED"
        assert AuditEventType.APPROVED.value == "APPROVED"
        assert AuditEventType.FAILED.value == "FAILED"


class TestDocumentRecord:
    """Tests for DocumentRecord dataclass."""

    def test_create_record(self) -> None:
        """Test creating a DocumentRecord."""
        now = datetime.now(UTC)
        record = DocumentRecord(
            document_id="test-hash",
            status=DocumentStatus.PENDING,
            source_uri="gs://bucket/file.pdf",
            created_at=now,
            updated_at=now,
        )

        assert record.document_id == "test-hash"
        assert record.status == DocumentStatus.PENDING
        assert record.source_uri == "gs://bucket/file.pdf"

    def test_record_to_dict(self) -> None:
        """Test converting record to dictionary."""
        now = datetime.now(UTC)
        record = DocumentRecord(
            document_id="test-hash",
            status=DocumentStatus.COMPLETED,
            source_uri="gs://bucket/file.pdf",
            destination_uri="gs://bucket/output/file.pdf",
            extracted_data={"management_id": "TEST-001"},
            created_at=now,
            updated_at=now,
        )

        data = record.to_dict()

        assert data["document_id"] == "test-hash"
        assert data["status"] == "COMPLETED"
        assert data["extracted_data"] == {"management_id": "TEST-001"}

    def test_record_from_dict(self) -> None:
        """Test creating record from dictionary."""
        now = datetime.now(UTC)
        data = {
            "document_id": "test-hash",
            "status": "PROCESSING",
            "source_uri": "gs://bucket/file.pdf",
            "created_at": now,
            "updated_at": now,
            "extracted_data": {},
        }

        record = DocumentRecord.from_dict(data)

        assert record.document_id == "test-hash"
        assert record.status == DocumentStatus.PROCESSING

    def test_record_from_dict_with_invalid_status(self) -> None:
        """Test record creation with invalid status defaults to PENDING."""
        now = datetime.now(UTC)
        data = {
            "document_id": "test-hash",
            "status": "INVALID_STATUS",
            "source_uri": "gs://bucket/file.pdf",
            "created_at": now,
            "updated_at": now,
        }

        record = DocumentRecord.from_dict(data)

        assert record.status == DocumentStatus.PENDING


class TestAuditLogEntry:
    """Tests for AuditLogEntry dataclass."""

    def test_create_entry(self) -> None:
        """Test creating an AuditLogEntry."""
        now = datetime.now(UTC)
        entry = AuditLogEntry(
            document_id="test-hash",
            event=AuditEventType.CORRECTED,
            timestamp=now,
            details={"before": "old", "after": "new"},
            user_id="user-123",
        )

        assert entry.document_id == "test-hash"
        assert entry.event == AuditEventType.CORRECTED
        assert entry.user_id == "user-123"

    def test_entry_to_dict(self) -> None:
        """Test converting entry to dictionary."""
        now = datetime.now(UTC)
        entry = AuditLogEntry(
            document_id="test-hash",
            event=AuditEventType.CREATED,
            timestamp=now,
        )

        data = entry.to_dict()

        assert data["document_id"] == "test-hash"
        assert data["event"] == "CREATED"


class TestOptimisticLocking:
    """Tests for optimistic locking functionality."""

    def test_optimistic_lock_error_message(self) -> None:
        """Test OptimisticLockError message format."""
        expected = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        actual = datetime(2025, 1, 15, 10, 5, 0, tzinfo=UTC)

        error = OptimisticLockError("test-hash", expected, actual)

        assert error.doc_id == "test-hash"
        assert error.expected_updated_at == expected
        assert error.actual_updated_at == actual
        assert "modified by another user" in str(error)


class TestDocumentNotFoundError:
    """Tests for DocumentNotFoundError."""

    def test_error_message(self) -> None:
        """Test error message format."""
        error = DocumentNotFoundError("missing-hash")

        assert error.doc_id == "missing-hash"
        assert "missing-hash" in str(error)
        assert "not found" in str(error).lower()


class TestDatabaseError:
    """Tests for DatabaseError base exception."""

    def test_database_error(self) -> None:
        """Test basic DatabaseError."""
        error = DatabaseError("Test error message")

        assert "Test error message" in str(error)
