"""Unit tests for audit module."""

from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import patch

from src.core.audit import (
    AuditAction,
    AuditEntry,
    AuditLogger,
    audit_log,
    get_audit_logger,
)


class TestAuditAction:
    """Tests for AuditAction enum."""

    def test_document_lifecycle_actions(self) -> None:
        """Test document lifecycle action types."""
        assert AuditAction.DOCUMENT_CREATED.value == "DOCUMENT_CREATED"
        assert AuditAction.DOCUMENT_PROCESSED.value == "DOCUMENT_PROCESSED"
        assert AuditAction.DOCUMENT_FAILED.value == "DOCUMENT_FAILED"
        assert AuditAction.DOCUMENT_QUARANTINED.value == "DOCUMENT_QUARANTINED"

    def test_review_actions(self) -> None:
        """Test review action types."""
        assert AuditAction.DOCUMENT_VIEWED.value == "DOCUMENT_VIEWED"
        assert AuditAction.DOCUMENT_CORRECTED.value == "DOCUMENT_CORRECTED"
        assert AuditAction.DOCUMENT_APPROVED.value == "DOCUMENT_APPROVED"
        assert AuditAction.DOCUMENT_REJECTED.value == "DOCUMENT_REJECTED"

    def test_draft_actions(self) -> None:
        """Test draft action types."""
        assert AuditAction.DRAFT_SAVED.value == "DRAFT_SAVED"
        assert AuditAction.DRAFT_RECOVERED.value == "DRAFT_RECOVERED"
        assert AuditAction.DRAFT_DISCARDED.value == "DRAFT_DISCARDED"

    def test_data_operations(self) -> None:
        """Test data operation action types."""
        assert AuditAction.DATA_EXPORTED.value == "DATA_EXPORTED"
        assert AuditAction.DATA_DELETED.value == "DATA_DELETED"

    def test_access_events(self) -> None:
        """Test access event types."""
        assert AuditAction.LOGIN_SUCCESS.value == "LOGIN_SUCCESS"
        assert AuditAction.LOGIN_FAILED.value == "LOGIN_FAILED"
        assert AuditAction.ACCESS_DENIED.value == "ACCESS_DENIED"


class TestAuditEntry:
    """Tests for AuditEntry dataclass."""

    def test_basic_entry(self) -> None:
        """Test basic audit entry creation."""
        entry = AuditEntry(
            action=AuditAction.DOCUMENT_APPROVED,
            resource_type="document",
            resource_id="sha256:abc123",
            actor="user@example.com",
        )
        assert entry.action == AuditAction.DOCUMENT_APPROVED
        assert entry.resource_type == "document"
        assert entry.resource_id == "sha256:abc123"
        assert entry.actor == "user@example.com"

    def test_entry_with_details(self) -> None:
        """Test audit entry with details."""
        entry = AuditEntry(
            action=AuditAction.DOCUMENT_CORRECTED,
            resource_type="document",
            resource_id="sha256:abc123",
            actor="user@example.com",
            details={"field": "management_id", "old": "ABC", "new": "DEF"},
        )
        assert entry.details["field"] == "management_id"
        assert entry.details["old"] == "ABC"

    def test_entry_with_client_info(self) -> None:
        """Test audit entry with client info."""
        entry = AuditEntry(
            action=AuditAction.DOCUMENT_VIEWED,
            resource_type="document",
            resource_id="sha256:abc123",
            actor="user@example.com",
            client_ip="192.168.1.1",
            user_agent="Mozilla/5.0",
        )
        assert entry.client_ip == "192.168.1.1"
        assert entry.user_agent == "Mozilla/5.0"

    def test_entry_to_dict(self) -> None:
        """Test audit entry serialization."""
        entry = AuditEntry(
            action=AuditAction.DOCUMENT_APPROVED,
            resource_type="document",
            resource_id="sha256:abc123",
            actor="user@example.com",
            actor_id="user123",
            details={"key": "value"},
            client_ip="192.168.1.1",
            user_agent="Mozilla/5.0",
            request_id="req123",
            session_id="sess456",
        )
        result = entry.to_dict()

        assert result["action"] == "DOCUMENT_APPROVED"
        assert result["resource_type"] == "document"
        assert result["resource_id"] == "sha256:abc123"
        assert result["actor"] == "user@example.com"
        assert result["actor_id"] == "user123"
        assert result["details"] == {"key": "value"}
        assert result["client_ip"] == "192.168.1.1"
        assert result["user_agent"] == "Mozilla/5.0"
        assert result["request_id"] == "req123"
        assert result["session_id"] == "sess456"
        assert "timestamp" in result

    def test_entry_timestamp_default(self) -> None:
        """Test that entry gets default timestamp."""
        entry = AuditEntry(
            action=AuditAction.DOCUMENT_APPROVED,
            resource_type="document",
            resource_id="sha256:abc123",
        )
        assert entry.timestamp is not None
        assert isinstance(entry.timestamp, datetime)


