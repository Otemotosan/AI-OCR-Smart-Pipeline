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
v2026.1 (Force Rebuild)
"""

from __future__ import annotations

import base64
import contextlib
import os
import time
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Any

import functions_framework
import structlog
from cloudevents.http import CloudEvent
from google.cloud import firestore, storage

from src.core.bigquery_client import BigQueryClient, BigQueryConfig
from src.core.budget import BudgetManager
from src.core.database import AuditEventType, DatabaseClient, DocumentStatus
from src.core.docai import DocumentAIClient
from src.core.extraction import GeminiInput, extract_with_retry, should_attach_image
from src.core.gemini import GeminiClient
from src.core.linters.gate import GateLinter
from src.core.linters.quality import QualityLinter

# Import core modules
from src.core.lock import DistributedLock, LockNotAcquiredError
from src.core.saga import generate_failed_report, persist_document
from src.core.schema_detector import select_schema_priority
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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Multi-schema extraction configuration
CLASSIFICATION_CONFIDENCE_THRESHOLD = float(
    os.environ.get("CLASSIFICATION_CONFIDENCE_THRESHOLD", "0.85")
)
MAX_SCHEMA_ATTEMPTS = int(os.environ.get("MAX_SCHEMA_ATTEMPTS", "2"))

# Timeout configuration (Cloud Functions 2nd Gen max is 60 minutes)
FUNCTION_TIMEOUT_SECONDS = int(os.environ.get("FUNCTION_TIMEOUT", "540"))
SAFETY_MARGIN_SECONDS = 30  # Stop processing before hard timeout


def _convert_dates_to_strings(data: Any) -> Any:
    """
    Recursively convert datetime.date objects to ISO format strings.

    Firestore cannot directly store datetime.date objects, only datetime.datetime.
    This function converts all date objects to strings for compatibility.

    Args:
        data: Data structure (dict, list, or primitive) to convert

    Returns:
        Data with date objects converted to ISO format strings
    """
    if isinstance(data, dict):
        return {key: _convert_dates_to_strings(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [_convert_dates_to_strings(item) for item in data]
    elif isinstance(data, date) and not isinstance(data, datetime):
        # date but not datetime - convert to ISO string
        return data.isoformat()
    elif isinstance(data, datetime):
        # datetime is supported by Firestore, keep as-is
        return data
    else:
        return data


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
    lock_manager = DistributedLock(firestore_client)
    try:
        with lock_manager.acquire(doc_hash):
            logger.info(
                "lock_acquired",
                doc_hash=doc_hash,
                ttl_seconds=lock_manager.ttl_seconds,
            )

            # Process the document
            result = _process_document_internal(
                doc_hash=doc_hash,
                gcs_uri=gcs_uri,
                storage_client=storage_client,
                firestore_client=firestore_client,
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
    firestore_client: firestore.Client,
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
        firestore_client: Firestore client
        storage_ops: Storage operations client
        db_client: Database client
        bq_client: BigQuery client
        start_time: Processing start time

    Returns:
        Status message string
    """
    attempts: list[dict[str, Any]] = []
    errors: list[str] = []
    docai_markdown: str | None = None

    try:
        # Check timeout
        _check_timeout(start_time, "start")

        # Step 1: Create database record
        logger.info("creating_db_record", doc_hash=doc_hash)
        db_client.create_document(doc_hash, gcs_uri, DocumentStatus.PROCESSING)

        # Step 2: Process with Document AI
        _check_timeout(start_time, "docai")
        logger.info("processing_with_docai", doc_hash=doc_hash)

        # Parse processor path: projects/{project}/locations/{location}/processors/{id}
        processor_parts = DOCUMENT_AI_PROCESSOR.split("/")
        if len(processor_parts) >= 6:
            docai_project = processor_parts[1]
            docai_location = processor_parts[3]
            docai_processor_id = processor_parts[5]
        else:
            # Fallback to PROJECT_ID and assume processor_id only
            docai_project = PROJECT_ID
            docai_location = "us"
            docai_processor_id = DOCUMENT_AI_PROCESSOR

        docai_client = DocumentAIClient(
            project_id=docai_project,
            location=docai_location,
            processor_id=docai_processor_id,
        )
        docai_result = docai_client.process_document(gcs_uri)
        docai_markdown = docai_result.markdown

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

        # Check if image attachment is needed
        include_image, image_reason = should_attach_image(
            confidence=docai_result.confidence,
            gate_failed=False,  # First attempt
            attempt=0,
            doc_type=docai_result.detected_type,
        )

        # Prepare image if needed
        image_base64 = None
        if include_image:
            bucket_name, blob_name = parse_gcs_path(gcs_uri)
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            file_content = blob.download_as_bytes()

            # Convert PDF to image if needed
            if gcs_uri.lower().endswith(".pdf"):
                image_bytes = _convert_pdf_to_image(file_content)
                if image_bytes:
                    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
                    logger.info("pdf_converted_to_image", doc_hash=doc_hash, size=len(image_bytes))
                else:
                    logger.warning("pdf_conversion_failed", doc_hash=doc_hash)
                    include_image = False
                    image_reason = "pdf_conversion_failed"
            else:
                # For image files, use directly
                image_base64 = base64.b64encode(file_content).decode("utf-8")

        # Create GeminiInput
        gemini_input = GeminiInput(
            markdown=docai_result.markdown,
            image_base64=image_base64,
            include_image=include_image,
            reason=image_reason,
        )

        # Initialize clients for extraction
        gemini_client = GeminiClient(api_key=GEMINI_API_KEY)
        budget_manager = BudgetManager(firestore_client=firestore_client)
        gate_linter = GateLinter()

        # Multi-schema extraction with intelligent schema selection
        schema_priority = select_schema_priority(
            markdown=docai_result.markdown,
            gcs_path=gcs_uri,
            confidence_threshold=CLASSIFICATION_CONFIDENCE_THRESHOLD,
        )

        logger.info(
            "schema_priority_determined",
            doc_hash=doc_hash,
            schemas=[s.__name__ for s in schema_priority[:MAX_SCHEMA_ATTEMPTS]],
        )

        extraction_result = None
        extraction_success = False

        # Try schemas in priority order (up to MAX_SCHEMA_ATTEMPTS)
        for schema_idx, schema_class in enumerate(schema_priority[:MAX_SCHEMA_ATTEMPTS]):
            logger.info(
                "trying_schema",
                doc_hash=doc_hash,
                schema=schema_class.__name__,
                attempt=schema_idx + 1,
            )

            extraction_result = extract_with_retry(
                gemini_input=gemini_input,
                schema_class=schema_class,
                gemini_client=gemini_client,
                budget_manager=budget_manager,
                gate_linter=gate_linter,
            )

            if extraction_result.status == "SUCCESS":
                extraction_success = True
                logger.info(
                    "schema_extraction_success",
                    doc_hash=doc_hash,
                    schema=schema_class.__name__,
                )
                break
            else:
                logger.warning(
                    "schema_extraction_failed",
                    doc_hash=doc_hash,
                    schema=schema_class.__name__,
                    reason=extraction_result.reason,
                )

        # Record all attempts from last extraction
        attempts = extraction_result.attempts if extraction_result else []

        # Fallback to GenericDocumentV1 if all schemas failed
        if not extraction_success:
            logger.warning(
                "all_schemas_failed_using_generic",
                doc_hash=doc_hash,
                tried_schemas=[s.__name__ for s in schema_priority[:MAX_SCHEMA_ATTEMPTS]],
            )

            # Create generic document with doc_hash as ID
            extracted_data = {
                "schema_version": "v1",
                "document_type": "generic",
                "document_id": doc_hash,
                "title": None,
                "extracted_text": docai_result.markdown[:500] if docai_result.markdown else "",
                "detected_fields": {},
                "confidence_score": docai_result.confidence,
            }
            document_type = "generic"
            schema_version = "generic/v1"
        else:
            extracted_data = (
                extraction_result.schema.model_dump() if extraction_result.schema else {}
            )
            # Convert date objects to strings for Firestore compatibility
            extracted_data = _convert_dates_to_strings(extracted_data)

            # Get document_type and schema_version from the schema class field defaults,
            # not from extracted_data (Gemini may return wrong values like Japanese text)
            schema_class = type(extraction_result.schema) if extraction_result.schema else None
            if schema_class and hasattr(schema_class, "model_fields"):
                # Get document_type from schema default
                doc_type_field = schema_class.model_fields.get("document_type")
                document_type = (
                    doc_type_field.default
                    if doc_type_field and doc_type_field.default
                    else "unknown"
                )

                # Get schema_version from schema default
                version_field = schema_class.model_fields.get("schema_version")
                version = version_field.default if version_field and version_field.default else "v1"

                # Override extracted_data with correct values to ensure consistency
                extracted_data["document_type"] = document_type
                extracted_data["schema_version"] = version
            else:
                document_type = extracted_data.get("document_type", "unknown")
                version = "v1"

            # Build schema_version string
            if version.startswith("v"):
                schema_version = f"{document_type}/{version}"
            else:
                schema_version = f"{document_type}/v{version}"

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
        # Convert ExtractionAttempt dataclass objects to dictionaries for Firestore
        attempts_dicts = [asdict(attempt) for attempt in attempts]
        # Convert any date/datetime objects in attempts to strings
        attempts_dicts = [_convert_dates_to_strings(d) for d in attempts_dicts]
        db_client.save_extraction(
            doc_id=doc_hash,
            extracted_data=extracted_data,
            attempts=attempts_dicts,
            schema_version=schema_version,
            quality_warnings=quality_warnings,
            docai_markdown=docai_result.markdown,
        )

        # Step 7: Generate destination path and persist with Saga
        _check_timeout(start_time, "persistence")
        logger.info("persisting_document", doc_hash=doc_hash)

        # Extract original filename from GCS URI for unknown documents
        original_filename = gcs_uri.split("/")[-1] if "/" in gcs_uri else gcs_uri

        dest_path = generate_destination_path(
            schema_data=extracted_data,
            timestamp=datetime.now(UTC),
            output_bucket=OUTPUT_BUCKET,
            original_filename=original_filename,
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

        # Step 7.5: Save Document AI markdown to GCS (for debugging and re-extraction)
        markdown_path = dest_path.rsplit(".", 1)[0] + "_docai.md"
        try:
            upload_string(
                storage_client,
                markdown_path,
                docai_result.markdown,
                "text/markdown; charset=utf-8",
            )
            logger.info(
                "markdown_saved_to_gcs",
                doc_hash=doc_hash,
                markdown_path=markdown_path,
                markdown_size=len(docai_result.markdown),
            )
        except Exception as e:
            # Non-critical: log warning but don't fail processing
            logger.warning(
                "markdown_save_failed",
                doc_hash=doc_hash,
                error=str(e),
            )

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
            docai_markdown=docai_markdown,
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
            docai_markdown=docai_markdown,
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
            docai_markdown=docai_markdown,
        )

        return f"ERROR: {doc_hash} - {type(e).__name__}"


