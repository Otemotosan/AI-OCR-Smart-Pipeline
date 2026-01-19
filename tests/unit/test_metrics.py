"""Unit tests for metrics module."""

from __future__ import annotations

import os
from unittest.mock import patch

from src.core.metrics import (
    MetricLabels,
    MetricsClient,
    MetricType,
    ProcessingTimer,
    get_metrics_client,
    record_metric,
)


class TestMetricType:
    """Tests for MetricType enum."""

    def test_document_processing_metrics(self) -> None:
        """Test document processing metric types."""
        assert (
            MetricType.DOCUMENTS_PROCESSED.value == "custom.googleapis.com/ocr/documents_processed"
        )
        assert (
            MetricType.PROCESSING_DURATION.value
            == "custom.googleapis.com/ocr/processing_duration_ms"
        )
        assert (
            MetricType.PROCESSING_ATTEMPTS.value == "custom.googleapis.com/ocr/processing_attempts"
        )

    def test_gemini_metrics(self) -> None:
        """Test Gemini API metric types."""
        assert MetricType.GEMINI_FLASH_CALLS.value == "custom.googleapis.com/ocr/gemini_flash_calls"
        assert MetricType.GEMINI_PRO_CALLS.value == "custom.googleapis.com/ocr/gemini_pro_calls"
        assert (
            MetricType.GEMINI_TOKENS_INPUT.value == "custom.googleapis.com/ocr/gemini_tokens_input"
        )

    def test_budget_metrics(self) -> None:
        """Test budget tracking metric types."""
        assert MetricType.PRO_BUDGET_USAGE.value == "custom.googleapis.com/ocr/pro_budget_usage"
        assert (
            MetricType.PRO_BUDGET_REMAINING.value
            == "custom.googleapis.com/ocr/pro_budget_remaining"
        )

    def test_ocr_quality_metrics(self) -> None:
        """Test OCR quality metric types."""
        assert MetricType.OCR_CONFIDENCE.value == "custom.googleapis.com/ocr/ocr_confidence"
        assert (
            MetricType.LOW_CONFIDENCE_COUNT.value
            == "custom.googleapis.com/ocr/low_confidence_count"
        )

    def test_validation_metrics(self) -> None:
        """Test validation metric types."""
        assert (
            MetricType.GATE_LINTER_FAILURES.value
            == "custom.googleapis.com/ocr/gate_linter_failures"
        )
        assert MetricType.QUALITY_WARNINGS.value == "custom.googleapis.com/ocr/quality_warnings"

    def test_saga_metrics(self) -> None:
        """Test saga operation metric types."""
        assert MetricType.SAGA_EXECUTIONS.value == "custom.googleapis.com/ocr/saga_executions"
        assert MetricType.SAGA_COMPENSATIONS.value == "custom.googleapis.com/ocr/saga_compensations"

    def test_lock_metrics(self) -> None:
        """Test lock operation metric types."""
        assert MetricType.LOCK_ACQUISITIONS.value == "custom.googleapis.com/ocr/lock_acquisitions"
        assert MetricType.LOCK_FAILURES.value == "custom.googleapis.com/ocr/lock_failures"

    def test_api_metrics(self) -> None:
        """Test API metric types."""
        assert MetricType.API_REQUESTS.value == "custom.googleapis.com/ocr/api_requests"
        assert MetricType.API_LATENCY.value == "custom.googleapis.com/ocr/api_latency_ms"
        assert MetricType.API_ERRORS.value == "custom.googleapis.com/ocr/api_errors"

    def test_review_ui_metrics(self) -> None:
        """Test Review UI metric types."""
        assert MetricType.DOCUMENTS_APPROVED.value == "custom.googleapis.com/ocr/documents_approved"
        assert MetricType.DOCUMENTS_REJECTED.value == "custom.googleapis.com/ocr/documents_rejected"
        assert MetricType.DRAFTS_SAVED.value == "custom.googleapis.com/ocr/drafts_saved"
        assert MetricType.CONFLICTS_DETECTED.value == "custom.googleapis.com/ocr/conflicts_detected"


