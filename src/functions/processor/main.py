"""
Document Processor Cloud Function Entry Point.

This is the main entry point for the OCR pipeline that:
1. Acquires distributed lock for idempotency
2. Processes document with Document AI
3. Extracts data using Gemini with self-correction
4. Validates with Gate and Quality linters
5. Persists using Saga pattern
6. Inserts into BigQuery for analytics

See: All docs/specs/*.md
"""

from __future__ import annotations

import contextlib
import os
import time
from datetime import UTC, datetime
from typing import Any

import functions_framework
import structlog
from cloudevents.http import CloudEvent
from google.cloud import firestore, storage

from src.core.bigquery_client import BigQueryClient, BigQueryConfig
from src.core.database import AuditEventType, DatabaseClient, DocumentStatus
from src.core.docai import DocumentAIClient
from src.core.extraction import extract_with_retry
from src.core.linters.gate import GateLinter
from src.core.linters.quality import QualityLinter

# Import core modules
from src.core.lock import DistributedLock, LockNotAcquiredError
from src.core.saga import generate_failed_report, persist_document
from src.core.storage import (
    StorageClient,
    generate_destination_path,
    parse_gcs_path,
    upload_string,
)

logger = structlog.get_logger(__name__)

# Configuration from environment variables
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "")
QUARANTINE_BUCKET = os.environ.get("QUARANTINE_BUCKET", "")
BIGQUERY_DATASET = os.environ.get("BIGQUERY_DATASET", "ocr_pipeline")
DOCUMENT_AI_PROCESSOR = os.environ.get("DOCUMENT_AI_PROCESSOR", "")

# Timeout configuration (Cloud Functions 2nd Gen max is 60 minutes)
FUNCTION_TIMEOUT_SECONDS = int(os.environ.get("FUNCTION_TIMEOUT", "540"))
SAFETY_MARGIN_SECONDS = 30  # Stop processing before hard timeout


class ProcessingError(Exception):
    """Raised when document processing fails."""

    pass


@functions_framework.cloud_event
def process_document(event: CloudEvent) -> str:
    """
    Cloud Function entry point for document processing.

    Triggered by Cloud Storage object finalization events.

    Args:
        event: CloudEvent containing GCS object metadata

    Returns:
        Status message string
    """
    start_time = time.time()
    execution_id = os.environ.get("FUNCTION_EXECUTION_ID", "local")

    # Extract event data
    data = event.data
    bucket_name = data.get("bucket", "")
    object_name = data.get("name", "")
    gcs_uri = f"gs://{bucket_name}/{object_name}"

    logger.info(
        "document_received",
        execution_id=execution_id,
        bucket=bucket_name,
        object_name=object_name,
        gcs_uri=gcs_uri,
    )

    # Skip non-PDF files
    if not object_name.lower().endswith(".pdf"):
        logger.info(
            "skipping_non_pdf",
            object_name=object_name,
        )
        return "SKIPPED: Not a PDF file"

    # Initialize clients
    storage_client = storage.Client()
    firestore_client = firestore.Client()
    db_client = DatabaseClient(firestore_client)
    storage_ops = StorageClient(storage_client)

    # Initialize BigQuery client
    bq_config = BigQueryConfig(
        project_id=PROJECT_ID,
        dataset_id=BIGQUERY_DATASET,
    )
    bq_client = BigQueryClient(bq_config)

    # Compute file hash for idempotency
    bucket_name, blob_name = parse_gcs_path(gcs_uri)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    file_content = blob.download_as_bytes()
    doc_hash = DistributedLock.compute_file_hash(file_content)

    logger.info(
        "document_hash_computed",
        doc_hash=doc_hash,
        gcs_uri=gcs_uri,
    )

    # Try to acquire distributed lock
    try:
        with DistributedLock(firestore_client, doc_hash) as lock:
            logger.info(
                "lock_acquired",
                doc_hash=doc_hash,
                ttl_seconds=lock.ttl_seconds,
            )

            # Process the document
            result = _process_document_internal(
                doc_hash=doc_hash,
                gcs_uri=gcs_uri,
                storage_client=storage_client,
                storage_ops=storage_ops,
                db_client=db_client,
                bq_client=bq_client,
                start_time=start_time,
            )

            return result

    except LockNotAcquiredError as e:
        logger.info(
            "lock_skipped_duplicate",
            doc_hash=doc_hash,
            reason=str(e),
        )
        return f"SKIPPED: {e}"

    except Exception as e:
        logger.error(
            "processing_failed_unexpected",
            doc_hash=doc_hash,
            error=str(e),
            error_type=type(e).__name__,
        )
        return f"FAILED: Unexpected error: {e}"