def _convert_pdf_to_image(pdf_bytes: bytes, dpi: int = 150) -> bytes | None:
    """
    Convert first page of PDF to PNG image.

    Uses PyMuPDF (fitz) for conversion without system dependencies.

    Args:
        pdf_bytes: PDF file content as bytes
        dpi: Resolution for rendering (default: 150 for balance of quality/size)

    Returns:
        PNG image bytes, or None if conversion fails
    """
    try:
        import fitz  # PyMuPDF

        # Open PDF from bytes
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        if len(doc) == 0:
            logger.warning("pdf_empty", page_count=0)
            return None

        # Get first page
        page = doc[0]

        # Calculate zoom factor for target DPI (default PDF is 72 DPI)
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)

        # Render page to pixmap (image)
        pixmap = page.get_pixmap(matrix=matrix)

        # Convert to PNG bytes
        png_bytes = pixmap.tobytes("png")

        doc.close()

        return png_bytes

    except Exception as e:
        logger.error("pdf_to_image_error", error=str(e), error_type=type(e).__name__)
        return None


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
    docai_markdown: str | None = None,
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
        docai_markdown: Optional Document AI markdown content
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
        docai_path = f"{quarantine_folder}/{doc_hash}_docai.md"

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
        upload_string(storage_client, data_path, data_content, "application/json; charset=utf-8")

        # Write failed report
        report_content = generate_failed_report(
            doc_hash=doc_hash,
            source_path=gcs_uri,
            attempts=attempts,
            errors=errors,
        )
        upload_string(storage_client, report_path, report_content, "text/markdown; charset=utf-8")

        # Write DocAI markdown if available
        if docai_markdown:
            upload_string(
                storage_client,
                docai_path,
                docai_markdown,
                "text/markdown; charset=utf-8",
            )

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
                        "text": "📋 Review UI で確認してください",
                    },
                ],
            },
        ],
    }

    try:
        response = requests.post(
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
