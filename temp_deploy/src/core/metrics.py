"""Cloud Monitoring metrics for AI-OCR Smart Pipeline.

This module provides custom metrics emission and recording for
Cloud Monitoring dashboards and alerting.

See docs/specs/07_monitoring.md for metrics requirements.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Any

from src.core.logging import EventType, get_logger, log_processing_event

logger = get_logger("metrics")


class MetricType(str, Enum):
    """Types of custom metrics."""

    # Document processing
    DOCUMENTS_PROCESSED = "custom.googleapis.com/ocr/documents_processed"
    PROCESSING_DURATION = "custom.googleapis.com/ocr/processing_duration_ms"
    PROCESSING_ATTEMPTS = "custom.googleapis.com/ocr/processing_attempts"

    # Model usage
    GEMINI_FLASH_CALLS = "custom.googleapis.com/ocr/gemini_flash_calls"
    GEMINI_PRO_CALLS = "custom.googleapis.com/ocr/gemini_pro_calls"
    GEMINI_TOKENS_INPUT = "custom.googleapis.com/ocr/gemini_tokens_input"
    GEMINI_TOKENS_OUTPUT = "custom.googleapis.com/ocr/gemini_tokens_output"

    # Budget tracking
    PRO_BUDGET_USAGE = "custom.googleapis.com/ocr/pro_budget_usage"
    PRO_BUDGET_REMAINING = "custom.googleapis.com/ocr/pro_budget_remaining"

    # OCR quality
    OCR_CONFIDENCE = "custom.googleapis.com/ocr/ocr_confidence"
    LOW_CONFIDENCE_COUNT = "custom.googleapis.com/ocr/low_confidence_count"

    # Validation
    GATE_LINTER_FAILURES = "custom.googleapis.com/ocr/gate_linter_failures"
    QUALITY_WARNINGS = "custom.googleapis.com/ocr/quality_warnings"

    # Saga operations
    SAGA_EXECUTIONS = "custom.googleapis.com/ocr/saga_executions"
    SAGA_COMPENSATIONS = "custom.googleapis.com/ocr/saga_compensations"

    # Lock operations
    LOCK_ACQUISITIONS = "custom.googleapis.com/ocr/lock_acquisitions"
    LOCK_FAILURES = "custom.googleapis.com/ocr/lock_failures"
    LOCK_CONTENTIONS = "custom.googleapis.com/ocr/lock_contentions"

    # API metrics
    API_REQUESTS = "custom.googleapis.com/ocr/api_requests"
    API_LATENCY = "custom.googleapis.com/ocr/api_latency_ms"
    API_ERRORS = "custom.googleapis.com/ocr/api_errors"

    # Review UI
    DOCUMENTS_APPROVED = "custom.googleapis.com/ocr/documents_approved"
    DOCUMENTS_REJECTED = "custom.googleapis.com/ocr/documents_rejected"
    DRAFTS_SAVED = "custom.googleapis.com/ocr/drafts_saved"
    CONFLICTS_DETECTED = "custom.googleapis.com/ocr/conflicts_detected"


@dataclass
class MetricLabels:
    """Common labels for metrics."""

    status: str | None = None
    document_type: str | None = None
    model: str | None = None
    error_type: str | None = None
    method: str | None = None
    endpoint: str | None = None

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


class MetricsClient:
    """Client for recording custom metrics to Cloud Monitoring.

    In production, this writes to Cloud Monitoring.
    In development, it logs metrics locally.
    """

    def __init__(self, project_id: str | None = None) -> None:
        """Initialize the metrics client.

        Args:
            project_id: GCP project ID. Defaults to environment variable.
        """
        self.project_id = project_id or os.environ.get("GCP_PROJECT", "local")
        self.environment = os.environ.get("ENVIRONMENT", "development")
        self._client = None

        if self.environment == "production":
            self._init_cloud_monitoring()

    def _init_cloud_monitoring(self) -> None:
        """Initialize Cloud Monitoring client for production."""
        try:
            from google.cloud import monitoring_v3

            self._client = monitoring_v3.MetricServiceClient()
            self._project_name = f"projects/{self.project_id}"
        except ImportError:
            logger.warning("google-cloud-monitoring not installed, metrics will be logged only")
        except Exception as e:
            logger.error(
                "Failed to initialize Cloud Monitoring",
                error=str(e),
            )

    def record(
        self,
        metric_type: MetricType | str,
        value: int | float,
        labels: MetricLabels | dict[str, str] | None = None,
    ) -> None:
        """Record a metric value.

        Args:
            metric_type: Type of metric to record.
            value: Metric value.
            labels: Optional labels for the metric.
        """
        if isinstance(metric_type, MetricType):
            metric_type = metric_type.value

        if isinstance(labels, MetricLabels):
            labels = labels.to_dict()
        elif labels is None:
            labels = {}

        # Always log the metric
        logger.debug(
            "metric_recorded",
            metric_type=metric_type,
            value=value,
            labels=labels,
        )

        # In production, also write to Cloud Monitoring
        if self._client is not None:
            self._write_to_cloud_monitoring(metric_type, value, labels)

    def _write_to_cloud_monitoring(
        self,
        metric_type: str,
        value: int | float,
        labels: dict[str, str],
    ) -> None:
        """Write metric to Cloud Monitoring.

        Args:
            metric_type: Full metric type string.
            value: Metric value.
            labels: Metric labels.
        """
        try:
            from google.cloud import monitoring_v3

            series = monitoring_v3.TimeSeries()
            series.metric.type = metric_type

            for key, val in labels.items():
                series.metric.labels[key] = str(val)

            series.resource.type = "global"

            now = time.time()
            point = monitoring_v3.Point()

            if isinstance(value, int):
                point.value.int64_value = value
            else:
                point.value.double_value = value

            point.interval.end_time.seconds = int(now)
            point.interval.end_time.nanos = int((now % 1) * 1e9)

            series.points.append(point)

            self._client.create_time_series(
                name=self._project_name,
                time_series=[series],
            )
        except Exception as e:
            logger.error(
                "Failed to write metric to Cloud Monitoring",
                metric_type=metric_type,
                error=str(e),
            )

    def record_processing_complete(
        self,
        doc_hash: str,
        status: str,
        document_type: str,
        duration_ms: int,
        attempts: int,
        model_used: str,
    ) -> None:
        """Record completion of document processing.

        Args:
            doc_hash: Document hash.
            status: Final status (COMPLETED, FAILED, etc.).
            document_type: Type of document processed.
            duration_ms: Processing duration in milliseconds.
            attempts: Number of attempts made.
            model_used: Model used (flash, pro).
        """
        labels = MetricLabels(
            status=status,
            document_type=document_type,
            model=model_used,
        )

        self.record(MetricType.DOCUMENTS_PROCESSED, 1, labels)
        self.record(
            MetricType.PROCESSING_DURATION,
            duration_ms,
            MetricLabels(document_type=document_type, model=model_used),
        )
        self.record(
            MetricType.PROCESSING_ATTEMPTS,
            attempts,
            MetricLabels(document_type=document_type),
        )

        # Log the processing event
        log_processing_event(
            EventType.PROCESSING_COMPLETED,
            doc_hash=doc_hash,
            status=status,
            document_type=document_type,
            duration_ms=duration_ms,
            attempts=attempts,
            model_used=model_used,
        )

    def record_gemini_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        success: bool,
        duration_ms: int,
    ) -> None:
        """Record a Gemini API call.

        Args:
            model: Model used (flash, pro).
            input_tokens: Input token count.
            output_tokens: Output token count.
            success: Whether the call succeeded.
            duration_ms: Call duration in milliseconds.
        """
        status = "success" if success else "error"
        labels = MetricLabels(model=model, status=status)

        if model == "flash":
            self.record(MetricType.GEMINI_FLASH_CALLS, 1, labels)
        else:
            self.record(MetricType.GEMINI_PRO_CALLS, 1, labels)

        self.record(
            MetricType.GEMINI_TOKENS_INPUT,
            input_tokens,
            MetricLabels(model=model),
        )
        self.record(
            MetricType.GEMINI_TOKENS_OUTPUT,
            output_tokens,
            MetricLabels(model=model),
        )

    def record_ocr_confidence(
        self,
        confidence: float,
        document_type: str | None = None,
    ) -> None:
        """Record OCR confidence score.

        Args:
            confidence: Confidence score (0.0 - 1.0).
            document_type: Optional document type.
        """
        self.record(
            MetricType.OCR_CONFIDENCE,
            confidence,
            MetricLabels(document_type=document_type) if document_type else None,
        )

        if confidence < 0.85:
            self.record(
                MetricType.LOW_CONFIDENCE_COUNT,
                1,
                MetricLabels(document_type=document_type) if document_type else None,
            )

    def record_validation_result(
        self,
        gate_passed: bool,
        gate_errors: int,
        quality_warnings: int,
        document_type: str | None = None,
    ) -> None:
        """Record validation results.

        Args:
            gate_passed: Whether gate linter passed.
            gate_errors: Number of gate linter errors.
            quality_warnings: Number of quality warnings.
            document_type: Optional document type.
        """
        labels = MetricLabels(document_type=document_type) if document_type else None

        if not gate_passed:
            self.record(MetricType.GATE_LINTER_FAILURES, gate_errors, labels)

        if quality_warnings > 0:
            self.record(MetricType.QUALITY_WARNINGS, quality_warnings, labels)

    def record_saga_execution(
        self,
        success: bool,
        steps_completed: int,
        compensation_needed: bool = False,
    ) -> None:
        """Record saga execution.

        Args:
            success: Whether saga completed successfully.
            steps_completed: Number of steps completed.
            compensation_needed: Whether compensation was triggered.
        """
        status = "success" if success else "failure"
        self.record(MetricType.SAGA_EXECUTIONS, 1, MetricLabels(status=status))

        if compensation_needed:
            self.record(MetricType.SAGA_COMPENSATIONS, 1)

    def record_lock_operation(
        self,
        acquired: bool,
        contention: bool = False,
    ) -> None:
        """Record lock operation.

        Args:
            acquired: Whether lock was acquired.
            contention: Whether there was lock contention.
        """
        if acquired:
            self.record(MetricType.LOCK_ACQUISITIONS, 1)
        else:
            self.record(MetricType.LOCK_FAILURES, 1)

        if contention:
            self.record(MetricType.LOCK_CONTENTIONS, 1)

    def record_api_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration_ms: int,
    ) -> None:
        """Record API request.

        Args:
            method: HTTP method.
            endpoint: API endpoint.
            status_code: Response status code.
            duration_ms: Request duration in milliseconds.
        """
        status = "success" if status_code < 400 else "error"
        labels = MetricLabels(
            method=method,
            endpoint=endpoint,
            status=status,
        )

        self.record(MetricType.API_REQUESTS, 1, labels)
        self.record(
            MetricType.API_LATENCY,
            duration_ms,
            MetricLabels(method=method, endpoint=endpoint),
        )

        if status_code >= 400:
            self.record(
                MetricType.API_ERRORS,
                1,
                MetricLabels(
                    method=method,
                    endpoint=endpoint,
                    error_type=str(status_code),
                ),
            )

    def record_review_action(
        self,
        action: str,
        document_type: str | None = None,
    ) -> None:
        """Record review UI action.

        Args:
            action: Action type (approved, rejected, draft_saved, conflict).
            document_type: Optional document type.
        """
        labels = MetricLabels(document_type=document_type) if document_type else None

        if action == "approved":
            self.record(MetricType.DOCUMENTS_APPROVED, 1, labels)
        elif action == "rejected":
            self.record(MetricType.DOCUMENTS_REJECTED, 1, labels)
        elif action == "draft_saved":
            self.record(MetricType.DRAFTS_SAVED, 1, labels)
        elif action == "conflict":
            self.record(MetricType.CONFLICTS_DETECTED, 1, labels)

    def record_budget_status(
        self,
        daily_used: int,
        daily_limit: int,
        monthly_used: int,
        monthly_limit: int,
    ) -> None:
        """Record Pro API budget status.

        Args:
            daily_used: Daily Pro calls used.
            daily_limit: Daily Pro call limit.
            monthly_used: Monthly Pro calls used.
            monthly_limit: Monthly Pro call limit.
        """
        self.record(MetricType.PRO_BUDGET_USAGE, daily_used)
        self.record(MetricType.PRO_BUDGET_REMAINING, daily_limit - daily_used)


@lru_cache(maxsize=1)
def get_metrics_client() -> MetricsClient:
    """Get the singleton metrics client.

    Returns:
        Configured MetricsClient instance.
    """
    return MetricsClient()


def record_metric(
    metric_type: MetricType | str,
    value: int | float,
    labels: dict[str, str] | None = None,
) -> None:
    """Convenience function to record a metric.

    Args:
        metric_type: Type of metric.
        value: Metric value.
        labels: Optional labels.
    """
    client = get_metrics_client()
    client.record(metric_type, value, labels)


class ProcessingTimer:
    """Context manager for timing processing operations.

    Example:
        with ProcessingTimer(doc_hash="abc123") as timer:
            # Processing code
            pass
        timer.record(status="COMPLETED", document_type="delivery_note")
    """

    def __init__(self, doc_hash: str) -> None:
        """Initialize timer.

        Args:
            doc_hash: Document hash for logging.
        """
        self.doc_hash = doc_hash
        self.start_time: float = 0
        self.end_time: float = 0
        self.duration_ms: int = 0

    def __enter__(self) -> ProcessingTimer:
        self.start_time = time.time()
        return self

    def __exit__(self, *args: Any) -> None:
        self.end_time = time.time()
        self.duration_ms = int((self.end_time - self.start_time) * 1000)

    def record(
        self,
        status: str,
        document_type: str,
        attempts: int = 1,
        model_used: str = "flash",
    ) -> None:
        """Record the processing metrics.

        Args:
            status: Final status.
            document_type: Document type.
            attempts: Number of attempts.
            model_used: Model used.
        """
        client = get_metrics_client()
        client.record_processing_complete(
            doc_hash=self.doc_hash,
            status=status,
            document_type=document_type,
            duration_ms=self.duration_ms,
            attempts=attempts,
            model_used=model_used,
        )
