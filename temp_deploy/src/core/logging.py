"""Structured logging configuration for AI-OCR Smart Pipeline.

This module provides structured logging with Cloud Logging integration,
sensitive data masking, and consistent event formatting.

See docs/specs/07_monitoring.md for logging requirements.
"""

from __future__ import annotations

import logging
import os
import re
from enum import Enum
from typing import Any

import structlog

# Standard log level values
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,  # 10
    "INFO": logging.INFO,  # 20
    "WARNING": logging.WARNING,  # 30
    "ERROR": logging.ERROR,  # 40
    "CRITICAL": logging.CRITICAL,  # 50
}


class LogLevel(str, Enum):
    """Log levels for structured logging."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class EventType(str, Enum):
    """Standardized event types for log correlation."""

    # Document lifecycle
    DOCUMENT_RECEIVED = "document_received"
    DOCUMENT_SKIPPED = "document_skipped"
    PROCESSING_STARTED = "processing_started"
    PROCESSING_COMPLETED = "processing_completed"
    PROCESSING_FAILED = "processing_failed"

    # Lock operations
    LOCK_ACQUIRED = "lock_acquired"
    LOCK_RELEASED = "lock_released"
    LOCK_SKIPPED_DUPLICATE = "lock_skipped_duplicate"
    LOCK_EXPIRED = "lock_expired"
    HEARTBEAT_SENT = "heartbeat_sent"

    # OCR operations
    OCR_STARTED = "ocr_started"
    OCR_COMPLETED = "ocr_completed"
    OCR_FAILED = "ocr_failed"

    # Gemini operations
    GEMINI_FLASH_ATTEMPT = "gemini_flash_attempt"
    GEMINI_FLASH_SUCCESS = "gemini_flash_success"
    GEMINI_FLASH_FAILED = "gemini_flash_failed"
    GEMINI_PRO_ESCALATION = "gemini_pro_escalation"
    GEMINI_PRO_SUCCESS = "gemini_pro_success"
    GEMINI_PRO_FAILED = "gemini_pro_failed"

    # Validation
    GATE_LINTER_PASSED = "gate_linter_passed"
    GATE_LINTER_FAILED = "gate_linter_failed"
    QUALITY_WARNINGS = "quality_warnings"

    # Saga operations
    SAGA_STARTED = "saga_started"
    SAGA_STEP_COMPLETED = "saga_step_completed"
    SAGA_STEP_FAILED = "saga_step_failed"
    SAGA_COMPENSATING = "saga_compensating"
    SAGA_COMPLETED = "saga_completed"
    SAGA_FAILED = "saga_failed"

    # Budget operations
    BUDGET_CHECK = "budget_check"
    BUDGET_INCREMENT = "budget_increment"
    BUDGET_EXCEEDED = "budget_exceeded"

    # API operations
    API_REQUEST = "api_request"
    API_RESPONSE = "api_response"
    API_ERROR = "api_error"

    # Review UI operations
    DRAFT_SAVED = "draft_saved"
    DRAFT_RECOVERED = "draft_recovered"
    DOCUMENT_CORRECTED = "document_corrected"
    DOCUMENT_APPROVED = "document_approved"
    DOCUMENT_REJECTED = "document_rejected"
    CONFLICT_DETECTED = "conflict_detected"

    # System operations
    HEALTH_CHECK = "health_check"
    ALERT_TRIGGERED = "alert_triggered"


# Patterns for sensitive data masking (order matters - more specific patterns first)
SENSITIVE_PATTERNS = [
    # Credit card numbers (16 digits with optional separators) - check before phone
    ("credit_card", re.compile(r"\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}")),
    # Email addresses
    ("email", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    # Japanese phone numbers (3-4 digit area code - 3-4 digits - 4 digits)
    ("phone", re.compile(r"\d{2,4}-\d{2,4}-\d{4}")),
    # Japanese postal codes (3-4 digits)
    ("postal_code", re.compile(r"\d{3}-\d{4}")),
]

# Fields that should always be masked
SENSITIVE_FIELDS = {
    "management_id",
    "total_amount",
    "tax_amount",
    "subtotal_amount",
    "company_name",
    "address",
    "phone_number",
    "email",
    "bank_account",
    "account_number",
}


def mask_value(value: Any, field_name: str = "") -> Any:
    """Mask sensitive values for logging.

    Args:
        value: The value to potentially mask.
        field_name: The field name for context-aware masking.

    Returns:
        Masked value or original if not sensitive.
    """
    if value is None:
        return None

    # Check if field is in sensitive fields list
    field_lower = field_name.lower()
    if any(sensitive in field_lower for sensitive in SENSITIVE_FIELDS):
        if isinstance(value, str):
            if len(value) <= 4:
                return "***"
            return f"{value[:2]}***{value[-2:]}"
        elif isinstance(value, (int, float)):
            return "***"

    # Check for pattern-based masking in strings
    if isinstance(value, str):
        result = value
        for pattern_name, pattern in SENSITIVE_PATTERNS:
            result = pattern.sub(f"[{pattern_name.upper()}_MASKED]", result)
        return result

    return value


def mask_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask sensitive data in a dictionary.

    Args:
        data: Dictionary to mask.

    Returns:
        New dictionary with sensitive values masked.
    """
    result = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result[key] = mask_dict(value)
        elif isinstance(value, list):
            result[key] = [
                mask_dict(item) if isinstance(item, dict) else mask_value(item, key)
                for item in value
            ]
        else:
            result[key] = mask_value(value, key)
    return result


