"""
Unit tests for Database Client.

See: docs/specs/07_monitoring.md, docs/specs/11_conflict.md
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from src.core.database import (
    AuditEventType,
    AuditLogEntry,
    DatabaseClient,
    DatabaseError,
    DocumentNotFoundError,
    DocumentRecord,
    DocumentStatus,
    GoogleAPIError,
    NotFound,
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


# ============================================================
# DatabaseClient Tests
# ============================================================


class TestDatabaseClientInit:
    """Tests for DatabaseClient initialization."""

    def test_init_with_client(self) -> None:
        """Test initialization with provided client."""
        mock_client = MagicMock()
        db = DatabaseClient(client=mock_client)

        assert db.client is mock_client

    def test_collection_constants(self) -> None:
        """Test collection name constants."""
        assert DatabaseClient.DOCUMENTS_COLLECTION == "processed_documents"
        assert DatabaseClient.AUDIT_LOG_COLLECTION == "audit_log"
        assert DatabaseClient.DRAFTS_COLLECTION == "drafts"


class TestCreateDocument:
    """Tests for create_document method."""

    def test_create_document_success(self) -> None:
        """Test successful document creation."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = DatabaseClient(client=mock_client)
        record = db.create_document(
            doc_id="sha256:abc123",
            source_uri="gs://bucket/file.pdf",
        )

        assert record.document_id == "sha256:abc123"
        assert record.status == DocumentStatus.PENDING
        assert record.source_uri == "gs://bucket/file.pdf"
        mock_doc_ref.set.assert_called_once()

    def test_create_document_with_status(self) -> None:
        """Test document creation with custom status."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = DatabaseClient(client=mock_client)
        record = db.create_document(
            doc_id="sha256:abc123",
            source_uri="gs://bucket/file.pdf",
            status=DocumentStatus.PROCESSING,
        )

        assert record.status == DocumentStatus.PROCESSING

    def test_create_document_api_error(self) -> None:
        """Test document creation handles API errors."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_ref.set.side_effect = GoogleAPIError("API error")
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = DatabaseClient(client=mock_client)

        with pytest.raises(DatabaseError) as exc_info:
            db.create_document(
                doc_id="sha256:abc123",
                source_uri="gs://bucket/file.pdf",
            )

        assert "Failed to create document" in str(exc_info.value)


class TestGetDocument:
    """Tests for get_document method."""

    def test_get_document_success(self) -> None:
        """Test successful document retrieval."""
        mock_client = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "document_id": "sha256:abc123",
            "status": "COMPLETED",
            "source_uri": "gs://bucket/file.pdf",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

        db = DatabaseClient(client=mock_client)
        record = db.get_document("sha256:abc123")

        assert record is not None
        assert record.document_id == "sha256:abc123"
        assert record.status == DocumentStatus.COMPLETED

    def test_get_document_not_found(self) -> None:
        """Test document retrieval when not found."""
        mock_client = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

        db = DatabaseClient(client=mock_client)
        record = db.get_document("sha256:nonexistent")

        assert record is None

    def test_get_document_api_error(self) -> None:
        """Test document retrieval handles API errors."""
        mock_client = MagicMock()
        mock_client.collection.return_value.document.return_value.get.side_effect = (
            GoogleAPIError("API error")
        )

        db = DatabaseClient(client=mock_client)
        record = db.get_document("sha256:abc123")

        assert record is None


class TestUpdateStatus:
    """Tests for update_status method."""

    def test_update_status_success(self) -> None:
        """Test successful status update."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = DatabaseClient(client=mock_client)
        db.update_status("sha256:abc123", DocumentStatus.COMPLETED)

        mock_doc_ref.update.assert_called_once()
        call_args = mock_doc_ref.update.call_args[0][0]
        assert call_args["status"] == "COMPLETED"
        assert "processed_at" in call_args

    def test_update_status_failed_with_message(self) -> None:
        """Test status update to FAILED with error message."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = DatabaseClient(client=mock_client)
        db.update_status(
            "sha256:abc123",
            DocumentStatus.FAILED,
            error_message="Extraction failed",
        )

        call_args = mock_doc_ref.update.call_args[0][0]
        assert call_args["status"] == "FAILED"
        assert call_args["error_message"] == "Extraction failed"

    def test_update_status_not_found(self) -> None:
        """Test status update when document not found."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_ref.update.side_effect = NotFound("Not found")
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = DatabaseClient(client=mock_client)

        with pytest.raises(DocumentNotFoundError):
            db.update_status("sha256:abc123", DocumentStatus.COMPLETED)

    def test_update_status_api_error(self) -> None:
        """Test status update handles API errors."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_ref.update.side_effect = GoogleAPIError("API error")
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = DatabaseClient(client=mock_client)

        with pytest.raises(DatabaseError):
            db.update_status("sha256:abc123", DocumentStatus.COMPLETED)


