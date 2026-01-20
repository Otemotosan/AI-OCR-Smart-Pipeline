"""
Database Client for Firestore.

Handles document persistence, status tracking, and audit logging
with optimistic locking for concurrent edit control.

See: docs/specs/07_monitoring.md, docs/specs/11_conflict.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from google.api_core.exceptions import GoogleAPIError, NotFound
    from google.cloud import firestore
else:
    try:
        from google.api_core.exceptions import GoogleAPIError, NotFound
        from google.cloud import firestore
    except ImportError:
        # Mock for testing without google-cloud-firestore installed
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        class GoogleAPIError(Exception):  # type: ignore[no-redef]
            """Mock GoogleAPIError for testing."""

        class NotFoundError(Exception):  # type: ignore[no-redef]
            """Mock NotFound for testing."""

        NotFound = NotFoundError  # Alias to match google.api_core.exceptions

        firestore = SimpleNamespace()  # type: ignore[assignment]
        firestore.Client = MagicMock
        firestore.Query = SimpleNamespace(DESCENDING="DESCENDING")
        firestore.Transaction = MagicMock
        firestore.transactional = lambda f: f

logger = structlog.get_logger(__name__)


class DocumentStatus(str, Enum):
    """Document processing status values."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


class AuditEventType(str, Enum):
    """Audit log event types."""

    CREATED = "CREATED"
    EXTRACTED = "EXTRACTED"
    VALIDATED = "VALIDATED"
    CORRECTED = "CORRECTED"
    APPROVED = "APPROVED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


class DatabaseError(Exception):
    """Base exception for database operations."""

    pass


class DocumentNotFoundError(DatabaseError):
    """Raised when a document is not found."""

    def __init__(self, doc_id: str) -> None:
        self.doc_id = doc_id
        super().__init__(f"Document not found: {doc_id}")


class OptimisticLockError(DatabaseError):
    """Raised when optimistic locking detects a conflict."""

    def __init__(
        self,
        doc_id: str,
        expected_updated_at: datetime,
        actual_updated_at: datetime,
    ) -> None:
        self.doc_id = doc_id
        self.expected_updated_at = expected_updated_at
        self.actual_updated_at = actual_updated_at
        super().__init__(
            f"Document {doc_id} was modified by another user. "
            f"Expected updated_at: {expected_updated_at}, "
            f"Actual: {actual_updated_at}"
        )


