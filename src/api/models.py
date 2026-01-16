"""API request/response models for the Review UI."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# =============================================================================
# Enums
# =============================================================================


class DocumentStatus(str, Enum):
    """Document processing status."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"


class SortOrder(str, Enum):
    """Sort order options."""

    ASC = "asc"
    DESC = "desc"


# =============================================================================
# Request Models
# =============================================================================


class DocumentUpdateRequest(BaseModel):
    """Request to update document extraction data."""

    corrected_data: dict[str, Any] = Field(..., description="Corrected extraction data")
    expected_updated_at: str = Field(..., description="Expected updated_at for optimistic locking")


class DocumentApproveRequest(BaseModel):
    """Request to approve a document."""

    pass  # No additional fields needed


class DocumentRejectRequest(BaseModel):
    """Request to reject a document."""

    reason: str = Field(..., min_length=1, max_length=500, description="Rejection reason")


class DraftSaveRequest(BaseModel):
    """Request to save a draft."""

    data: dict[str, Any] = Field(..., description="Draft data")
    saved_at: str = Field(..., description="Client-side save timestamp")


# =============================================================================
# Response Models
# =============================================================================


class ProUsageResponse(BaseModel):
    """Pro API usage statistics."""

    daily_count: int = Field(..., description="Daily Pro API calls")
    daily_limit: int = Field(..., description="Daily limit")
    monthly_count: int = Field(..., description="Monthly Pro API calls")
    monthly_limit: int = Field(..., description="Monthly limit")


class ActivityItem(BaseModel):
    """Recent activity item."""

    timestamp: datetime
    event: str
    document_id: str
    status: str
    message: str


class DashboardResponse(BaseModel):
    """Dashboard summary data."""

    today_count: int = Field(..., description="Documents processed today")
    success_rate_7d: float = Field(..., description="7-day success rate (0-100)")
    pending_review: int = Field(..., description="Documents pending review")
    pro_usage: ProUsageResponse = Field(..., description="Pro API usage")
    recent_activity: list[ActivityItem] = Field(default_factory=list)


class DocumentListItem(BaseModel):
    """Document item in list view."""

    document_id: str
    status: DocumentStatus
    document_type: str | None = None
    source_uri: str
    error_message: str | None = None
    attempts: int = 0
    confidence: float | None = None
    created_at: datetime
    updated_at: datetime


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""

    items: list[DocumentListItem]
    total: int
    page: int
    pages: int
    limit: int


class ExtractionAttempt(BaseModel):
    """Details of a single extraction attempt."""

    attempt_number: int
    model: str
    timestamp: datetime
    success: bool
    error_type: str | None = None
    error_message: str | None = None
    tokens_used: int | None = None


class MigrationMetadata(BaseModel):
    """Schema migration metadata."""

    from_version: str | None = None
    to_version: str | None = None
    migrated_at: datetime | None = None
    fields_defaulted: list[str] = Field(default_factory=list)


class DocumentDetailResponse(BaseModel):
    """Full document details for review."""

    document_id: str
    status: DocumentStatus
    document_type: str | None = None
    source_uri: str
    destination_uri: str | None = None
    extracted_data: dict[str, Any] | None = None
    corrected_data: dict[str, Any] | None = None
    validation_errors: list[str] = Field(default_factory=list)
    quality_warnings: list[str] = Field(default_factory=list)
    migration_metadata: MigrationMetadata | None = None
    attempts: list[ExtractionAttempt] = Field(default_factory=list)
    pdf_url: str | None = None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None = None
    schema_version: str | None = None
    error_message: str | None = None


class UpdateResponse(BaseModel):
    """Response after updating a document."""

    status: str = "saved"
    updated_at: str


class ApproveResponse(BaseModel):
    """Response after approving a document."""

    status: str = "approved"
    message: str = "Document queued for processing"


class RejectResponse(BaseModel):
    """Response after rejecting a document."""

    status: str = "rejected"


class DraftResponse(BaseModel):
    """Draft data response."""

    doc_hash: str
    data: dict[str, Any]
    saved_at: str
    user_id: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str
    timestamp: datetime


class ErrorResponse(BaseModel):
    """Error response."""

    detail: str
    error_code: str | None = None