def add_cloud_context(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Add Cloud Function context to log events.

    Adds execution_id, function_name, and project_id from environment.
    """
    event_dict["execution_id"] = os.environ.get(
        "FUNCTION_EXECUTION_ID", os.environ.get("K_REVISION", "local")
    )
    event_dict["function_name"] = os.environ.get(
        "FUNCTION_NAME", os.environ.get("K_SERVICE", "unknown")
    )
    event_dict["project_id"] = os.environ.get("GCP_PROJECT", "local")
    event_dict["environment"] = os.environ.get("ENVIRONMENT", "development")

    return event_dict


def mask_sensitive_data(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor to mask sensitive data in log events."""
    # Only mask in production
    if os.environ.get("ENVIRONMENT") == "production":
        return mask_dict(event_dict)
    return event_dict


def add_severity_for_cloud_logging(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Add severity field for Cloud Logging integration.

    Cloud Logging expects a 'severity' field with uppercase level names.
    """
    level = event_dict.get("level", "info").upper()

    # Map Python log levels to Cloud Logging severity
    severity_map = {
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "WARNING": "WARNING",
        "ERROR": "ERROR",
        "CRITICAL": "CRITICAL",
    }

    event_dict["severity"] = severity_map.get(level, "DEFAULT")

    return event_dict


def configure_logging(
    json_logs: bool | None = None,
    log_level: str = "INFO",
) -> None:
    """Configure structured logging for the application.

    Args:
        json_logs: Whether to output JSON logs. Defaults to True in production.
        log_level: Minimum log level to output.
    """
    # Determine if we should use JSON output
    if json_logs is None:
        json_logs = os.environ.get("ENVIRONMENT") == "production"

    # Common processors
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_cloud_context,
        mask_sensitive_data,
        add_severity_for_cloud_logging,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_logs:
        # Production: JSON output for Cloud Logging
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Development: Human-readable output
        processors.append(
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            )
        )

    # Get numeric log level
    level_value = LOG_LEVELS.get(log_level.upper(), logging.INFO)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level_value),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a configured logger instance.

    Args:
        name: Optional logger name for identification.

    Returns:
        Configured structlog logger.
    """
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(logger_name=name)
    return logger


def log_processing_event(
    event_type: str | EventType,
    doc_hash: str,
    **kwargs: Any,
) -> None:
    """Log a standardized processing event.

    This is the primary logging interface for document processing events.
    All events include doc_hash for correlation.

    Args:
        event_type: Type of event from EventType enum.
        doc_hash: Document hash for correlation.
        **kwargs: Additional event-specific fields.

    Example:
        log_processing_event(
            EventType.OCR_COMPLETED,
            doc_hash="sha256:abc123",
            confidence=0.92,
            page_count=2,
            duration_ms=1234
        )
    """
    logger = get_logger("processor")

    # Convert enum to string if needed
    if isinstance(event_type, EventType):
        event_type = event_type.value

    logger.info(event_type, doc_hash=doc_hash, **kwargs)


def log_api_event(
    event_type: str | EventType,
    user_id: str | None = None,
    **kwargs: Any,
) -> None:
    """Log a standardized API event.

    Args:
        event_type: Type of event from EventType enum.
        user_id: User identifier for audit.
        **kwargs: Additional event-specific fields.
    """
    logger = get_logger("api")

    if isinstance(event_type, EventType):
        event_type = event_type.value

    logger.info(event_type, user_id=user_id, **kwargs)


def log_error(
    event_type: str | EventType,
    error: Exception | str,
    doc_hash: str | None = None,
    **kwargs: Any,
) -> None:
    """Log an error event with full context.

    Args:
        event_type: Type of error event.
        error: The exception or error message.
        doc_hash: Optional document hash for correlation.
        **kwargs: Additional context.
    """
    logger = get_logger("error")

    if isinstance(event_type, EventType):
        event_type = event_type.value

    error_msg = str(error)
    error_type = type(error).__name__ if isinstance(error, Exception) else "Error"

    logger.error(
        event_type, doc_hash=doc_hash, error_message=error_msg, error_type=error_type, **kwargs
    )


class LogContext:
    """Context manager for adding temporary logging context.

    Example:
        with LogContext(request_id="abc123", user_id="user@example.com"):
            log_processing_event(EventType.DOCUMENT_RECEIVED, doc_hash="...")
    """

    def __init__(self, **context: Any) -> None:
        self.context = context
        self.token = None

    def __enter__(self) -> LogContext:
        self.token = structlog.contextvars.bind_contextvars(**self.context)
        return self

    def __exit__(self, *args: Any) -> None:
        if self.token:
            structlog.contextvars.unbind_contextvars(*self.context.keys())


def create_metrics_logger() -> structlog.stdlib.BoundLogger:
    """Create a logger specifically for metrics emission.

    Returns:
        Logger configured for metrics with special formatting.
    """
    return get_logger("metrics")


# Initialize logging on module import if running in Cloud Function
if os.environ.get("FUNCTION_NAME") or os.environ.get("K_SERVICE"):
    configure_logging(json_logs=True, log_level="INFO")
