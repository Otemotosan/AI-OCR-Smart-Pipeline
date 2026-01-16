"""
Saga Pattern for Atomic Operations.

Ensures atomic persistence through compensation transactions.
When any step fails, previously executed steps are rolled back in reverse order.

See: docs/specs/03_saga.md
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SagaFailedError(Exception):
    """Raised when saga execution fails."""

    def __init__(self, step_name: str, original_error: Exception) -> None:
        self.step_name = step_name
        self.original_error = original_error
        super().__init__(f"Saga failed at step '{step_name}': {original_error}")


class CompensationFailedError(Exception):
    """Raised when compensation fails during rollback."""

    def __init__(
        self,
        step_name: str,
        original_error: Exception,
        compensation_errors: list[tuple[str, Exception]],
    ) -> None:
        self.step_name = step_name
        self.original_error = original_error
        self.compensation_errors = compensation_errors
        super().__init__(
            f"Saga failed at '{step_name}' and compensation also failed for: "
            f"{[name for name, _ in compensation_errors]}"
        )


@dataclass
class SagaStep:
    """
    A single step in the saga with its compensation.

    Attributes:
        name: Human-readable step identifier for logging
        execute: Callable that performs the forward operation
        compensate: Callable that reverses the forward operation
    """

    name: str
    execute: Callable[[], None]
    compensate: Callable[[], None]


@dataclass
class SagaResult:
    """
    Result of saga execution.

    Attributes:
        success: Whether all steps completed successfully
        executed_steps: List of step names that were executed
        failed_step: Name of the step that failed (if any)
        compensated_steps: List of step names that were compensated
        compensation_failures: List of (step_name, error) for failed compensations
        error: The original error that caused the failure
    """

    success: bool
    executed_steps: list[str] = field(default_factory=list)
    failed_step: str | None = None
    compensated_steps: list[str] = field(default_factory=list)
    compensation_failures: list[tuple[str, str]] = field(default_factory=list)
    error: str | None = None


class SagaOrchestrator:
    """
    Executes saga steps in order.
    On failure, compensates in reverse order.

    Usage:
        saga = SagaOrchestrator()
        result = saga.execute([
            SagaStep("step1", execute_fn1, compensate_fn1),
            SagaStep("step2", execute_fn2, compensate_fn2),
        ])

    Thread Safety:
        Each instance should be used for a single execution.
        Create a new instance for each saga execution.
    """

    def __init__(self) -> None:
        self._executed_steps: list[SagaStep] = []

    def execute(self, steps: list[SagaStep]) -> SagaResult:
        """
        Execute all saga steps.

        Args:
            steps: Ordered list of saga steps to execute

        Returns:
            SagaResult with execution details

        Note:
            Does NOT raise on failure - check result.success instead.
            This allows callers to handle failures gracefully.
        """
        self._executed_steps = []
        result = SagaResult(success=True, executed_steps=[])

        for step in steps:
            try:
                logger.info("saga_step_starting", step_name=step.name)
                step.execute()
                self._executed_steps.append(step)
                result.executed_steps.append(step.name)
                logger.info("saga_step_completed", step_name=step.name)

            except Exception as e:
                logger.error(
                    "saga_step_failed",
                    step_name=step.name,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                result.success = False
                result.failed_step = step.name
                result.error = str(e)

                # Rollback executed steps
                self._rollback(result)
                return result

        logger.info(
            "saga_completed",
            success=True,
            steps_executed=len(result.executed_steps),
        )
        return result

    def _rollback(self, result: SagaResult) -> None:
        """
        Execute compensations in reverse order.

        Best-effort: continues compensating even if some compensations fail.
        All compensation failures are logged and recorded in result.
        """
        logger.warning(
            "saga_rollback_starting",
            steps_to_compensate=len(self._executed_steps),
        )

        for step in reversed(self._executed_steps):
            try:
                logger.info("saga_compensating", step_name=step.name)
                step.compensate()
                result.compensated_steps.append(step.name)
                logger.info("saga_compensated", step_name=step.name)

            except Exception as e:
                # Log but continue - best effort compensation
                logger.error(
                    "saga_compensation_failed",
                    step_name=step.name,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                result.compensation_failures.append((step.name, str(e)))

        logger.warning(
            "saga_rollback_completed",
            compensated=len(result.compensated_steps),
            failed=len(result.compensation_failures),
        )


def generate_failed_report(
    doc_hash: str,
    source_path: str,
    attempts: list[dict[str, Any]],
    errors: list[str],
    saga_error: SagaFailedError | None = None,
) -> str:
    """
    Generate FAILED_REPORT.md content for human review.

    Args:
        doc_hash: SHA-256 hash of the document
        source_path: Original GCS path of the document
        attempts: List of extraction attempt details
        errors: List of validation error messages
        saga_error: Optional saga failure details

    Returns:
        Markdown-formatted report string
    """
    timestamp = datetime.now(UTC).isoformat()

    report = f"""# Processing Failed Report

## Document Information
- **Hash**: `{doc_hash}`
- **Source**: `{source_path}`
- **Failed At**: {timestamp}

## Extraction Attempts
"""

    for i, attempt in enumerate(attempts, 1):
        # Sanitize attempt data for display
        attempt_json = json.dumps(attempt, indent=2, ensure_ascii=False, default=str)
        report += f"""
### Attempt {i}
```json
{attempt_json}
```
"""

    report += """
## Validation Errors
"""
    for error in errors:
        report += f"- {error}\n"

    if saga_error:
        report += f"""