class TestSaveExtraction:
    """Tests for save_extraction method."""

    def test_save_extraction_success(self) -> None:
        """Test successful extraction save."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = DatabaseClient(client=mock_client)
        db.save_extraction(
            doc_id="sha256:abc123",
            extracted_data={"management_id": "DN-001"},
            attempts=[{"model": "flash", "success": True}],
            schema_version="v1",
            quality_warnings=["missing_field"],
        )

        mock_doc_ref.update.assert_called_once()
        call_args = mock_doc_ref.update.call_args[0][0]
        assert call_args["extracted_data"] == {"management_id": "DN-001"}
        assert call_args["schema_version"] == "v1"
        assert call_args["quality_warnings"] == ["missing_field"]

    def test_save_extraction_not_found(self) -> None:
        """Test extraction save when document not found."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_ref.update.side_effect = NotFound("Not found")
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = DatabaseClient(client=mock_client)

        with pytest.raises(DocumentNotFoundError):
            db.save_extraction(
                doc_id="sha256:abc123",
                extracted_data={},
                attempts=[],
                schema_version="v1",
            )

    def test_save_extraction_api_error(self) -> None:
        """Test extraction save handles API errors."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_ref.update.side_effect = GoogleAPIError("API error")
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = DatabaseClient(client=mock_client)

        with pytest.raises(DatabaseError):
            db.save_extraction(
                doc_id="sha256:abc123",
                extracted_data={},
                attempts=[],
                schema_version="v1",
            )


class TestLogAuditEvent:
    """Tests for log_audit_event method."""

    def test_log_audit_event_success(self) -> None:
        """Test successful audit event logging."""
        mock_client = MagicMock()

        db = DatabaseClient(client=mock_client)
        db.log_audit_event(
            doc_id="sha256:abc123",
            event=AuditEventType.CREATED,
            details={"source_uri": "gs://bucket/file.pdf"},
            user_id="user@example.com",
        )

        mock_client.collection.return_value.add.assert_called_once()
        call_args = mock_client.collection.return_value.add.call_args[0][0]
        assert call_args["document_id"] == "sha256:abc123"
        assert call_args["event"] == "CREATED"
        assert call_args["user_id"] == "user@example.com"

    def test_log_audit_event_api_error_does_not_raise(self) -> None:
        """Test audit event logging handles API errors gracefully."""
        mock_client = MagicMock()
        mock_client.collection.return_value.add.side_effect = GoogleAPIError("API error")

        db = DatabaseClient(client=mock_client)
        # Should not raise - audit logging shouldn't break main flow
        db.log_audit_event(
            doc_id="sha256:abc123",
            event=AuditEventType.CREATED,
            details={},
        )


class TestGetAuditLog:
    """Tests for get_audit_log method."""

    def test_get_audit_log_success(self) -> None:
        """Test successful audit log retrieval."""
        mock_client = MagicMock()
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            "document_id": "sha256:abc123",
            "event": "CREATED",
            "timestamp": datetime.now(UTC),
            "details": {},
        }
        mock_query = MagicMock()
        mock_query.stream.return_value = [mock_doc]
        mock_client.collection.return_value.where.return_value.order_by.return_value = mock_query

        db = DatabaseClient(client=mock_client)
        entries = db.get_audit_log("sha256:abc123")

        assert len(entries) == 1
        assert entries[0].document_id == "sha256:abc123"

    def test_get_audit_log_empty(self) -> None:
        """Test audit log retrieval with no entries."""
        mock_client = MagicMock()
        mock_query = MagicMock()
        mock_query.stream.return_value = []
        mock_client.collection.return_value.where.return_value.order_by.return_value = mock_query

        db = DatabaseClient(client=mock_client)
        entries = db.get_audit_log("sha256:abc123")

        assert entries == []

    def test_get_audit_log_api_error(self) -> None:
        """Test audit log retrieval handles API errors."""
        mock_client = MagicMock()
        mock_stream = mock_client.collection.return_value.where.return_value
        mock_stream.order_by.return_value.stream.side_effect = GoogleAPIError(
            "API error"
        )

        db = DatabaseClient(client=mock_client)
        entries = db.get_audit_log("sha256:abc123")

        assert entries == []


class TestListDocuments:
    """Tests for list_documents method."""

    def test_list_documents_success(self) -> None:
        """Test successful document listing."""
        mock_client = MagicMock()
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            "document_id": "sha256:abc123",
            "status": "COMPLETED",
            "source_uri": "gs://bucket/file.pdf",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        mock_query = MagicMock()
        mock_chain = mock_query.order_by.return_value.limit.return_value
        mock_chain.offset.return_value.stream.return_value = [mock_doc]
        mock_client.collection.return_value = mock_query

        db = DatabaseClient(client=mock_client)
        records = db.list_documents()

        assert len(records) == 1
        assert records[0].document_id == "sha256:abc123"

    def test_list_documents_with_status_filter(self) -> None:
        """Test document listing with status filter."""
        mock_client = MagicMock()
        mock_query = MagicMock()
        mock_chain = mock_query.where.return_value.order_by.return_value
        mock_chain.limit.return_value.offset.return_value.stream.return_value = []
        mock_client.collection.return_value = mock_query

        db = DatabaseClient(client=mock_client)
        db.list_documents(status=DocumentStatus.PENDING)

        mock_query.where.assert_called_once_with("status", "==", "PENDING")

    def test_list_documents_api_error(self) -> None:
        """Test document listing handles API errors."""
        mock_client = MagicMock()
        mock_chain = mock_client.collection.return_value.order_by.return_value
        mock_chain.limit.return_value.offset.return_value.stream.side_effect = (
            GoogleAPIError("API error")
        )

        db = DatabaseClient(client=mock_client)
        records = db.list_documents()

        assert records == []


class TestDraftOperations:
    """Tests for draft operations."""

    def test_save_draft_success(self) -> None:
        """Test successful draft save."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = DatabaseClient(client=mock_client)
        db.save_draft(
            doc_id="sha256:abc123",
            draft_data={"management_id": "DN-001"},
            user_id="user@example.com",
        )

        mock_doc_ref.set.assert_called_once()
        call_args = mock_doc_ref.set.call_args[0][0]
        assert call_args["document_id"] == "sha256:abc123"
        assert call_args["user_id"] == "user@example.com"
        assert call_args["draft_data"] == {"management_id": "DN-001"}

    def test_save_draft_api_error_does_not_raise(self) -> None:
        """Test draft save handles API errors gracefully."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_ref.set.side_effect = GoogleAPIError("API error")
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = DatabaseClient(client=mock_client)
        # Should not raise
        db.save_draft(
            doc_id="sha256:abc123",
            draft_data={},
            user_id="user@example.com",
        )

    def test_get_draft_success(self) -> None:
        """Test successful draft retrieval."""
        mock_client = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"draft_data": {"management_id": "DN-001"}}
        mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

        db = DatabaseClient(client=mock_client)
        draft = db.get_draft("sha256:abc123", "user@example.com")

        assert draft == {"management_id": "DN-001"}

    def test_get_draft_not_found(self) -> None:
        """Test draft retrieval when not found."""
        mock_client = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_client.collection.return_value.document.return_value.get.return_value = mock_doc

        db = DatabaseClient(client=mock_client)
        draft = db.get_draft("sha256:abc123", "user@example.com")

        assert draft is None

    def test_get_draft_api_error(self) -> None:
        """Test draft retrieval handles API errors."""
        mock_client = MagicMock()
        mock_client.collection.return_value.document.return_value.get.side_effect = (
            GoogleAPIError("API error")
        )

        db = DatabaseClient(client=mock_client)
        draft = db.get_draft("sha256:abc123", "user@example.com")

        assert draft is None

    def test_delete_draft_success(self) -> None:
        """Test successful draft deletion."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = DatabaseClient(client=mock_client)
        db.delete_draft("sha256:abc123", "user@example.com")

        mock_doc_ref.delete.assert_called_once()

    def test_delete_draft_api_error_does_not_raise(self) -> None:
        """Test draft deletion handles API errors gracefully."""
        mock_client = MagicMock()
        mock_doc_ref = MagicMock()
        mock_doc_ref.delete.side_effect = GoogleAPIError("API error")
        mock_client.collection.return_value.document.return_value = mock_doc_ref

        db = DatabaseClient(client=mock_client)
        # Should not raise
        db.delete_draft("sha256:abc123", "user@example.com")


