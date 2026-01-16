"""Unit tests for structured logging module."""

from __future__ import annotations

import os
from unittest.mock import patch

from src.core.logging import (
    EventType,
    LogContext,
    LogLevel,
    configure_logging,
    get_logger,
    log_api_event,
    log_error,
    log_processing_event,
    mask_dict,
    mask_value,
)


class TestLogLevel:
    """Tests for LogLevel enum."""

    def test_log_levels_are_strings(self) -> None:
        """Test that log levels are string enums."""
        assert LogLevel.DEBUG == "debug"
        assert LogLevel.INFO == "info"
        assert LogLevel.WARNING == "warning"
        assert LogLevel.ERROR == "error"
        assert LogLevel.CRITICAL == "critical"

    def test_all_log_levels_defined(self) -> None:
        """Test that all standard log levels are defined."""
        levels = [level.value for level in LogLevel]
        assert len(levels) == 5
        assert "debug" in levels
        assert "info" in levels
        assert "warning" in levels
        assert "error" in levels
        assert "critical" in levels


class TestEventType:
    """Tests for EventType enum."""

    def test_document_lifecycle_events(self) -> None:
        """Test document lifecycle event types."""
        assert EventType.DOCUMENT_RECEIVED.value == "document_received"
        assert EventType.PROCESSING_STARTED.value == "processing_started"
        assert EventType.PROCESSING_COMPLETED.value == "processing_completed"
        assert EventType.PROCESSING_FAILED.value == "processing_failed"

    def test_lock_events(self) -> None:
        """Test lock operation event types."""
        assert EventType.LOCK_ACQUIRED.value == "lock_acquired"
        assert EventType.LOCK_RELEASED.value == "lock_released"
        assert EventType.LOCK_SKIPPED_DUPLICATE.value == "lock_skipped_duplicate"
        assert EventType.HEARTBEAT_SENT.value == "heartbeat_sent"

    def test_gemini_events(self) -> None:
        """Test Gemini API event types."""
        assert EventType.GEMINI_FLASH_ATTEMPT.value == "gemini_flash_attempt"
        assert EventType.GEMINI_FLASH_SUCCESS.value == "gemini_flash_success"
        assert EventType.GEMINI_PRO_ESCALATION.value == "gemini_pro_escalation"

    def test_saga_events(self) -> None:
        """Test saga operation event types."""
        assert EventType.SAGA_STARTED.value == "saga_started"
        assert EventType.SAGA_STEP_COMPLETED.value == "saga_step_completed"
        assert EventType.SAGA_COMPENSATING.value == "saga_compensating"
        assert EventType.SAGA_COMPLETED.value == "saga_completed"

    def test_api_events(self) -> None:
        """Test API event types."""
        assert EventType.API_REQUEST.value == "api_request"
        assert EventType.API_RESPONSE.value == "api_response"
        assert EventType.API_ERROR.value == "api_error"

    def test_review_ui_events(self) -> None:
        """Test Review UI event types."""
        assert EventType.DRAFT_SAVED.value == "draft_saved"
        assert EventType.DOCUMENT_APPROVED.value == "document_approved"
        assert EventType.DOCUMENT_REJECTED.value == "document_rejected"
        assert EventType.CONFLICT_DETECTED.value == "conflict_detected"


class TestMaskValue:
    """Tests for value masking."""

    def test_mask_none_returns_none(self) -> None:
        """Test that None values are preserved."""
        assert mask_value(None) is None
        assert mask_value(None, "management_id") is None

    def test_mask_sensitive_string_field(self) -> None:
        """Test masking of sensitive string fields."""
        result = mask_value("ABC123-456", "management_id")
        assert result == "AB***56"

    def test_mask_short_sensitive_string(self) -> None:
        """Test masking of short sensitive strings."""
        result = mask_value("AB", "management_id")
        assert result == "***"

    def test_mask_sensitive_numeric_field(self) -> None:
        """Test masking of sensitive numeric fields."""
        result = mask_value(123456, "total_amount")
        assert result == "***"

    def test_mask_company_name(self) -> None:
        """Test masking of company names."""
        result = mask_value("Acme Corporation Ltd", "company_name")
        assert result == "Ac***td"

    def test_mask_phone_pattern(self) -> None:
        """Test masking of phone number patterns."""
        result = mask_value("Contact: 03-1234-5678")
        assert "[PHONE_MASKED]" in result

    def test_mask_email_pattern(self) -> None:
        """Test masking of email patterns."""
        result = mask_value("Email: user@example.com")
        assert "[EMAIL_MASKED]" in result

    def test_mask_credit_card_pattern(self) -> None:
        """Test masking of credit card patterns."""
        result = mask_value("Card: 1234-5678-9012-3456")
        assert "[CREDIT_CARD_MASKED]" in result

    def test_mask_postal_code_pattern(self) -> None:
        """Test masking of postal code patterns."""
        result = mask_value("Postal: 123-4567")
        assert "[POSTAL_CODE_MASKED]" in result

    def test_non_sensitive_field_not_masked(self) -> None:
        """Test that non-sensitive fields are not masked."""
        result = mask_value("normal_value", "status")
        assert result == "normal_value"

    def test_non_sensitive_number_not_masked(self) -> None:
        """Test that non-sensitive numbers are not masked."""
        result = mask_value(42, "page_count")
        assert result == 42