@dataclass
class DocumentRecord:
    """
    Represents a document in the database.

    Schema for `processed_documents` collection:
    - document_id: str (SHA-256 hash)
    - status: str (PENDING/PROCESSING/COMPLETED/FAILED)
    - source_uri: str
    - destination_uri: str | None
    - extracted_data: dict (JSON)
    - attempts: list[dict]
    - quality_warnings: list[str]
    - created_at: datetime
    - updated_at: datetime
    - processed_at: datetime | None
    """

    document_id: str
    status: DocumentStatus
    source_uri: str
    created_at: datetime
    updated_at: datetime
    destination_uri: str | None = None
    extracted_data: dict[str, Any] = field(default_factory=dict)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    quality_warnings: list[str] = field(default_factory=list)
    processed_at: datetime | None = None
    schema_version: str | None = None
    error_message: str | None = None
    quarantine_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Firestore."""
        return {
            "document_id": self.document_id,
            "status": self.status.value if isinstance(self.status, DocumentStatus) else self.status,
            "source_uri": self.source_uri,
            "destination_uri": self.destination_uri,
            "extracted_data": self.extracted_data,
            "attempts": self.attempts,
            "quality_warnings": self.quality_warnings,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "processed_at": self.processed_at,
            "schema_version": self.schema_version,
            "error_message": self.error_message,
            "quarantine_path": self.quarantine_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocumentRecord:
        """Create from Firestore document data."""
        # Handle Firestore timestamp conversion
        created_at = data.get("created_at")
        if hasattr(created_at, "timestamp"):
            created_at = datetime.fromtimestamp(created_at.timestamp(), tz=UTC)

        updated_at = data.get("updated_at")
        if hasattr(updated_at, "timestamp"):
            updated_at = datetime.fromtimestamp(updated_at.timestamp(), tz=UTC)

        processed_at = data.get("processed_at")
        if processed_at and hasattr(processed_at, "timestamp"):
            processed_at = datetime.fromtimestamp(processed_at.timestamp(), tz=UTC)

        status = data.get("status", "PENDING")
        if isinstance(status, str):
            try:
                status = DocumentStatus(status)
            except ValueError:
                status = DocumentStatus.PENDING

        return cls(
            document_id=data.get("document_id", ""),
            status=status,
            source_uri=data.get("source_uri", ""),
            destination_uri=data.get("destination_uri"),
            extracted_data=data.get("extracted_data", {}),
            attempts=data.get("attempts", []),
            quality_warnings=data.get("quality_warnings", []),
            created_at=created_at or datetime.now(UTC),
            updated_at=updated_at or datetime.now(UTC),
            processed_at=processed_at,
            schema_version=data.get("schema_version"),
            error_message=data.get("error_message"),
            quarantine_path=data.get("quarantine_path"),
        )


@dataclass
class AuditLogEntry:
    """
    Represents an audit log entry.

    Schema for `audit_log` collection:
    - document_id: str
    - event: str
    - details: dict
    - user_id: str | None
    - timestamp: datetime
    """

    document_id: str
    event: AuditEventType
    timestamp: datetime
    details: dict[str, Any] = field(default_factory=dict)
    user_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Firestore."""
        return {
            "document_id": self.document_id,
            "event": self.event.value if isinstance(self.event, AuditEventType) else self.event,
            "timestamp": self.timestamp,
            "details": self.details,
            "user_id": self.user_id,
        }