class TestDocumentRecordTimestampHandling:
    """Tests for DocumentRecord timestamp handling."""

    def test_from_dict_with_firestore_timestamp(self) -> None:
        """Test creating record from dict with Firestore timestamps."""
        mock_timestamp = MagicMock()
        mock_timestamp.timestamp.return_value = 1705312800.0  # 2024-01-15 10:00:00

        data = {
            "document_id": "test-hash",
            "status": "COMPLETED",
            "source_uri": "gs://bucket/file.pdf",
            "created_at": mock_timestamp,
            "updated_at": mock_timestamp,
            "processed_at": mock_timestamp,
        }

        record = DocumentRecord.from_dict(data)

        assert record.document_id == "test-hash"
        assert record.created_at is not None
        assert record.processed_at is not None


class TestAuditLogEntryEventHandling:
    """Tests for AuditLogEntry event handling."""

    def test_entry_with_invalid_event_defaults(self) -> None:
        """Test that get_audit_log handles invalid event types."""
        mock_client = MagicMock()
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {
            "document_id": "sha256:abc123",
            "event": "INVALID_EVENT",
            "timestamp": datetime.now(UTC),
            "details": {},
        }
        mock_query = MagicMock()
        mock_query.stream.return_value = [mock_doc]
        mock_client.collection.return_value.where.return_value.order_by.return_value = mock_query

        db = DatabaseClient(client=mock_client)
        entries = db.get_audit_log("sha256:abc123")

        assert len(entries) == 1
        assert entries[0].event == AuditEventType.CREATED  # Default