class TestMetricLabels:
    """Tests for MetricLabels dataclass."""

    def test_empty_labels(self) -> None:
        """Test empty labels to_dict."""
        labels = MetricLabels()
        assert labels.to_dict() == {}

    def test_partial_labels(self) -> None:
        """Test partial labels to_dict."""
        labels = MetricLabels(status="success", model="flash")
        result = labels.to_dict()
        assert result == {"status": "success", "model": "flash"}
        assert "document_type" not in result

    def test_full_labels(self) -> None:
        """Test full labels to_dict."""
        labels = MetricLabels(
            status="success",
            document_type="delivery_note",
            model="flash",
            error_type="syntax",
            method="GET",
            endpoint="/api/documents",
        )
        result = labels.to_dict()
        assert len(result) == 6
        assert result["status"] == "success"
        assert result["document_type"] == "delivery_note"
        assert result["model"] == "flash"
        assert result["error_type"] == "syntax"
        assert result["method"] == "GET"
        assert result["endpoint"] == "/api/documents"


class TestMetricsClient:
    """Tests for MetricsClient class."""

    def test_init_development(self) -> None:
        """Test client initialization in development."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            client = MetricsClient()
            assert client.environment == "development"
            assert client._client is None

    def test_init_with_project_id(self) -> None:
        """Test client initialization with project ID."""
        client = MetricsClient(project_id="test-project")
        assert client.project_id == "test-project"

    def test_init_production_with_monitoring_available(self) -> None:
        """Test client initialization in production with monitoring available."""
        from unittest.mock import MagicMock

        mock_monitoring = MagicMock()
        mock_client = MagicMock()
        mock_monitoring.MetricServiceClient.return_value = mock_client

        with (
            patch.dict(
                os.environ, {"ENVIRONMENT": "production", "GCP_PROJECT": "test-proj"}, clear=False
            ),
            patch.dict("sys.modules", {"google.cloud.monitoring_v3": mock_monitoring}),
        ):
            client = MetricsClient()
            client._init_cloud_monitoring()
            # If google.cloud.monitoring_v3 is mocked, it should try to init

    def test_init_production_import_error(self) -> None:
        """Test client initialization in production when monitoring not installed."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
            client = MetricsClient()
            # Should handle ImportError gracefully and set _client to None
            # When import fails, client remains None

    def test_init_cloud_monitoring_exception(self) -> None:
        """Test _init_cloud_monitoring handles exceptions."""
        from unittest.mock import MagicMock

        mock_monitoring = MagicMock()
        mock_monitoring.MetricServiceClient.side_effect = Exception("Connection error")

        with (
            patch.dict(
                os.environ, {"ENVIRONMENT": "production", "GCP_PROJECT": "test-proj"}, clear=False
            ),
            patch.dict("sys.modules", {"google.cloud.monitoring_v3": mock_monitoring}),
        ):
            client = MetricsClient()
            # Should handle exception gracefully
            client._init_cloud_monitoring()

    def test_write_to_cloud_monitoring_int_value(self) -> None:
        """Test _write_to_cloud_monitoring with int value."""
        from unittest.mock import MagicMock

        mock_monitoring = MagicMock()
        mock_client = MagicMock()

        client = MetricsClient()
        client._client = mock_client
        client._project_name = "projects/test-project"

        with patch.dict("sys.modules", {"google.cloud.monitoring_v3": mock_monitoring}):
            client._write_to_cloud_monitoring(
                "custom.googleapis.com/ocr/test", 42, {"status": "success"}
            )

    def test_write_to_cloud_monitoring_float_value(self) -> None:
        """Test _write_to_cloud_monitoring with float value."""
        from unittest.mock import MagicMock

        mock_monitoring = MagicMock()
        mock_client = MagicMock()

        client = MetricsClient()
        client._client = mock_client
        client._project_name = "projects/test-project"

        with patch.dict("sys.modules", {"google.cloud.monitoring_v3": mock_monitoring}):
            client._write_to_cloud_monitoring(
                "custom.googleapis.com/ocr/confidence", 0.95, {"document_type": "invoice"}
            )

    def test_write_to_cloud_monitoring_exception(self) -> None:
        """Test _write_to_cloud_monitoring handles exceptions."""
        from unittest.mock import MagicMock

        mock_monitoring = MagicMock()
        mock_monitoring.TimeSeries.side_effect = Exception("API error")
        mock_client = MagicMock()

        client = MetricsClient()
        client._client = mock_client
        client._project_name = "projects/test-project"

        with patch.dict("sys.modules", {"google.cloud.monitoring_v3": mock_monitoring}):
            # Should not raise
            client._write_to_cloud_monitoring("custom.googleapis.com/ocr/test", 1, {})

    def test_record_calls_cloud_monitoring_when_client_exists(self) -> None:
        """Test record calls _write_to_cloud_monitoring when client exists."""
        from unittest.mock import MagicMock

        mock_client = MagicMock()
        client = MetricsClient()
        client._client = mock_client
        client._project_name = "projects/test-project"

        with patch.object(client, "_write_to_cloud_monitoring") as mock_write:
            client.record(MetricType.DOCUMENTS_PROCESSED, 1, {"status": "success"})
            mock_write.assert_called_once()

    def test_record_with_enum(self) -> None:
        """Test recording metric with enum type."""
        client = MetricsClient()
        # Should not raise
        client.record(MetricType.DOCUMENTS_PROCESSED, 1)

    def test_record_with_string(self) -> None:
        """Test recording metric with string type."""
        client = MetricsClient()
        # Should not raise
        client.record("custom.googleapis.com/ocr/test", 42)

    def test_record_with_labels_object(self) -> None:
        """Test recording metric with MetricLabels object."""
        client = MetricsClient()
        labels = MetricLabels(status="success", document_type="delivery_note")
        # Should not raise
        client.record(MetricType.DOCUMENTS_PROCESSED, 1, labels)

    def test_record_with_labels_dict(self) -> None:
        """Test recording metric with dict labels."""
        client = MetricsClient()
        labels = {"status": "success", "model": "flash"}
        # Should not raise
        client.record(MetricType.GEMINI_FLASH_CALLS, 1, labels)

    def test_record_float_value(self) -> None:
        """Test recording metric with float value."""
        client = MetricsClient()
        # Should not raise
        client.record(MetricType.OCR_CONFIDENCE, 0.92)

    def test_record_processing_complete(self) -> None:
        """Test record_processing_complete method."""
        client = MetricsClient()
        # Should not raise
        client.record_processing_complete(
            doc_hash="sha256:abc123",
            status="COMPLETED",
            document_type="delivery_note",
            duration_ms=1500,
            attempts=1,
            model_used="flash",
        )

    def test_record_gemini_call_flash(self) -> None:
        """Test record_gemini_call for flash model."""
        client = MetricsClient()
        # Should not raise
        client.record_gemini_call(
            model="flash",
            input_tokens=2000,
            output_tokens=500,
            success=True,
            duration_ms=800,
        )

    def test_record_gemini_call_pro(self) -> None:
        """Test record_gemini_call for pro model."""
        client = MetricsClient()
        # Should not raise
        client.record_gemini_call(
            model="pro",
            input_tokens=10000,
            output_tokens=1000,
            success=True,
            duration_ms=3000,
        )

    def test_record_gemini_call_failure(self) -> None:
        """Test record_gemini_call for failed call."""
        client = MetricsClient()
        # Should not raise
        client.record_gemini_call(
            model="flash",
            input_tokens=2000,
            output_tokens=0,
            success=False,
            duration_ms=100,
        )

    def test_record_ocr_confidence_high(self) -> None:
        """Test record_ocr_confidence with high confidence."""
        client = MetricsClient()
        # Should not raise
        client.record_ocr_confidence(0.95, document_type="delivery_note")

    def test_record_ocr_confidence_low(self) -> None:
        """Test record_ocr_confidence with low confidence."""
        client = MetricsClient()
        # Should not raise - should also record low confidence count
        client.record_ocr_confidence(0.75, document_type="invoice")

    def test_record_validation_result_passed(self) -> None:
        """Test record_validation_result when passed."""
        client = MetricsClient()
        # Should not raise
        client.record_validation_result(
            gate_passed=True,
            gate_errors=0,
            quality_warnings=2,
            document_type="delivery_note",
        )

    def test_record_validation_result_failed(self) -> None:
        """Test record_validation_result when failed."""
        client = MetricsClient()
        # Should not raise
        client.record_validation_result(
            gate_passed=False,
            gate_errors=3,
            quality_warnings=1,
        )

    def test_record_saga_execution_success(self) -> None:
        """Test record_saga_execution for success."""
        client = MetricsClient()
        # Should not raise
        client.record_saga_execution(
            success=True,
            steps_completed=4,
        )

    def test_record_saga_execution_with_compensation(self) -> None:
        """Test record_saga_execution with compensation."""
        client = MetricsClient()
        # Should not raise
        client.record_saga_execution(
            success=False,
            steps_completed=2,
            compensation_needed=True,
        )

    def test_record_lock_operation_acquired(self) -> None:
        """Test record_lock_operation when acquired."""
        client = MetricsClient()
        # Should not raise
        client.record_lock_operation(acquired=True)

    def test_record_lock_operation_failed(self) -> None:
        """Test record_lock_operation when failed."""
        client = MetricsClient()
        # Should not raise
        client.record_lock_operation(acquired=False, contention=True)

    def test_record_api_request_success(self) -> None:
        """Test record_api_request for successful request."""
        client = MetricsClient()
        # Should not raise
        client.record_api_request(
            method="GET",
            endpoint="/api/documents",
            status_code=200,
            duration_ms=50,
        )

    def test_record_api_request_error(self) -> None:
        """Test record_api_request for error request."""
        client = MetricsClient()
        # Should not raise
        client.record_api_request(
            method="POST",
            endpoint="/api/documents/abc123",
            status_code=500,
            duration_ms=100,
        )

    def test_record_review_action_approved(self) -> None:
        """Test record_review_action for approval."""
        client = MetricsClient()
        # Should not raise
        client.record_review_action("approved", "delivery_note")

    def test_record_review_action_rejected(self) -> None:
        """Test record_review_action for rejection."""
        client = MetricsClient()
        # Should not raise
        client.record_review_action("rejected", "invoice")

    def test_record_review_action_draft(self) -> None:
        """Test record_review_action for draft save."""
        client = MetricsClient()
        # Should not raise
        client.record_review_action("draft_saved")

    def test_record_review_action_conflict(self) -> None:
        """Test record_review_action for conflict."""
        client = MetricsClient()
        # Should not raise
        client.record_review_action("conflict")

    def test_record_budget_status(self) -> None:
        """Test record_budget_status."""
        client = MetricsClient()
        # Should not raise
        client.record_budget_status(
            daily_used=10,
            daily_limit=50,
            monthly_used=100,
            monthly_limit=1000,
        )