class DatabaseClient:
    """
    High-level database client for Firestore operations.

    Handles CRUD operations for documents and audit logging
    with optimistic locking support.
    """

    DOCUMENTS_COLLECTION = "processed_documents"
    AUDIT_LOG_COLLECTION = "audit_log"
    DRAFTS_COLLECTION = "drafts"

    def __init__(self, client: firestore.Client | None = None) -> None:
        """
        Initialize database client.

        Args:
            client: Optional Firestore client. If not provided, creates a new one.
        """
        self._client = client or firestore.Client()

    @property
    def client(self) -> firestore.Client:
        """Get the underlying Firestore client."""
        return self._client

    def create_document(
        self,
        doc_id: str,
        source_uri: str,
        status: DocumentStatus = DocumentStatus.PENDING,
    ) -> DocumentRecord:
        """
        Create a new document record.

        Args:
            doc_id: Document hash (SHA-256)
            source_uri: Source GCS URI
            status: Initial status (default: PENDING)

        Returns:
            Created DocumentRecord

        Raises:
            DatabaseError: If creation fails
        """
        now = datetime.now(UTC)

        record = DocumentRecord(
            document_id=doc_id,
            status=status,
            source_uri=source_uri,
            created_at=now,
            updated_at=now,
        )

        try:
            doc_ref = self._client.collection(self.DOCUMENTS_COLLECTION).document(doc_id)
            doc_ref.set(record.to_dict())

            logger.info(
                "document_created",
                doc_id=doc_id,
                source_uri=source_uri,
                status=status.value,
            )

            # Log audit event
            self.log_audit_event(doc_id, AuditEventType.CREATED, {"source_uri": source_uri})

            return record

        except GoogleAPIError as e:
            logger.error(
                "document_create_failed",
                doc_id=doc_id,
                error=str(e),
            )
            raise DatabaseError(f"Failed to create document {doc_id}: {e}") from e

    def get_document(self, doc_id: str) -> DocumentRecord | None:
        """
        Get a document by ID.

        Args:
            doc_id: Document hash

        Returns:
            DocumentRecord if found, None otherwise
        """
        try:
            doc_ref = self._client.collection(self.DOCUMENTS_COLLECTION).document(doc_id)
            doc = doc_ref.get()

            if not doc.exists:
                return None

            return DocumentRecord.from_dict(doc.to_dict())

        except GoogleAPIError as e:
            logger.error(
                "document_get_failed",
                doc_id=doc_id,
                error=str(e),
            )
            return None

    def update_status(
        self,
        doc_id: str,
        status: DocumentStatus,
        error_message: str | None = None,
    ) -> None:
        """
        Update document status.

        Args:
            doc_id: Document hash
            status: New status
            error_message: Optional error message for FAILED status

        Raises:
            DocumentNotFoundError: If document not found
            DatabaseError: If update fails
        """
        try:
            doc_ref = self._client.collection(self.DOCUMENTS_COLLECTION).document(doc_id)

            update_data: dict[str, Any] = {
                "status": status.value,
                "updated_at": datetime.now(UTC),
            }

            if status == DocumentStatus.COMPLETED:
                update_data["processed_at"] = datetime.now(UTC)

            if error_message:
                update_data["error_message"] = error_message

            doc_ref.update(update_data)

            logger.info(
                "document_status_updated",
                doc_id=doc_id,
                status=status.value,
            )

        except NotFound as e:
            raise DocumentNotFoundError(doc_id) from e
        except GoogleAPIError as e:
            logger.error(
                "document_status_update_failed",
                doc_id=doc_id,
                status=status.value,
                error=str(e),
            )
            raise DatabaseError(f"Failed to update status for {doc_id}: {e}") from e

    def save_extraction(
        self,
        doc_id: str,
        extracted_data: dict[str, Any],
        attempts: list[dict[str, Any]],
        schema_version: str,
        quality_warnings: list[str] | None = None,
    ) -> None:
        """
        Save extraction results to document.

        Args:
            doc_id: Document hash
            extracted_data: Validated extraction data
            attempts: List of extraction attempts
            schema_version: Schema version string
            quality_warnings: Optional list of quality warnings

        Raises:
            DocumentNotFoundError: If document not found
            DatabaseError: If save fails
        """
        try:
            doc_ref = self._client.collection(self.DOCUMENTS_COLLECTION).document(doc_id)

            update_data = {
                "extracted_data": extracted_data,
                "attempts": attempts,
                "schema_version": schema_version,
                "updated_at": datetime.now(UTC),
            }

            if quality_warnings is not None:
                update_data["quality_warnings"] = quality_warnings

            doc_ref.update(update_data)

            logger.info(
                "document_extraction_saved",
                doc_id=doc_id,
                schema_version=schema_version,
                attempts_count=len(attempts),
            )

            # Log audit event
            self.log_audit_event(
                doc_id,
                AuditEventType.EXTRACTED,
                {
                    "schema_version": schema_version,
                    "attempts_count": len(attempts),
                    "has_warnings": bool(quality_warnings),
                },
            )

        except NotFound as e:
            raise DocumentNotFoundError(doc_id) from e
        except GoogleAPIError as e:
            logger.error(
                "document_extraction_save_failed",
                doc_id=doc_id,
                error=str(e),
            )
            raise DatabaseError(f"Failed to save extraction for {doc_id}: {e}") from e

    def update_with_optimistic_lock(
        self,
        doc_id: str,
        update_data: dict[str, Any],
        expected_updated_at: datetime,
    ) -> None:
        """
        Update document with optimistic locking.

        Args:
            doc_id: Document hash
            update_data: Fields to update
            expected_updated_at: Expected updated_at timestamp

        Raises:
            DocumentNotFoundError: If document not found
            OptimisticLockError: If document was modified by another user
            DatabaseError: If update fails
        """
        try:
            doc_ref = self._client.collection(self.DOCUMENTS_COLLECTION).document(doc_id)

            @firestore.transactional
            def update_in_transaction(transaction: firestore.Transaction) -> None:
                doc = doc_ref.get(transaction=transaction)

                if not doc.exists:
                    raise DocumentNotFoundError(doc_id)

                current_data = doc.to_dict()
                actual_updated_at = current_data.get("updated_at")

                # Convert Firestore timestamp if needed
                if hasattr(actual_updated_at, "timestamp"):
                    actual_updated_at = datetime.fromtimestamp(
                        actual_updated_at.timestamp(), tz=UTC
                    )

                # Compare timestamps (with some tolerance for float precision)
                if actual_updated_at:
                    expected_ts = expected_updated_at.timestamp()
                    actual_ts = actual_updated_at.timestamp()
                    if abs(expected_ts - actual_ts) > 0.001:  # 1ms tolerance
                        raise OptimisticLockError(doc_id, expected_updated_at, actual_updated_at)

                # Add new updated_at
                update_data["updated_at"] = datetime.now(UTC)
                transaction.update(doc_ref, update_data)

            transaction = self._client.transaction()
            update_in_transaction(transaction)

            logger.info(
                "document_updated_with_lock",
                doc_id=doc_id,
                fields=list(update_data.keys()),
            )

        except (DocumentNotFoundError, OptimisticLockError):
            raise
        except GoogleAPIError as e:
            logger.error(
                "document_optimistic_update_failed",
                doc_id=doc_id,
                error=str(e),
            )
            raise DatabaseError(f"Failed to update {doc_id} with lock: {e}") from e

    def save_correction(
        self,
        doc_id: str,
        corrected_data: dict[str, Any],
        user_id: str,
        expected_updated_at: datetime,
    ) -> None:
        """
        Save user correction with optimistic locking.

        Args:
            doc_id: Document hash
            corrected_data: Corrected extraction data
            user_id: User who made the correction
            expected_updated_at: Expected updated_at for conflict detection

        Raises:
            DocumentNotFoundError: If document not found
            OptimisticLockError: If document was modified
            DatabaseError: If save fails
        """
        # Get current data for audit log (before field)
        current = self.get_document(doc_id)
        if not current:
            raise DocumentNotFoundError(doc_id)

        before_data = current.extracted_data

        # Update with optimistic lock
        self.update_with_optimistic_lock(
            doc_id,
            {"extracted_data": corrected_data},
            expected_updated_at,
        )

        # Log correction audit event
        self.log_audit_event(
            doc_id,
            AuditEventType.CORRECTED,
            {
                "before": before_data,
                "after": corrected_data,
            },
            user_id=user_id,
        )

        logger.info(
            "document_correction_saved",
            doc_id=doc_id,
            user_id=user_id,
        )

    def log_audit_event(
        self,
        doc_id: str,
        event: AuditEventType,
        details: dict[str, Any],
        user_id: str | None = None,
    ) -> None:
        """
        Log an audit event.

        Audit log entries are append-only and cannot be modified or deleted.

        Args:
            doc_id: Document hash
            event: Event type
            details: Event details
            user_id: Optional user ID who triggered the event
        """
        entry = AuditLogEntry(
            document_id=doc_id,
            event=event,
            timestamp=datetime.now(UTC),
            details=details,
            user_id=user_id,
        )

        try:
            # Use auto-generated ID for audit log entries
            self._client.collection(self.AUDIT_LOG_COLLECTION).add(entry.to_dict())

            logger.debug(
                "audit_event_logged",
                doc_id=doc_id,
                audit_event=event.value,
            )

        except GoogleAPIError as e:
            # Log but don't fail - audit logging should not break main flow
            logger.error(
                "audit_log_failed",
                doc_id=doc_id,
                audit_event=event.value,
                error=str(e),
            )

    def get_audit_log(self, doc_id: str) -> list[AuditLogEntry]:
        """
        Get audit log entries for a document.

        Args:
            doc_id: Document hash

        Returns:
            List of audit log entries, ordered by timestamp
        """
        try:
            query = (
                self._client.collection(self.AUDIT_LOG_COLLECTION)
                .where("document_id", "==", doc_id)
                .order_by("timestamp")
            )

            entries = []
            for doc in query.stream():
                data = doc.to_dict()
                timestamp = data.get("timestamp")
                if hasattr(timestamp, "timestamp"):
                    timestamp = datetime.fromtimestamp(timestamp.timestamp(), tz=UTC)

                event = data.get("event", "CREATED")
                if isinstance(event, str):
                    try:
                        event = AuditEventType(event)
                    except ValueError:
                        event = AuditEventType.CREATED

                entries.append(
                    AuditLogEntry(
                        document_id=doc_id,
                        event=event,
                        timestamp=timestamp or datetime.now(UTC),
                        details=data.get("details", {}),
                        user_id=data.get("user_id"),
                    )
                )

            return entries

        except GoogleAPIError as e:
            logger.error(
                "audit_log_get_failed",
                doc_id=doc_id,
                error=str(e),
            )
            return []

    def list_documents(
        self,
        status: DocumentStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DocumentRecord]:
        """
        List documents with optional filtering.

        Args:
            status: Optional status filter
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of DocumentRecord objects
        """
        try:
            query = self._client.collection(self.DOCUMENTS_COLLECTION)

            if status:
                query = query.where("status", "==", status.value)

            query = query.order_by("created_at", direction=firestore.Query.DESCENDING)
            query = query.limit(limit).offset(offset)

            records = []
            for doc in query.stream():
                records.append(DocumentRecord.from_dict(doc.to_dict()))

            return records

        except GoogleAPIError as e:
            logger.error(
                "document_list_failed",
                status=status.value if status else None,
                error=str(e),
            )
            return []

    def save_draft(
        self,
        doc_id: str,
        draft_data: dict[str, Any],
        user_id: str,
    ) -> None:
        """
        Save a draft for auto-save functionality.

        Args:
            doc_id: Document hash
            draft_data: Draft extraction data (may be incomplete)
            user_id: User who owns the draft
        """
        try:
            draft_id = f"{doc_id}_{user_id}"
            doc_ref = self._client.collection(self.DRAFTS_COLLECTION).document(draft_id)

            now = datetime.now(UTC)
            doc_ref.set(
                {
                    "document_id": doc_id,
                    "user_id": user_id,
                    "draft_data": draft_data,
                    "created_at": now,
                    "updated_at": now,
                },
                merge=True,
            )

            logger.debug(
                "draft_saved",
                doc_id=doc_id,
                user_id=user_id,
            )

        except GoogleAPIError as e:
            logger.error(
                "draft_save_failed",
                doc_id=doc_id,
                user_id=user_id,
                error=str(e),
            )

    def get_draft(self, doc_id: str, user_id: str) -> dict[str, Any] | None:
        """
        Get a saved draft.

        Args:
            doc_id: Document hash
            user_id: User who owns the draft

        Returns:
            Draft data if found, None otherwise
        """
        try:
            draft_id = f"{doc_id}_{user_id}"
            doc_ref = self._client.collection(self.DRAFTS_COLLECTION).document(draft_id)
            doc = doc_ref.get()

            if not doc.exists:
                return None

            return doc.to_dict().get("draft_data")

        except GoogleAPIError as e:
            logger.error(
                "draft_get_failed",
                doc_id=doc_id,
                user_id=user_id,
                error=str(e),
            )
            return None

    def delete_draft(self, doc_id: str, user_id: str) -> None:
        """
        Delete a saved draft.

        Args:
            doc_id: Document hash
            user_id: User who owns the draft
        """
        try:
            draft_id = f"{doc_id}_{user_id}"
            doc_ref = self._client.collection(self.DRAFTS_COLLECTION).document(draft_id)
            doc_ref.delete()

            logger.debug(
                "draft_deleted",
                doc_id=doc_id,
                user_id=user_id,
            )

        except GoogleAPIError as e:
            logger.error(
                "draft_delete_failed",
                doc_id=doc_id,
                user_id=user_id,
                error=str(e),
            )