def _process_document_internal(  # noqa: C901 - Pipeline orchestration requires multiple steps
    doc_hash: str,
    gcs_uri: str,
    storage_client: storage.Client,
    storage_ops: StorageClient,
    db_client: DatabaseClient,
    bq_client: BigQueryClient,
    start_time: float,
) -> str:
    """
    Internal document processing logic.

    Args:
        doc_hash: Document hash for tracking
        gcs_uri: Source GCS URI
        storage_client: GCS client
        storage_ops: Storage operations client
        db_client: Database client
        bq_client: BigQuery client
        start_time: Processing start time

    Returns:
        Status message string
    """
    attempts: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        # Check timeout
        _check_timeout(start_time, "start")

        # Step 1: Create database record
        logger.info("creating_db_record", doc_hash=doc_hash)
        db_client.create_document(doc_hash, gcs_uri, DocumentStatus.PROCESSING)

        # Step 2: Process with Document AI
        _check_timeout(start_time, "docai")
        logger.info("processing_with_docai", doc_hash=doc_hash)

        docai_client = DocumentAIClient(processor_name=DOCUMENT_AI_PROCESSOR)
        docai_result = docai_client.process_document(gcs_uri)

        logger.info(
            "docai_completed",
            doc_hash=doc_hash,
            confidence=docai_result.confidence,
            page_count=docai_result.page_count,
            detected_type=docai_result.detected_type,
        )

        # Step 3: Extract data using Gemini with self-correction
        _check_timeout(start_time, "extraction")
        logger.info("extracting_with_gemini", doc_hash=doc_hash)

        extraction_result = extract_with_retry(
            markdown=docai_result.markdown,
            confidence=docai_result.confidence,
            detected_type=docai_result.detected_type,
            image_bytes=None,  # Will be fetched if needed
            gcs_uri=gcs_uri,
            storage_client=storage_client,
        )

        # Record all attempts
        attempts = extraction_result.attempts

        if extraction_result.status == "FAILED":
            errors.append("Extraction failed after all retry attempts")
            for attempt in attempts:
                if attempt.get("error"):
                    errors.append(f"Attempt {attempt.get('attempt', '?')}: {attempt.get('error')}")

            raise ProcessingError("Extraction failed")

        extracted_data = extraction_result.schema.model_dump() if extraction_result.schema else {}
        document_type = extracted_data.get("document_type", "unknown")
        schema_version = f"{document_type}/v{extracted_data.get('schema_version', '1')}"

        logger.info(
            "extraction_completed",
            doc_hash=doc_hash,
            document_type=document_type,
            schema_version=schema_version,
            final_model=extraction_result.final_model,
            attempts_count=len(attempts),
        )

        # Step 4: Validate with Gate Linter
        _check_timeout(start_time, "validation")
        logger.info("validating_with_gate_linter", doc_hash=doc_hash)

        gate_linter = GateLinter()
        gate_result = gate_linter.validate(extracted_data)

        if not gate_result.passed:
            errors.extend(gate_result.errors)
            logger.error(
                "gate_linter_failed",
                doc_hash=doc_hash,
                errors=gate_result.errors,
            )
            raise ProcessingError(f"Gate Linter failed: {gate_result.errors}")

        logger.info("gate_linter_passed", doc_hash=doc_hash)

        # Step 5: Quality Linter (warnings only)
        quality_linter = QualityLinter()
        quality_result = quality_linter.validate(extracted_data)
        quality_warnings = [w.message for w in quality_result.warnings]

        if quality_warnings:
            logger.info(
                "quality_warnings",
                doc_hash=doc_hash,
                warnings=quality_warnings,
            )

        # Step 6: Save extraction results
        db_client.save_extraction(
            doc_id=doc_hash,
            extracted_data=extracted_data,
            attempts=attempts,
            schema_version=schema_version,
            quality_warnings=quality_warnings,
        )

        # Step 7: Generate destination path and persist with Saga
        _check_timeout(start_time, "persistence")
        logger.info("persisting_document", doc_hash=doc_hash)

        dest_path = generate_destination_path(
            schema_data=extracted_data,
            timestamp=datetime.now(UTC),
            output_bucket=OUTPUT_BUCKET,
        )

        saga_result = persist_document(
            db_client=db_client.client,
            storage_client=storage_client,
            doc_hash=doc_hash,
            validated_json=extracted_data,
            source_path=gcs_uri,
            dest_path=dest_path,
            schema_version=schema_version,
        )

        if not saga_result.success:
            errors.append(f"Saga failed at step: {saga_result.failed_step}")
            if saga_result.error:
                errors.append(saga_result.error)
            raise ProcessingError(f"Saga failed: {saga_result.failed_step}")

        # Step 8: Insert into BigQuery
        _check_timeout(start_time, "bigquery")
        logger.info("inserting_into_bigquery", doc_hash=doc_hash)

        processing_duration_ms = int((time.time() - start_time) * 1000)

        bq_client.insert_extraction(
            document_id=doc_hash,
            document_type=document_type,
            schema_version=schema_version,
            extracted_data=extracted_data,
            source_uri=gcs_uri,
            destination_uri=dest_path,
            confidence_score=docai_result.confidence,
            model_used=extraction_result.final_model,
            attempts_count=len(attempts),
            processing_duration_ms=processing_duration_ms,
            quality_warnings=quality_warnings,
        )

        # Step 9: Log success
        duration_seconds = time.time() - start_time
        logger.info(
            "processing_completed",
            doc_hash=doc_hash,
            status="COMPLETED",
            duration_seconds=round(duration_seconds, 2),
            destination_uri=dest_path,
            model_used=extraction_result.final_model,
            attempts_count=len(attempts),
        )

        return f"COMPLETED: {doc_hash} -> {dest_path}"

    except ProcessingError as e:
        # Expected failure - quarantine the document
        logger.error(
            "processing_failed",
            doc_hash=doc_hash,
            error=str(e),
            attempts_count=len(attempts),
        )

        _quarantine_document(
            doc_hash=doc_hash,
            gcs_uri=gcs_uri,
            attempts=attempts,
            errors=errors,
            storage_client=storage_client,
            db_client=db_client,
        )

        return f"FAILED: {doc_hash} - {e}"

    except TimeoutError as e:
        # Timeout - quarantine for manual review
        logger.error(
            "processing_timeout",
            doc_hash=doc_hash,
            error=str(e),
        )
        errors.append(str(e))

        _quarantine_document(
            doc_hash=doc_hash,
            gcs_uri=gcs_uri,
            attempts=attempts,
            errors=errors,
            storage_client=storage_client,
            db_client=db_client,
        )

        return f"TIMEOUT: {doc_hash}"

    except Exception as e:
        # Unexpected error - quarantine for investigation
        logger.exception(
            "processing_unexpected_error",
            doc_hash=doc_hash,
            error=str(e),
            error_type=type(e).__name__,
        )
        errors.append(f"Unexpected error: {type(e).__name__}: {e}")

        _quarantine_document(
            doc_hash=doc_hash,
            gcs_uri=gcs_uri,
            attempts=attempts,
            errors=errors,
            storage_client=storage_client,
            db_client=db_client,
        )

        return f"ERROR: {doc_hash} - {type(e).__name__}"