## Saga Error
- **Failed Step**: {saga_error.step_name}
- **Error**: {saga_error.original_error}
"""

    report += f"""
## Required Action
Manual review required in the Review UI.

[Open in Review UI](https://review.example.com/document/{doc_hash})
"""

    return report


class DocumentPersistenceSteps:
    """
    Factory for creating standard document persistence saga steps.

    This class provides methods to create SagaStep instances for common
    document persistence operations.
    """

    def __init__(
        self,
        db_client: Any,
        storage_client: Any,
        doc_hash: str,
        validated_json: dict[str, Any],
        source_path: str,
        dest_path: str,
        schema_version: str,
    ) -> None:
        """
        Initialize with required clients and document info.

        Args:
            db_client: Database client (Firestore)
            storage_client: GCS storage client
            doc_hash: Document hash (unique identifier)
            validated_json: Validated extraction result
            source_path: Source GCS URI
            dest_path: Destination GCS URI
            schema_version: Schema version string
        """
        self.db_client = db_client
        self.storage_client = storage_client
        self.doc_hash = doc_hash
        self.validated_json = validated_json
        self.source_path = source_path
        self.dest_path = dest_path
        self.schema_version = schema_version

    def create_db_pending_step(self) -> SagaStep:
        """Create step for updating DB status to PENDING."""

        def execute() -> None:
            doc_ref = self.db_client.collection("processed_documents").document(self.doc_hash)
            doc_ref.update(
                {
                    "status": "PENDING",
                    "validated_json": self.validated_json,
                    "schema_version": self.schema_version,
                    "gcs_output_path": self.dest_path,
                    "updated_at": datetime.now(UTC),
                }
            )

        def compensate() -> None:
            doc_ref = self.db_client.collection("processed_documents").document(self.doc_hash)
            doc_ref.update(
                {
                    "status": "FAILED",
                    "error_message": "Saga rollback at db_pending",
                    "updated_at": datetime.now(UTC),
                }
            )

        return SagaStep(name="db_pending", execute=execute, compensate=compensate)

    def create_gcs_copy_step(self) -> SagaStep:
        """Create step for copying file to destination."""
        from src.core.storage import copy_blob, delete_blob

        def execute() -> None:
            copy_blob(self.storage_client, self.source_path, self.dest_path)

        def compensate() -> None:
            delete_blob(self.storage_client, self.dest_path, ignore_not_found=True)

        return SagaStep(name="gcs_copy", execute=execute, compensate=compensate)

    def create_gcs_delete_source_step(self) -> SagaStep:
        """Create step for deleting source file."""
        from src.core.storage import copy_blob, delete_blob

        def execute() -> None:
            delete_blob(self.storage_client, self.source_path)

        def compensate() -> None:
            # Restore source from destination
            copy_blob(self.storage_client, self.dest_path, self.source_path)

        return SagaStep(name="gcs_delete_source", execute=execute, compensate=compensate)

    def create_db_complete_step(self) -> SagaStep:
        """Create step for updating DB status to COMPLETED."""

        def execute() -> None:
            doc_ref = self.db_client.collection("processed_documents").document(self.doc_hash)
            doc_ref.update(
                {
                    "status": "COMPLETED",
                    "completed_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            )

        def compensate() -> None:
            # Final step - no compensation needed
            pass

        return SagaStep(name="db_complete", execute=execute, compensate=compensate)

    def create_all_steps(self) -> list[SagaStep]:
        """Create all standard persistence steps in order."""
        return [
            self.create_db_pending_step(),
            self.create_gcs_copy_step(),
            self.create_gcs_delete_source_step(),
            self.create_db_complete_step(),
        ]


def persist_document(
    db_client: Any,
    storage_client: Any,
    doc_hash: str,
    validated_json: dict[str, Any],
    source_path: str,
    dest_path: str,
    schema_version: str,
) -> SagaResult:
    """
    Atomically persist document using Saga pattern.

    This is the main entry point for document persistence. It:
    1. Updates DB status to PENDING
    2. Copies file to destination in GCS
    3. Deletes source file
    4. Updates DB status to COMPLETED

    On any failure, it compensates in reverse order.

    Args:
        db_client: Firestore client
        storage_client: GCS storage client
        doc_hash: SHA-256 hash of document
        validated_json: Validated extraction result
        source_path: gs://bucket/input/original.pdf
        dest_path: gs://bucket/output/ID_Company_Date.pdf
        schema_version: e.g., "delivery_note/v2"

    Returns:
        SagaResult with success status and execution details
    """
    logger.info(
        "saga_started",
        doc_hash=doc_hash,
        source_path=source_path,
        dest_path=dest_path,
        schema_version=schema_version,
    )

    steps_factory = DocumentPersistenceSteps(
        db_client=db_client,
        storage_client=storage_client,
        doc_hash=doc_hash,
        validated_json=validated_json,
        source_path=source_path,
        dest_path=dest_path,
        schema_version=schema_version,
    )

    saga = SagaOrchestrator()
    result = saga.execute(steps_factory.create_all_steps())

    if result.success:
        logger.info(
            "saga_completed_success",
            doc_hash=doc_hash,
            dest_path=dest_path,
        )
    else:
        logger.error(
            "saga_completed_failure",
            doc_hash=doc_hash,
            failed_step=result.failed_step,
            error=result.error,
            compensated_steps=result.compensated_steps,
            compensation_failures=result.compensation_failures,
        )

    return result