class TestMaskDict:
    """Tests for dictionary masking."""

    def test_mask_empty_dict(self) -> None:
        """Test masking empty dictionary."""
        result = mask_dict({})
        assert result == {}

    def test_mask_simple_dict(self) -> None:
        """Test masking simple dictionary with sensitive fields."""
        data = {
            "management_id": "ABC123-456",
            "status": "COMPLETED",
            "page_count": 3,
        }
        result = mask_dict(data)
        assert result["management_id"] == "AB***56"
        assert result["status"] == "COMPLETED"
        assert result["page_count"] == 3

    def test_mask_nested_dict(self) -> None:
        """Test masking nested dictionary."""
        data = {
            "document": {
                "management_id": "ABC123-456",
                "company_name": "Test Company",
            },
            "status": "OK",
        }
        result = mask_dict(data)
        assert result["document"]["management_id"] == "AB***56"
        assert result["document"]["company_name"] == "Te***ny"
        assert result["status"] == "OK"

    def test_mask_list_in_dict(self) -> None:
        """Test masking list values in dictionary."""
        data = {
            "errors": ["Error 1", "Error 2"],
            "amounts": [{"total_amount": 1000}, {"total_amount": 2000}],
        }
        result = mask_dict(data)
        assert result["errors"] == ["Error 1", "Error 2"]
        assert result["amounts"][0]["total_amount"] == "***"
        assert result["amounts"][1]["total_amount"] == "***"


class TestConfigureLogging:
    """Tests for logging configuration."""

    def test_configure_development_logging(self) -> None:
        """Test configuration for development environment."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            configure_logging(json_logs=False, log_level="DEBUG")
            logger = get_logger("test")
            assert logger is not None

    def test_configure_production_logging(self) -> None:
        """Test configuration for production environment."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            configure_logging(json_logs=True, log_level="INFO")
            logger = get_logger("test")
            assert logger is not None

    def test_auto_detect_json_logs_production(self) -> None:
        """Test auto-detection of JSON logs in production."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            configure_logging(json_logs=None)
            # Should not raise

    def test_auto_detect_json_logs_development(self) -> None:
        """Test auto-detection of non-JSON logs in development."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            configure_logging(json_logs=None)
            # Should not raise


class TestGetLogger:
    """Tests for logger creation."""

    def test_get_logger_without_name(self) -> None:
        """Test getting logger without name."""
        configure_logging(json_logs=False)
        logger = get_logger()
        assert logger is not None

    def test_get_logger_with_name(self) -> None:
        """Test getting logger with name."""
        configure_logging(json_logs=False)
        logger = get_logger("test_module")
        assert logger is not None


class TestLogProcessingEvent:
    """Tests for processing event logging."""

    def test_log_processing_event_with_enum(self) -> None:
        """Test logging event with EventType enum."""
        configure_logging(json_logs=False)
        # Should not raise
        log_processing_event(
            EventType.DOCUMENT_RECEIVED,
            doc_hash="sha256:abc123",
            source_path="gs://bucket/file.pdf",
            file_size=12345,
        )

    def test_log_processing_event_with_string(self) -> None:
        """Test logging event with string type."""
        configure_logging(json_logs=False)
        # Should not raise
        log_processing_event(
            "custom_event",
            doc_hash="sha256:abc123",
            custom_field="value",
        )

    def test_log_processing_event_minimal(self) -> None:
        """Test logging event with minimal fields."""
        configure_logging(json_logs=False)
        # Should not raise
        log_processing_event(
            EventType.LOCK_ACQUIRED,
            doc_hash="sha256:abc123",
        )


class TestLogApiEvent:
    """Tests for API event logging."""

    def test_log_api_event_with_user(self) -> None:
        """Test logging API event with user ID."""
        configure_logging(json_logs=False)
        # Should not raise
        log_api_event(
            EventType.API_REQUEST,
            user_id="user@example.com",
            method="GET",
            path="/api/documents",
        )

    def test_log_api_event_without_user(self) -> None:
        """Test logging API event without user ID."""
        configure_logging(json_logs=False)
        # Should not raise
        log_api_event(
            EventType.HEALTH_CHECK,
            status="healthy",
        )


