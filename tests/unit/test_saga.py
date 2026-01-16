"""
Unit tests for Saga Pattern implementation.

See: docs/specs/03_saga.md
"""

from __future__ import annotations

from unittest.mock import Mock, patch

from src.core.saga import (
    DocumentPersistenceSteps,
    SagaFailedError,
    SagaOrchestrator,
    SagaResult,
    SagaStep,
    generate_failed_report,
    persist_document,
)


class TestSagaStep:
    """Tests for SagaStep dataclass."""

    def test_saga_step_creation(self) -> None:
        """Test creating a SagaStep."""
        execute_fn = Mock()
        compensate_fn = Mock()

        step = SagaStep(
            name="test_step",
            execute=execute_fn,
            compensate=compensate_fn,
        )

        assert step.name == "test_step"
        assert step.execute == execute_fn
        assert step.compensate == compensate_fn


class TestSagaResult:
    """Tests for SagaResult dataclass."""

    def test_saga_result_success(self) -> None:
        """Test successful SagaResult."""
        result = SagaResult(
            success=True,
            executed_steps=["step1", "step2"],
        )

        assert result.success is True
        assert result.executed_steps == ["step1", "step2"]
        assert result.failed_step is None
        assert result.compensated_steps == []
        assert result.error is None

    def test_saga_result_failure(self) -> None:
        """Test failed SagaResult."""
        result = SagaResult(
            success=False,
            executed_steps=["step1"],
            failed_step="step2",
            compensated_steps=["step1"],
            error="Test error",
        )

        assert result.success is False
        assert result.failed_step == "step2"
        assert result.compensated_steps == ["step1"]
        assert result.error == "Test error"


class TestSagaOrchestrator:
    """Tests for SagaOrchestrator class."""

    def test_all_steps_succeed(self) -> None:
        """Happy path: all steps execute successfully."""
        executed = []
        compensated = []

        steps = [
            SagaStep(
                name="step1",
                execute=lambda: executed.append("step1"),
                compensate=lambda: compensated.append("step1"),
            ),
            SagaStep(
                name="step2",
                execute=lambda: executed.append("step2"),
                compensate=lambda: compensated.append("step2"),
            ),
            SagaStep(
                name="step3",
                execute=lambda: executed.append("step3"),
                compensate=lambda: compensated.append("step3"),
            ),
        ]

        saga = SagaOrchestrator()
        result = saga.execute(steps)

        assert result.success is True
        assert executed == ["step1", "step2", "step3"]
        assert compensated == []
        assert result.executed_steps == ["step1", "step2", "step3"]

    def test_first_step_fails_no_compensation(self) -> None:
        """When first step fails, no compensation needed."""
        executed = []
        compensated = []

        def fail_step1() -> None:
            executed.append("step1")
            raise Exception("Step 1 failed")

        steps = [
            SagaStep(
                name="step1",
                execute=fail_step1,
                compensate=lambda: compensated.append("step1"),
            ),
            SagaStep(
                name="step2",
                execute=lambda: executed.append("step2"),
                compensate=lambda: compensated.append("step2"),
            ),
        ]

        saga = SagaOrchestrator()
        result = saga.execute(steps)

        assert result.success is False
        assert result.failed_step == "step1"
        assert executed == ["step1"]
        # No compensation because step1 wasn't added to executed_steps before failing
        assert compensated == []

    def test_second_step_fails_compensates_first(self) -> None:
        """When step 2 fails, step 1 is compensated."""
        executed = []
        compensated = []

        def fail_step2() -> None:
            executed.append("step2")
            raise Exception("Step 2 failed")

        steps = [
            SagaStep(
                name="step1",
                execute=lambda: executed.append("step1"),
                compensate=lambda: compensated.append("step1"),
            ),
            SagaStep(
                name="step2",
                execute=fail_step2,
                compensate=lambda: compensated.append("step2"),
            ),
        ]

        saga = SagaOrchestrator()
        result = saga.execute(steps)

        assert result.success is False
        assert result.failed_step == "step2"
        assert executed == ["step1", "step2"]
        assert compensated == ["step1"]  # Only step1 compensated
        assert result.compensated_steps == ["step1"]

    def test_third_step_fails_compensates_in_reverse_order(self) -> None:
        """When step 3 fails, steps 2 and 1 are compensated in reverse order."""
        executed = []
        compensated = []

        def fail_step3() -> None:
            executed.append("step3")
            raise Exception("Step 3 failed")

        steps = [
            SagaStep(
                name="step1",
                execute=lambda: executed.append("step1"),
                compensate=lambda: compensated.append("step1"),
            ),
            SagaStep(
                name="step2",
                execute=lambda: executed.append("step2"),
                compensate=lambda: compensated.append("step2"),
            ),
            SagaStep(
                name="step3",
                execute=fail_step3,
                compensate=lambda: compensated.append("step3"),
            ),
        ]

        saga = SagaOrchestrator()
        result = saga.execute(steps)

        assert result.success is False
        assert result.failed_step == "step3"
        assert executed == ["step1", "step2", "step3"]
        # Compensated in reverse order
        assert compensated == ["step2", "step1"]

    def test_compensation_failure_logged_but_continues(self) -> None:
        """If compensation fails, continue compensating other steps."""
        executed = []
        compensated = []

        def fail_step2_compensation() -> None:
            raise Exception("Compensation failed")

        def fail_step3() -> None:
            executed.append("step3")
            raise Exception("Step 3 failed")

        steps = [
            SagaStep(
                name="step1",
                execute=lambda: executed.append("step1"),
                compensate=lambda: compensated.append("step1"),
            ),
            SagaStep(
                name="step2",
                execute=lambda: executed.append("step2"),
                compensate=fail_step2_compensation,
            ),
            SagaStep(
                name="step3",
                execute=fail_step3,
                compensate=lambda: compensated.append("step3"),
            ),
        ]

        saga = SagaOrchestrator()
        result = saga.execute(steps)

        assert result.success is False
        # step1 should still be compensated even though step2 compensation failed
        assert "step1" in compensated
        # step2 compensation failure should be recorded
        assert len(result.compensation_failures) == 1
        assert result.compensation_failures[0][0] == "step2"

    def test_empty_steps_list(self) -> None:
        """Empty steps list should succeed immediately."""
        saga = SagaOrchestrator()
        result = saga.execute([])

        assert result.success is True
        assert result.executed_steps == []