def _check_timeout(start_time: float, phase: str) -> None:
    """
    Check if we're approaching the function timeout.

    Args:
        start_time: Processing start time
        phase: Current processing phase name

    Raises:
        TimeoutError: If approaching timeout
    """
    elapsed = time.time() - start_time
    remaining = FUNCTION_TIMEOUT_SECONDS - elapsed

    if remaining < SAFETY_MARGIN_SECONDS:
        raise TimeoutError(
            f"Approaching timeout at phase '{phase}'. "
            f"Elapsed: {elapsed:.1f}s, Remaining: {remaining:.1f}s"
        )


def _quarantine_document(
    doc_hash: str,
    gcs_uri: str,
    attempts: list[dict[str, Any]],
    errors: list[str],
    storage_client: storage.Client,
    db_client: DatabaseClient,
) -> None:
    """
    Move failed document to quarantine with report.

    Args:
        doc_hash: Document hash
        gcs_uri: Original GCS URI
        attempts: List of extraction attempts
        errors: List of error messages
        storage_client: GCS client
        db_client: Database client
    """
    logger.info(
        "quarantining_document",
        doc_hash=doc_hash,
        errors_count=len(errors),
    )

    try:
        # Parse original filename
        _, blob_name = parse_gcs_path(gcs_uri)
        filename = blob_name.split("/")[-1]

        # Generate quarantine paths
        quarantine_folder = f"gs://{QUARANTINE_BUCKET}/quarantine/{doc_hash}"
        original_copy_path = f"{quarantine_folder}/original_{filename}"
        report_path = f"{quarantine_folder}/FAILED_REPORT.md"
        data_path = f"{quarantine_folder}/extracted_data.json"

        # Copy original file to quarantine
        try:
            from src.core.storage import copy_blob

            copy_blob(storage_client, gcs_uri, original_copy_path)
        except Exception as e:
            logger.error(
                "quarantine_copy_failed",
                doc_hash=doc_hash,
                error=str(e),
            )

        # Write extracted data
        import json

        last_attempt_data = attempts[-1] if attempts else {}
        data_content = json.dumps(last_attempt_data, indent=2, ensure_ascii=False, default=str)
        upload_string(storage_client, data_path, data_content, "application/json")

        # Write failed report
        report_content = generate_failed_report(
            doc_hash=doc_hash,
            source_path=gcs_uri,
            attempts=attempts,
            errors=errors,
        )
        upload_string(storage_client, report_path, report_content, "text/markdown")

        # Update database status
        db_client.update_status(
            doc_id=doc_hash,
            status=DocumentStatus.QUARANTINED,
            error_message="; ".join(errors[:3]),  # First 3 errors
        )

        # Log audit event
        db_client.log_audit_event(
            doc_id=doc_hash,
            event=AuditEventType.QUARANTINED,
            details={
                "quarantine_path": quarantine_folder,
                "errors": errors,
                "attempts_count": len(attempts),
            },
        )

        logger.info(
            "document_quarantined",
            doc_hash=doc_hash,
            quarantine_path=quarantine_folder,
        )

    except Exception as e:
        logger.error(
            "quarantine_failed",
            doc_hash=doc_hash,
            error=str(e),
        )
        # Try to at least update the database (best-effort, ignore failures)
        with contextlib.suppress(Exception):
            db_client.update_status(
                doc_id=doc_hash,
                status=DocumentStatus.FAILED,
                error_message=f"Quarantine failed: {e}. Original errors: {'; '.join(errors[:2])}",
            )


