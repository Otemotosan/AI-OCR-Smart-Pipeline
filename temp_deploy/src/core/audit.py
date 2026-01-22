"""Audit logging for AI-OCR Smart Pipeline.

This module provides audit logging for compliance and security tracking.
All document operations are logged with actor identity and timestamps.

See docs/specs/08_security.md for security requirements.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from src.core.logging import get_logger

logger = get_logger("audit")


class AuditAction(str, Enum):
    """Audit action types for tracking operations."""

    # Document lifecycle
    DOCUMENT_CREATED = "DOCUMENT_CREATED"
    DOCUMENT_PROCESSED = "DOCUMENT_PROCESSED"
    DOCUMENT_FAILED = "DOCUMENT_FAILED"
    DOCUMENT_QUARANTINED = "DOCUMENT_QUARANTINED"

    # Review actions
    DOCUMENT_VIEWED = "DOCUMENT_VIEWED"
    DOCUMENT_CORRECTED = "DOCUMENT_CORRECTED"
    DOCUMENT_APPROVED = "DOCUMENT_APPROVED"
    DOCUMENT_REJECTED = "DOCUMENT_REJECTED"
    DOCUMENT_RESUBMITTED = "DOCUMENT_RESUBMITTED"

    # Draft actions
    DRAFT_SAVED = "DRAFT_SAVED"
    DRAFT_RECOVERED = "DRAFT_RECOVERED"
    DRAFT_DISCARDED = "DRAFT_DISCARDED"

    # Data operations
    DATA_EXPORTED = "DATA_EXPORTED"
    DATA_DELETED = "DATA_DELETED"

    # System operations
    LOCK_ACQUIRED = "LOCK_ACQUIRED"
    LOCK_RELEASED = "LOCK_RELEASED"
    SAGA_COMPENSATED = "SAGA_COMPENSATED"

    # Access events
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    ACCESS_DENIED = "ACCESS_DENIED"


@dataclass
class AuditEntry:
    """Audit log entry."""

    action: AuditAction
    resource_type: str
    resource_id: str
    actor: str | None = None
    actor_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    client_ip: str | None = None
    user_agent: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    request_id: str | None = None
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "action": self.action.value,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "actor": self.actor,
            "actor_id": self.actor_id,
            "details": self.details,
            "client_ip": self.client_ip,
            "user_agent": self.user_agent,
            "request_id": self.request_id,
            "session_id": self.session_id,
        }


class AuditLogger:
    """Audit logger for compliance and security tracking.

    In production, logs are sent to Cloud Logging with locked retention.
    In development, logs are written to structured logs.
    """

    def __init__(self) -> None:
        """Initialize audit logger."""
        self.environment = os.environ.get("ENVIRONMENT", "development")
        self._cloud_logger = None

        if self.environment == "production":
            self._init_cloud_logging()

    def _init_cloud_logging(self) -> None:
        """Initialize Cloud Logging client for production."""
        try:
            from google.cloud import logging as cloud_logging

            client = cloud_logging.Client()
            self._cloud_logger = client.logger("ocr-audit-log")
        except ImportError:
            logger.warning("google-cloud-logging not installed, using structured logs only")
        except Exception as e:
            logger.error(
                "Failed to initialize Cloud Logging for audit",
                error=str(e),
            )

    def log(self, entry: AuditEntry) -> None:
        """Log an audit entry.

        Args:
            entry: Audit entry to log.
        """
        entry_dict = entry.to_dict()

        # Always log to structured logs
        logger.info(
            "audit_event",
            **entry_dict,
        )

        # In production, also log to Cloud Logging
        if self._cloud_logger is not None:
            try:
                self._cloud_logger.log_struct(
                    entry_dict,
                    severity="INFO",
                    labels={
                        "audit_type": "custom",
                        "action": entry.action.value,
                        "resource_type": entry.resource_type,
                    },
                )
            except Exception as e:
                logger.error(
                    "Failed to write audit log to Cloud Logging",
                    error=str(e),
                )

    def log_document_action(
        self,
        action: AuditAction,
        doc_hash: str,
        actor: str | None = None,
        details: dict[str, Any] | None = None,
        request: Any = None,
    ) -> None:
        """Log a document action.

        Args:
            action: Action performed.
            doc_hash: Document hash.
            actor: Actor performing the action.
            details: Additional details.
            request: HTTP request for client info.
        """
        entry = AuditEntry(
            action=action,
            resource_type="document",
            resource_id=doc_hash,
            actor=actor,
            details=details or {},
        )

        if request is not None:
            entry.client_ip = getattr(request.client, "host", None)
            entry.user_agent = request.headers.get("User-Agent")
            entry.request_id = request.headers.get("X-Request-ID")

        self.log(entry)

    def log_correction(
        self,
        doc_hash: str,
        actor: str,
        field: str,
        old_value: Any,
        new_value: Any,
        request: Any = None,
    ) -> None:
        """Log a data correction.

        Args:
            doc_hash: Document hash.
            actor: User making the correction.
            field: Field being corrected.
            old_value: Previous value.
            new_value: New value.
            request: HTTP request for client info.
        """
        # Mask sensitive values
        masked_old = self._mask_sensitive_value(field, old_value)
        masked_new = self._mask_sensitive_value(field, new_value)

        self.log_document_action(
            action=AuditAction.DOCUMENT_CORRECTED,
            doc_hash=doc_hash,
            actor=actor,
            details={
                "field": field,
                "old_value": masked_old,
                "new_value": masked_new,
            },
            request=request,
        )

    def log_approval(
        self,
        doc_hash: str,
        actor: str,
        corrections_count: int = 0,
        warnings_acknowledged: int = 0,
        request: Any = None,
    ) -> None:
        """Log document approval.

        Args:
            doc_hash: Document hash.
            actor: User approving.
            corrections_count: Number of corrections made.
            warnings_acknowledged: Number of warnings acknowledged.
            request: HTTP request for client info.
        """
        self.log_document_action(
            action=AuditAction.DOCUMENT_APPROVED,
            doc_hash=doc_hash,
            actor=actor,
            details={
                "corrections_count": corrections_count,
                "warnings_acknowledged": warnings_acknowledged,
            },
            request=request,
        )

    def log_rejection(
        self,
        doc_hash: str,
        actor: str,
        reason: str,
        request: Any = None,
    ) -> None:
        """Log document rejection.

        Args:
            doc_hash: Document hash.
            actor: User rejecting.
            reason: Rejection reason.
            request: HTTP request for client info.
        """
        self.log_document_action(
            action=AuditAction.DOCUMENT_REJECTED,
            doc_hash=doc_hash,
            actor=actor,
            details={
                "reason": reason,
            },
            request=request,
        )

    def log_access(
        self,
        action: AuditAction,
        actor: str,
        resource: str | None = None,
        success: bool = True,
        reason: str | None = None,
        request: Any = None,
    ) -> None:
        """Log access event.

        Args:
            action: Access action type.
            actor: User attempting access.
            resource: Resource being accessed.
            success: Whether access was successful.
            reason: Reason for failure if applicable.
            request: HTTP request for client info.
        """
        entry = AuditEntry(
            action=action,
            resource_type="access",
            resource_id=resource or "system",
            actor=actor,
            details=(
                {
                    "success": success,
                    "reason": reason,
                }
                if reason
                else {"success": success}
            ),
        )

        if request is not None:
            entry.client_ip = getattr(request.client, "host", None)
            entry.user_agent = request.headers.get("User-Agent")

        self.log(entry)

    def log_data_export(
        self,
        actor: str,
        export_type: str,
        record_count: int,
        date_range: tuple[str, str] | None = None,
        request: Any = None,
    ) -> None:
        """Log data export event.

        Args:
            actor: User requesting export.
            export_type: Type of export (csv, pdf, etc.).
            record_count: Number of records exported.
            date_range: Date range of exported data.
            request: HTTP request for client info.
        """
        details = {
            "export_type": export_type,
            "record_count": record_count,
        }
        if date_range:
            details["date_range"] = {
                "start": date_range[0],
                "end": date_range[1],
            }

        entry = AuditEntry(
            action=AuditAction.DATA_EXPORTED,
            resource_type="export",
            resource_id=f"export_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            actor=actor,
            details=details,
        )

        if request is not None:
            entry.client_ip = getattr(request.client, "host", None)
            entry.user_agent = request.headers.get("User-Agent")

        self.log(entry)

    def _mask_sensitive_value(self, field: str, value: Any) -> Any:
        """Mask sensitive values for audit logs.

        Args:
            field: Field name.
            value: Field value.

        Returns:
            Masked value if sensitive, original otherwise.
        """
        sensitive_fields = {
            "management_id",
            "total_amount",
            "tax_amount",
            "bank_account",
            "account_number",
        }

        if field.lower() in sensitive_fields:
            if isinstance(value, str):
                if len(value) <= 4:
                    return "***"
                return f"{value[:2]}***{value[-2:]}"
            elif isinstance(value, (int, float)):
                return "***"

        return value


# Singleton instance
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get the singleton audit logger.

    Returns:
        Configured AuditLogger instance.
    """
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


# Convenience functions


def audit_log(
    action: str | AuditAction,
    resource: str,
    actor: str,
    details: dict[str, Any] | None = None,
    request: Any = None,
) -> None:
    """Log an audit event (convenience function).

    Args:
        action: Action name or AuditAction enum.
        resource: Resource identifier.
        actor: Actor performing the action.
        details: Additional details.
        request: HTTP request for client info.
    """
    if isinstance(action, str):
        try:
            action = AuditAction(action)
        except ValueError:
            # Use structured log if action is not a known type
            logger.warning(
                "unknown_audit_action",
                action=action,
                resource=resource,
                actor=actor,
            )
            return

    audit_logger = get_audit_logger()
    audit_logger.log_document_action(
        action=action,
        doc_hash=resource,
        actor=actor,
        details=details,
        request=request,
    )