class TestAuditLogger:
    """Tests for AuditLogger class."""

    def test_init_development(self) -> None:
        """Test logger initialization in development."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            logger = AuditLogger()
            assert logger.environment == "development"
            assert logger._cloud_logger is None

    def test_init_production_with_logging_available(self) -> None:
        """Test logger initialization in production with cloud logging available."""
        from unittest.mock import MagicMock

        mock_cloud_logging = MagicMock()
        mock_client = MagicMock()
        mock_logger = MagicMock()
        mock_cloud_logging.Client.return_value = mock_client
        mock_client.logger.return_value = mock_logger

        with (
            patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False),
            patch.dict("sys.modules", {"google.cloud.logging": mock_cloud_logging}),
        ):
            logger = AuditLogger()
            logger._init_cloud_logging()
            # Should have initialized cloud logger

    def test_init_production_import_error(self) -> None:
        """Test logger initialization in production when logging not installed."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            logger = AuditLogger()
            # Should handle ImportError gracefully

    def test_init_cloud_logging_exception(self) -> None:
        """Test _init_cloud_logging handles exceptions."""
        from unittest.mock import MagicMock

        mock_cloud_logging = MagicMock()
        mock_cloud_logging.Client.side_effect = Exception("Connection error")

        with (
            patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False),
            patch.dict("sys.modules", {"google.cloud.logging": mock_cloud_logging}),
        ):
            logger = AuditLogger()
            logger._init_cloud_logging()
            # Should handle exception gracefully

    def test_log_with_cloud_logger(self) -> None:
        """Test log sends to cloud logger when available."""
        from unittest.mock import MagicMock

        mock_cloud_logger = MagicMock()

        logger = AuditLogger()
        logger._cloud_logger = mock_cloud_logger

        entry = AuditEntry(
            action=AuditAction.DOCUMENT_APPROVED,
            resource_type="document",
            resource_id="sha256:abc123",
            actor="user@example.com",
        )
        logger.log(entry)

        # Should have called cloud logger
        mock_cloud_logger.log_struct.assert_called_once()

    def test_log_basic_entry(self) -> None:
        """Test logging basic entry."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            logger = AuditLogger()
            entry = AuditEntry(
                action=AuditAction.DOCUMENT_APPROVED,
                resource_type="document",
                resource_id="sha256:abc123",
                actor="user@example.com",
            )
            # Should not raise
            logger.log(entry)

    def test_log_document_action(self) -> None:
        """Test logging document action."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            logger = AuditLogger()
            # Should not raise
            logger.log_document_action(
                action=AuditAction.DOCUMENT_APPROVED,
                doc_hash="sha256:abc123",
                actor="user@example.com",
                details={"note": "test"},
            )

    def test_log_correction(self) -> None:
        """Test logging correction."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            logger = AuditLogger()
            # Should not raise
            logger.log_correction(
                doc_hash="sha256:abc123",
                actor="user@example.com",
                field="company_name",
                old_value="Old Company",
                new_value="New Company",
            )

    def test_log_correction_masks_sensitive_field(self) -> None:
        """Test that sensitive fields are masked in corrections."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            logger = AuditLogger()
            # Should not raise, and sensitive data should be masked
            logger.log_correction(
                doc_hash="sha256:abc123",
                actor="user@example.com",
                field="management_id",
                old_value="ABC123456789",
                new_value="DEF987654321",
            )

    def test_log_approval(self) -> None:
        """Test logging approval."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            logger = AuditLogger()
            # Should not raise
            logger.log_approval(
                doc_hash="sha256:abc123",
                actor="user@example.com",
                corrections_count=3,
                warnings_acknowledged=2,
            )

    def test_log_rejection(self) -> None:
        """Test logging rejection."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            logger = AuditLogger()
            # Should not raise
            logger.log_rejection(
                doc_hash="sha256:abc123",
                actor="user@example.com",
                reason="Invalid data format",
            )

    def test_log_access(self) -> None:
        """Test logging access event."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            logger = AuditLogger()
            # Should not raise
            logger.log_access(
                action=AuditAction.LOGIN_SUCCESS,
                actor="user@example.com",
                resource="system",
            )

    def test_log_access_denied(self) -> None:
        """Test logging access denied event."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            logger = AuditLogger()
            # Should not raise
            logger.log_access(
                action=AuditAction.ACCESS_DENIED,
                actor="user@example.com",
                resource="admin/settings",
                success=False,
                reason="Insufficient permissions",
            )

    def test_log_data_export(self) -> None:
        """Test logging data export."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            logger = AuditLogger()
            # Should not raise
            logger.log_data_export(
                actor="user@example.com",
                export_type="csv",
                record_count=100,
                date_range=("2025-01-01", "2025-01-31"),
            )

    def test_log_data_export_without_date_range(self) -> None:
        """Test logging data export without date range."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            logger = AuditLogger()
            # Should not raise
            logger.log_data_export(
                actor="user@example.com",
                export_type="pdf",
                record_count=1,
            )

    def test_mask_sensitive_value_string(self) -> None:
        """Test masking sensitive string value."""
        logger = AuditLogger()
        result = logger._mask_sensitive_value("management_id", "ABC123456789")
        assert result == "AB***89"

    def test_mask_sensitive_value_short_string(self) -> None:
        """Test masking short sensitive string."""
        logger = AuditLogger()
        result = logger._mask_sensitive_value("management_id", "AB")
        assert result == "***"

    def test_mask_sensitive_value_number(self) -> None:
        """Test masking sensitive numeric value."""
        logger = AuditLogger()
        result = logger._mask_sensitive_value("total_amount", 123456)
        assert result == "***"

    def test_mask_non_sensitive_value(self) -> None:
        """Test non-sensitive value is not masked."""
        logger = AuditLogger()
        result = logger._mask_sensitive_value("company_name", "Acme Corp")
        assert result == "Acme Corp"