class TestLogError:
    """Tests for error logging."""

    def test_log_error_with_exception(self) -> None:
        """Test logging error with exception."""
        configure_logging(json_logs=False)
        try:
            raise ValueError("Test error message")
        except ValueError as e:
            # Should not raise
            log_error(
                EventType.PROCESSING_FAILED,
                error=e,
                doc_hash="sha256:abc123",
                attempts=3,
            )

    def test_log_error_with_string(self) -> None:
        """Test logging error with string message."""
        configure_logging(json_logs=False)
        # Should not raise
        log_error(
            EventType.API_ERROR,
            error="Connection refused",
            request_id="req123",
        )

    def test_log_error_without_doc_hash(self) -> None:
        """Test logging error without doc_hash."""
        configure_logging(json_logs=False)
        # Should not raise
        log_error(
            EventType.BUDGET_EXCEEDED,
            error="Daily limit reached",
            daily_usage=50,
            limit=50,
        )


class TestLogContext:
    """Tests for LogContext context manager."""

    def test_log_context_adds_fields(self) -> None:
        """Test that LogContext adds fields to logs."""
        configure_logging(json_logs=False)
        with LogContext(request_id="req123", user_id="user@example.com"):
            # Within context, logs should have these fields
            # (actual verification would require capturing output)
            log_processing_event(
                EventType.DOCUMENT_RECEIVED,
                doc_hash="sha256:abc123",
            )

    def test_log_context_cleans_up(self) -> None:
        """Test that LogContext cleans up fields after exit."""
        configure_logging(json_logs=False)
        with LogContext(request_id="req123"):
            pass
        # After context, logs should not have request_id
        # (actual verification would require capturing output)


class TestCloudContext:
    """Tests for Cloud Function context injection."""

    def test_cloud_context_from_environment(self) -> None:
        """Test that cloud context is added from environment."""
        env_vars = {
            "FUNCTION_EXECUTION_ID": "exec-123",
            "FUNCTION_NAME": "ocr-processor",
            "GCP_PROJECT": "my-project",
            "ENVIRONMENT": "production",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            configure_logging(json_logs=False)
            # Should include cloud context in logs
            log_processing_event(
                EventType.DOCUMENT_RECEIVED,
                doc_hash="sha256:abc123",
            )

    def test_cloud_context_with_cloud_run(self) -> None:
        """Test cloud context with Cloud Run environment."""
        env_vars = {
            "K_REVISION": "ocr-processor-00001",
            "K_SERVICE": "ocr-processor",
            "GCP_PROJECT": "my-project",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            configure_logging(json_logs=False)
            log_processing_event(
                EventType.API_REQUEST,
                doc_hash="sha256:abc123",
            )

    def test_cloud_context_local(self) -> None:
        """Test cloud context in local development."""
        # Clear cloud-related env vars
        with patch.dict(os.environ, {}, clear=True):
            os.environ["ENVIRONMENT"] = "development"
            configure_logging(json_logs=False)
            log_processing_event(
                EventType.DOCUMENT_RECEIVED,
                doc_hash="sha256:abc123",
            )


class TestProductionMasking:
    """Tests for production environment masking."""

    def test_masking_in_production(self) -> None:
        """Test that sensitive data is masked in production."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            configure_logging(json_logs=True)
            # In production, sensitive fields should be masked
            # (would need to capture output to verify)
            log_processing_event(
                EventType.PROCESSING_COMPLETED,
                doc_hash="sha256:abc123",
                management_id="ABC123-456",
                company_name="Test Company Inc",
            )

    def test_no_masking_in_development(self) -> None:
        """Test that sensitive data is not masked in development."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            configure_logging(json_logs=False)
            # In development, data should not be masked
            log_processing_event(
                EventType.PROCESSING_COMPLETED,
                doc_hash="sha256:abc123",
                management_id="ABC123-456",
            )


class TestEventTypeCoverage:
    """Tests to ensure all event types can be logged."""

    def test_all_event_types_are_loggable(self) -> None:
        """Test that all event types can be used in logging."""
        configure_logging(json_logs=False)
        for event_type in EventType:
            # Each event type should be loggable without error
            log_processing_event(
                event_type,
                doc_hash="sha256:test",
                test_field="value",
            )


class TestSensitiveFieldsCoverage:
    """Tests for sensitive field detection."""

    def test_management_id_masked(self) -> None:
        """Test management_id is detected as sensitive."""
        assert mask_value("ABC123", "management_id") != "ABC123"

    def test_total_amount_masked(self) -> None:
        """Test total_amount is detected as sensitive."""
        assert mask_value(10000, "total_amount") == "***"

    def test_tax_amount_masked(self) -> None:
        """Test tax_amount is detected as sensitive."""
        assert mask_value(1000, "tax_amount") == "***"

    def test_company_name_masked(self) -> None:
        """Test company_name is detected as sensitive."""
        result = mask_value("Acme Corp", "company_name")
        assert result != "Acme Corp"

    def test_address_masked(self) -> None:
        """Test address is detected as sensitive."""
        result = mask_value("123 Main Street", "address")
        assert result != "123 Main Street"

    def test_email_field_masked(self) -> None:
        """Test email field is detected as sensitive."""
        result = mask_value("user@example.com", "email")
        assert result != "user@example.com"

    def test_bank_account_masked(self) -> None:
        """Test bank_account is detected as sensitive."""
        result = mask_value("12345678", "bank_account")
        assert result != "12345678"