class TestGetMetricsClient:
    """Tests for get_metrics_client function."""

    def test_returns_client(self) -> None:
        """Test that function returns a MetricsClient."""
        get_metrics_client.cache_clear()
        client = get_metrics_client()
        assert isinstance(client, MetricsClient)

    def test_returns_singleton(self) -> None:
        """Test that function returns same instance."""
        get_metrics_client.cache_clear()
        client1 = get_metrics_client()
        client2 = get_metrics_client()
        assert client1 is client2


class TestRecordMetric:
    """Tests for record_metric convenience function."""

    def test_record_with_enum(self) -> None:
        """Test convenience function with enum."""
        get_metrics_client.cache_clear()
        # Should not raise
        record_metric(MetricType.DOCUMENTS_PROCESSED, 1)

    def test_record_with_labels(self) -> None:
        """Test convenience function with labels."""
        get_metrics_client.cache_clear()
        # Should not raise
        record_metric(
            MetricType.GEMINI_FLASH_CALLS,
            1,
            {"status": "success", "model": "flash"},
        )


class TestProcessingTimer:
    """Tests for ProcessingTimer context manager."""

    def test_timer_measures_duration(self) -> None:
        """Test that timer measures duration."""
        import time

        with ProcessingTimer("sha256:abc123") as timer:
            time.sleep(0.01)  # 10ms

        # Should have measured at least 10ms
        assert timer.duration_ms >= 10

    def test_timer_record(self) -> None:
        """Test timer record method."""
        with ProcessingTimer("sha256:abc123") as timer:
            pass

        # Should not raise
        timer.record(
            status="COMPLETED",
            document_type="delivery_note",
            attempts=1,
            model_used="flash",
        )

    def test_timer_stores_doc_hash(self) -> None:
        """Test timer stores document hash."""
        with ProcessingTimer("sha256:test123") as timer:
            pass

        assert timer.doc_hash == "sha256:test123"

    def test_timer_default_values(self) -> None:
        """Test timer with default record values."""
        with ProcessingTimer("sha256:abc123") as timer:
            pass

        # Should not raise with defaults
        timer.record(status="COMPLETED", document_type="delivery_note")