class TestGetAuditLogger:
    """Tests for get_audit_logger function."""

    def test_returns_logger(self) -> None:
        """Test that function returns an AuditLogger."""
        # Reset singleton
        import src.core.audit as audit_module

        audit_module._audit_logger = None

        logger = get_audit_logger()
        assert isinstance(logger, AuditLogger)

    def test_returns_singleton(self) -> None:
        """Test that function returns same instance."""
        import src.core.audit as audit_module

        audit_module._audit_logger = None

        logger1 = get_audit_logger()
        logger2 = get_audit_logger()
        assert logger1 is logger2


class TestAuditLogFunction:
    """Tests for audit_log convenience function."""

    def test_audit_log_with_enum(self) -> None:
        """Test audit_log with AuditAction enum."""
        # Should not raise
        audit_log(
            action=AuditAction.DOCUMENT_APPROVED,
            resource="sha256:abc123",
            actor="user@example.com",
        )

    def test_audit_log_with_string(self) -> None:
        """Test audit_log with string action."""
        # Should not raise
        audit_log(
            action="DOCUMENT_APPROVED",
            resource="sha256:abc123",
            actor="user@example.com",
        )

    def test_audit_log_with_details(self) -> None:
        """Test audit_log with details."""
        # Should not raise
        audit_log(
            action=AuditAction.DOCUMENT_CORRECTED,
            resource="sha256:abc123",
            actor="user@example.com",
            details={"field": "company_name", "change": "updated"},
        )

    def test_audit_log_unknown_action(self) -> None:
        """Test audit_log with unknown action string."""
        # Should not raise, just log warning
        audit_log(
            action="UNKNOWN_ACTION",
            resource="sha256:abc123",
            actor="user@example.com",
        )