class TestGenerateFailedReport:
    """Tests for generate_failed_report function."""

    def test_basic_report_generation(self) -> None:
        """Test basic report generation."""
        report = generate_failed_report(
            doc_hash="test-hash-123",
            source_path="gs://bucket/input/test.pdf",
            attempts=[{"attempt": 1, "model": "flash", "error": "Parse error"}],
            errors=["Invalid management_id format"],
        )

        assert "test-hash-123" in report
        assert "gs://bucket/input/test.pdf" in report
        assert "Invalid management_id format" in report
        assert "flash" in report
        assert "Processing Failed Report" in report

    def test_report_with_saga_error(self) -> None:
        """Test report generation with saga error."""
        saga_error = SagaFailedError("gcs_copy", Exception("GCS unavailable"))

        report = generate_failed_report(
            doc_hash="test-hash-456",
            source_path="gs://bucket/input/test2.pdf",
            attempts=[],
            errors=["Test error"],
            saga_error=saga_error,
        )

        assert "Saga Error" in report
        assert "gcs_copy" in report
        assert "GCS unavailable" in report

    def test_report_with_multiple_attempts(self) -> None:
        """Test report with multiple extraction attempts."""
        attempts = [
            {"attempt": 1, "model": "flash", "success": False},
            {"attempt": 2, "model": "flash", "success": False},
            {"attempt": 3, "model": "pro", "success": False},
        ]

        report = generate_failed_report(
            doc_hash="test-hash-789",
            source_path="gs://bucket/input/test3.pdf",
            attempts=attempts,
            errors=["Error 1", "Error 2"],
        )

        assert "Attempt 1" in report
        assert "Attempt 2" in report
        assert "Attempt 3" in report
        assert "Error 1" in report
        assert "Error 2" in report


