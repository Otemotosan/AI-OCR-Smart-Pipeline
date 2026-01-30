"""Document API routes."""

from __future__ import annotations

from datetime import datetime
from math import ceil
from typing import Literal
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, HTTPException, Query
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from api.deps import (
    CurrentUser,
    FirestoreClient,
    StorageClient,
    generate_signed_url,
)
from api.models import (
    ApproveResponse,
    DocumentDetailResponse,
    DocumentListItem,
    DocumentRejectRequest,
    DocumentStatus,
    DocumentUpdateRequest,
    ExtractionAttempt,
    MigrationMetadata,
    PaginatedResponse,
    RejectResponse,
    UpdateResponse,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/documents")

JST = ZoneInfo("Asia/Tokyo")


# =============================================================================
# Document Listing
# =============================================================================


@router.get("", response_model=PaginatedResponse)
async def list_documents(
    db: FirestoreClient,
    user: CurrentUser,
    status: DocumentStatus | None = Query(None, description="Filter by status"),
    document_type: str | None = Query(None, description="Filter by document type"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: Literal["asc", "desc"] = Query("desc", description="Sort order"),
) -> PaginatedResponse:
    """
    List documents with pagination and filtering.

    Supports filtering by status, document_type.
    Supports sorting by created_at, updated_at, confidence.
    """
    logger.info(
        "Listing documents",
        user=user.email,
        status=status,
        page=page,
        limit=limit,
    )

    # Build query
    collection = db.collection("processed_documents")
    query = collection

    # Apply filters
    if status:
        query = query.where(filter=FieldFilter("status", "==", status.value))

    if document_type:
        query = query.where(filter=FieldFilter("document_type", "==", document_type))

    # Get total count (before pagination)
    count_result = query.count().get()
    total = count_result[0][0].value if count_result else 0

    # Apply sorting
    direction = firestore.Query.DESCENDING if sort_order == "desc" else firestore.Query.ASCENDING
    query = query.order_by(sort_by, direction=direction)

    # Apply pagination
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    # Execute query
    docs = query.stream()

    items = []
    for doc in docs:
        data = doc.to_dict()
        items.append(
            DocumentListItem(
                document_id=doc.id,
                status=DocumentStatus(data.get("status", "PENDING")),
                document_type=data.get("document_type"),
                source_uri=data.get("source_uri", ""),
                error_message=data.get("error_message"),
                attempts=len(data.get("attempts", [])),
                confidence=data.get("confidence"),
                created_at=data.get("created_at", datetime.now(JST)),
                updated_at=data.get("updated_at", datetime.now(JST)),
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        pages=ceil(total / limit) if total > 0 else 1,
        limit=limit,
    )


@router.get("/failed", response_model=PaginatedResponse)
async def list_failed_documents(
    db: FirestoreClient,
    user: CurrentUser,
    document_type: str | None = Query(None, description="Filter by document type"),
    error_type: str | None = Query(None, description="Filter by error type"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
) -> PaginatedResponse:
    """
    List documents requiring human review (FAILED or QUARANTINED).
    """
    logger.info("Listing failed documents", user=user.email, page=page)

    # Build query for failed documents
    collection = db.collection("processed_documents")
    query = collection.where(filter=FieldFilter("status", "in", ["FAILED", "QUARANTINED"]))

    if document_type:
        query = query.where(filter=FieldFilter("document_type", "==", document_type))

    # Get total count
    count_result = query.count().get()
    total = count_result[0][0].value if count_result else 0

    # Apply sorting
    direction = firestore.Query.DESCENDING if sort_order == "desc" else firestore.Query.ASCENDING
    query = query.order_by(sort_by, direction=direction)

    # Apply pagination
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    # Execute query
    docs = query.stream()

    items = []
    for doc in docs:
        data = doc.to_dict()
        items.append(
            DocumentListItem(
                document_id=doc.id,
                status=DocumentStatus(data.get("status", "FAILED")),
                document_type=data.get("document_type"),
                source_uri=data.get("source_uri", ""),
                error_message=data.get("error_message"),
                attempts=len(data.get("attempts", [])),
                confidence=data.get("confidence"),
                created_at=data.get("created_at", datetime.now(JST)),
                updated_at=data.get("updated_at", datetime.now(JST)),
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        pages=ceil(total / limit) if total > 0 else 1,
        limit=limit,
    )


# =============================================================================
# Document Details
# =============================================================================


@router.get("/{doc_hash}", response_model=DocumentDetailResponse)
async def get_document(
    doc_hash: str,
    db: FirestoreClient,
    storage: StorageClient,
    user: CurrentUser,
) -> DocumentDetailResponse:
    """
    Get full document details for review.

    Includes extracted data, validation errors, quality warnings,
    migration metadata, and a signed URL for PDF viewing.
    """
    logger.info("Fetching document", doc_hash=doc_hash, user=user.email)

    # Fetch document
    doc_ref = db.collection("processed_documents").document(doc_hash)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Document not found")

    data = doc.to_dict()

    # Generate signed URL for PDF
    pdf_url = None
    source_uri = data.get("quarantine_path") or data.get("source_uri")
    logger.info(
        "Attempting to generate signed URL",
        source_uri=source_uri,
        has_quarantine_path=bool(data.get("quarantine_path")),
    )
    if source_uri:
        try:
            pdf_url = generate_signed_url(storage, source_uri, expiry_seconds=3600)
            url_prefix = pdf_url[:50] if pdf_url else None
            logger.info("Generated signed URL successfully", pdf_url_prefix=url_prefix)
        except Exception as e:
            logger.warning(
                "Failed to generate signed URL",
                error=str(e),
                error_type=type(e).__name__,
                source_uri=source_uri,
            )
    else:
        logger.warning("No source_uri found for document", doc_hash=doc_hash)


    # Parse attempts
    attempts = []
    for i, attempt in enumerate(data.get("attempts", [])):
        attempts.append(
            ExtractionAttempt(
                attempt_number=i + 1,
                model=attempt.get("model", "unknown"),
                timestamp=attempt.get("timestamp", datetime.now(JST)),
                success=attempt.get("success", False),
                error_type=attempt.get("error_type"),
                error_message=attempt.get("error_message"),
                tokens_used=attempt.get("tokens_used"),
            )
        )

    # Parse migration metadata
    migration_metadata = None
    raw_migration = data.get("migration_metadata") or data.get("_migration_metadata")
    if raw_migration:
        migration_metadata = MigrationMetadata(
            from_version=raw_migration.get("from_version"),
            to_version=raw_migration.get("to_version"),
            migrated_at=raw_migration.get("migrated_at"),
            fields_defaulted=raw_migration.get("fields_defaulted", []),
        )

    return DocumentDetailResponse(
        document_id=doc_hash,
        status=DocumentStatus(data.get("status", "PENDING")),
        document_type=data.get("document_type"),
        source_uri=data.get("source_uri", ""),
        destination_uri=data.get("destination_uri"),
        extracted_data=data.get("extracted_data"),
        corrected_data=data.get("corrected_data"),
        validation_errors=data.get("validation_errors", []),
        quality_warnings=data.get("quality_warnings", []),
        migration_metadata=migration_metadata,
        attempts=attempts,
        pdf_url=pdf_url,
        created_at=data.get("created_at", datetime.now(JST)),
        updated_at=data.get("updated_at", datetime.now(JST)),
        processed_at=data.get("processed_at"),
        schema_version=data.get("schema_version"),
        error_message=data.get("error_message"),
    )


# =============================================================================
# Document Update (with Optimistic Locking)
# =============================================================================


@router.put("/{doc_hash}", response_model=UpdateResponse)
async def update_document(
    doc_hash: str,
    body: DocumentUpdateRequest,
    db: FirestoreClient,
    user: CurrentUser,
) -> UpdateResponse:
    """
    Update document with corrected data.

    Uses optimistic locking via expected_updated_at to prevent
    concurrent edit conflicts.
    """
    logger.info("Updating document", doc_hash=doc_hash, user=user.email)

    doc_ref = db.collection("processed_documents").document(doc_hash)

    @firestore.transactional
    def _update_with_lock(transaction: firestore.Transaction) -> str:
        doc = doc_ref.get(transaction=transaction)

        if not doc.exists:
            raise HTTPException(status_code=404, detail="Document not found")

        current_data = doc.to_dict()
        current_updated_at = current_data.get("updated_at")

        # Convert to comparable format
        if hasattr(current_updated_at, "isoformat"):
            current_updated_at_str = current_updated_at.isoformat()
        else:
            current_updated_at_str = str(current_updated_at)

        # Conflict detection
        if current_updated_at_str != body.expected_updated_at:
            last_modified_by = current_data.get("last_modified_by", "another user")
            raise HTTPException(
                status_code=409,
                detail=f"Document was modified by {last_modified_by}. "
                f"Please reload the page and try again.",
            )

        # Perform update
        transaction.update(
            doc_ref,
            {
                "corrected_data": body.corrected_data,
                "last_modified_by": user.email,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
        )

        return "updated"

    # Execute transactional update
    transaction = db.transaction()
    _update_with_lock(transaction)

    # Fetch updated document to get new timestamp
    updated_doc = doc_ref.get().to_dict()
    new_updated_at = updated_doc.get("updated_at")
    if hasattr(new_updated_at, "isoformat"):
        new_updated_at = new_updated_at.isoformat()

    # Log audit event
    _log_audit(
        db,
        doc_hash=doc_hash,
        event="CORRECTED",
        user_id=user.email,
        details={"fields_changed": list(body.corrected_data.keys())},
    )

    return UpdateResponse(status="saved", updated_at=str(new_updated_at))


# =============================================================================
# Document Approval
# =============================================================================


@router.post("/{doc_hash}/approve", response_model=ApproveResponse)
async def approve_document(
    doc_hash: str,
    db: FirestoreClient,
    user: CurrentUser,
) -> ApproveResponse:
    """
    Approve document and trigger processing.

    Validates with Gate Linter before approval.
    """
    logger.info("Approving document", doc_hash=doc_hash, user=user.email)

    doc_ref = db.collection("processed_documents").document(doc_hash)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Document not found")

    data = doc.to_dict()
    status = data.get("status")

    if status not in ["FAILED", "QUARANTINED"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve document with status: {status}",
        )

    # Get data to validate (prefer corrected_data over extracted_data)
    validation_data = data.get("corrected_data") or data.get("extracted_data")

    if not validation_data:
        raise HTTPException(
            status_code=400,
            detail="No data to validate. Please correct the document first.",
        )

    # Validate with Gate Linter
    from core.linters.gate import GateLinter

    gate_linter = GateLinter()
    gate_result = gate_linter.validate(validation_data)

    if not gate_result.passed:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Gate validation failed",
                "errors": gate_result.errors,
            },
        )

    # Update status to APPROVED
    doc_ref.update(
        {
            "status": "APPROVED",
            "approved_by": user.email,
            "approved_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
    )

    # Log audit event
    _log_audit(
        db,
        doc_hash=doc_hash,
        event="APPROVED",
        user_id=user.email,
        details={"quality_warnings_count": len(data.get("quality_warnings", []))},
    )

    # TODO: Trigger Saga resume for file processing
    # await trigger_saga_resume(doc_hash)

    return ApproveResponse(
        status="approved",
        message="Document approved and queued for processing",
    )


# =============================================================================
# Document Rejection
# =============================================================================


@router.post("/{doc_hash}/reject", response_model=RejectResponse)
async def reject_document(
    doc_hash: str,
    body: DocumentRejectRequest,
    db: FirestoreClient,
    user: CurrentUser,
) -> RejectResponse:
    """
    Permanently reject a document.
    """
    logger.info(
        "Rejecting document",
        doc_hash=doc_hash,
        user=user.email,
        reason=body.reason,
    )

    doc_ref = db.collection("processed_documents").document(doc_hash)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Document not found")

    # Update status to REJECTED
    doc_ref.update(
        {
            "status": "REJECTED",
            "rejection_reason": body.reason,
            "rejected_by": user.email,
            "rejected_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
    )

    # Log audit event
    _log_audit(
        db,
        doc_hash=doc_hash,
        event="REJECTED",
        user_id=user.email,
        details={"reason": body.reason},
    )

    return RejectResponse(status="rejected")


# =============================================================================
# Helpers
# =============================================================================


def _log_audit(
    db: FirestoreClient,
    doc_hash: str,
    event: str,
    user_id: str,
    details: dict | None = None,
) -> None:
    """Log an audit event."""
    db.collection("audit_log").add(
        {
            "document_id": doc_hash,
            "event": event,
            "user_id": user_id,
            "details": details or {},
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
    )