# ============================================================
# Health Check Function
# ============================================================


@functions_framework.http
def health_check(request: Any) -> tuple[dict[str, Any], int]:
    """
    Health check endpoint for monitoring.

    Returns system health status including:
    - Service availability
    - Firestore connectivity
    - Storage connectivity

    Args:
        request: Flask request object

    Returns:
        Tuple of (response dict, HTTP status code)
    """
    health_status: dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "environment": os.environ.get("ENVIRONMENT", "unknown"),
        "checks": {},
    }
    all_healthy = True

    # Check Firestore
    try:
        firestore_client = firestore.Client()
        # Simple read operation
        firestore_client.collection("_health_check").limit(1).get()
        health_status["checks"]["firestore"] = "ok"
    except Exception as e:
        health_status["checks"]["firestore"] = f"error: {e}"
        all_healthy = False

    # Check Storage
    try:
        storage_client = storage.Client()
        list(storage_client.list_buckets(max_results=1))
        health_status["checks"]["storage"] = "ok"
    except Exception as e:
        health_status["checks"]["storage"] = f"error: {e}"
        all_healthy = False

    if not all_healthy:
        health_status["status"] = "degraded"
        logger.warning("health_check_degraded", checks=health_status["checks"])
        return health_status, 503

    logger.info("health_check_ok")
    return health_status, 200


# ============================================================
# Dead Letter Handler Function
# ============================================================


@functions_framework.cloud_event
def handle_dead_letter(event: CloudEvent) -> str:
    """
    Handle messages from dead letter queue.

    Sends Slack notification for failed documents that
    require human attention.

    Args:
        event: CloudEvent from Pub/Sub dead letter topic

    Returns:
        Status message string
    """
    import base64
    import json

    import requests

    logger.info("dead_letter_received", event_type=event["type"])

    # Decode Pub/Sub message
    try:
        message_data = event.data.get("message", {}).get("data", "")
        decoded = base64.b64decode(message_data).decode("utf-8")
        payload = json.loads(decoded)
    except Exception as e:
        logger.error("dead_letter_decode_failed", error=str(e))
        payload = {"raw_event": str(event.data)}

    # Prepare Slack notification
    slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")

    if not slack_webhook_url:
        logger.warning("slack_webhook_not_configured")
        return "SKIPPED: Slack webhook not configured"

    environment = os.environ.get("ENVIRONMENT", "unknown")
    doc_hash = payload.get("doc_hash", "unknown")
    error_message = payload.get("error", "Unknown error")

    slack_message = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 OCR処理失敗 ({environment})",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Document ID:*\n`{doc_hash}`"},
                    {"type": "mrkdwn", "text": f"*Environment:*\n{environment}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error:*\n```{error_message[:500]}```",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"📋 Review UI で確認してください",
                    },
                ],
            },
        ],
    }

    try:
        response = requests.post(  # noqa: S113
            slack_webhook_url,
            json=slack_message,
            timeout=10,
        )
        response.raise_for_status()
        logger.info("slack_notification_sent", doc_hash=doc_hash)
        return "NOTIFIED: Slack message sent"
    except Exception as e:
        logger.error("slack_notification_failed", error=str(e))
        return f"FAILED: Slack notification error: {e}"


# For local testing
if __name__ == "__main__":
    # Test with a mock event

    test_event = CloudEvent(
        attributes={
            "type": "google.cloud.storage.object.v1.finalized",
            "source": "//storage.googleapis.com/projects/_/buckets/test-bucket",
        },
        data={
            "bucket": "test-bucket",
            "name": "input/test-document.pdf",
        },
    )

    print("Testing process_document with mock event...")
    result = process_document(test_event)
    print(f"Result: {result}")