class TestDocumentPersistenceSteps:
    """Tests for DocumentPersistenceSteps factory."""

    def test_create_all_steps(self) -> None:
        """Test creating all persistence steps."""
        mock_db = Mock()
        mock_storage = Mock()

        factory = DocumentPersistenceSteps(
            db_client=mock_db,
            storage_client=mock_storage,
            doc_hash="test-hash",
            validated_json={"management_id": "TEST-001"},
            source_path="gs://bucket/input/test.pdf",
            dest_path="gs://bucket/output/TEST-001.pdf",
            schema_version="delivery_note/v2",
        )

        steps = factory.create_all_steps()

        assert len(steps) == 4
        assert steps[0].name == "db_pending"
        assert steps[1].name == "gcs_copy"
        assert steps[2].name == "gcs_delete_source"
        assert steps[3].name == "db_complete"

    def test_db_pending_step(self) -> None:
        """Test db_pending step execution."""
        mock_db = Mock()
        mock_doc_ref = Mock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        factory = DocumentPersistenceSteps(
            db_client=mock_db,
            storage_client=Mock(),
            doc_hash="test-hash",
            validated_json={"management_id": "TEST-001"},
            source_path="gs://bucket/input/test.pdf",
            dest_path="gs://bucket/output/TEST-001.pdf",
            schema_version="delivery_note/v2",
        )

        step = factory.create_db_pending_step()
        step.execute()

        mock_db.collection.assert_called_with("processed_documents")
        mock_doc_ref.update.assert_called_once()
        call_args = mock_doc_ref.update.call_args[0][0]
        assert call_args["status"] == "PENDING"
        assert call_args["validated_json"] == {"management_id": "TEST-001"}

    def test_db_pending_compensation(self) -> None:
        """Test db_pending step compensation."""
        mock_db = Mock()
        mock_doc_ref = Mock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        factory = DocumentPersistenceSteps(
            db_client=mock_db,
            storage_client=Mock(),
            doc_hash="test-hash",
            validated_json={},
            source_path="gs://bucket/input/test.pdf",
            dest_path="gs://bucket/output/test.pdf",
            schema_version="v1",
        )

        step = factory.create_db_pending_step()
        step.compensate()

        call_args = mock_doc_ref.update.call_args[0][0]
        assert call_args["status"] == "FAILED"


class TestPersistDocument:
    """Tests for persist_document function."""

    @patch("src.core.saga.DocumentPersistenceSteps")
    def test_persist_document_success(self, mock_steps_class: Mock) -> None:
        """Test successful document persistence."""
        mock_db = Mock()
        mock_storage = Mock()

        # Setup mock steps that succeed
        mock_steps = [
            SagaStep("step1", lambda: None, lambda: None),
        ]
        mock_factory = Mock()
        mock_factory.create_all_steps.return_value = mock_steps
        mock_steps_class.return_value = mock_factory

        result = persist_document(
            db_client=mock_db,
            storage_client=mock_storage,
            doc_hash="test-hash",
            validated_json={"management_id": "TEST-001"},
            source_path="gs://bucket/input/test.pdf",
            dest_path="gs://bucket/output/TEST-001.pdf",
            schema_version="v2",
        )

        assert result.success is True

    @patch("src.core.saga.DocumentPersistenceSteps")
    def test_persist_document_failure(self, mock_steps_class: Mock) -> None:
        """Test document persistence failure."""
        mock_db = Mock()
        mock_storage = Mock()

        def fail_step() -> None:
            raise Exception("Test failure")

        # Setup mock steps that fail
        mock_steps = [
            SagaStep("step1", fail_step, lambda: None),
        ]
        mock_factory = Mock()
        mock_factory.create_all_steps.return_value = mock_steps
        mock_steps_class.return_value = mock_factory

        result = persist_document(
            db_client=mock_db,
            storage_client=mock_storage,
            doc_hash="test-hash",
            validated_json={},
            source_path="gs://bucket/input/test.pdf",
            dest_path="gs://bucket/output/test.pdf",
            schema_version="v1",
        )

        assert result.success is False
        assert result.failed_step == "step1"


class TestSagaFailedError:
    """Tests for SagaFailedError exception."""

    def test_saga_failed_error_message(self) -> None:
        """Test SagaFailedError message format."""
        original_error = ValueError("Original error")
        error = SagaFailedError("test_step", original_error)

        assert error.step_name == "test_step"
        assert error.original_error == original_error
        assert "test_step" in str(error)
        assert "Original error" in str(error)
