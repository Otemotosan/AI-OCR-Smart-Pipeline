"""Unit tests for the Review UI API."""

from __future__ import annotations

import sys
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

# Mock Google Cloud modules before importing API modules
sys.modules["google.cloud"] = Mock()
sys.modules["google.cloud.firestore"] = Mock()
sys.modules["google.cloud.firestore_v1"] = Mock()
sys.modules["google.cloud.firestore_v1.base_query"] = Mock()
sys.modules["google.cloud.storage"] = Mock()
sys.modules["google.cloud.bigquery"] = Mock()

# Now import API modules (must be after mocking)
from api.deps import Settings, User  # noqa: E402
from api.models import (  # noqa: E402
    ActivityItem,
    ApproveResponse,
    DashboardResponse,
    DocumentDetailResponse,
    DocumentListItem,
    DocumentRejectRequest,
    DocumentStatus,
    DocumentUpdateRequest,
    DraftResponse,
    DraftSaveRequest,
    ErrorResponse,
    ExtractionAttempt,
    HealthResponse,
    MigrationMetadata,
    PaginatedResponse,
    ProUsageResponse,
    RejectResponse,
    UpdateResponse,
)

JST = ZoneInfo("Asia/Tokyo")


# =============================================================================
# Model Tests
# =============================================================================


class TestModels:
    """Test API request/response models."""

    def test_document_status_enum(self) -> None:
        """Test DocumentStatus enum values."""
        assert DocumentStatus.PENDING == "PENDING"
        assert DocumentStatus.PROCESSING == "PROCESSING"
        assert DocumentStatus.COMPLETED == "COMPLETED"
        assert DocumentStatus.FAILED == "FAILED"
        assert DocumentStatus.QUARANTINED == "QUARANTINED"
        assert DocumentStatus.REJECTED == "REJECTED"
        assert DocumentStatus.APPROVED == "APPROVED"

    def test_document_update_request(self) -> None:
        """Test DocumentUpdateRequest model."""
        request = DocumentUpdateRequest(
            corrected_data={"management_id": "TEST-001"},
            expected_updated_at="2025-01-15T10:00:00+09:00",
        )
        assert request.corrected_data["management_id"] == "TEST-001"
        assert request.expected_updated_at == "2025-01-15T10:00:00+09:00"

    def test_document_reject_request_validation(self) -> None:
        """Test DocumentRejectRequest validation."""
        # Valid request
        request = DocumentRejectRequest(reason="Invalid document")
        assert request.reason == "Invalid document"

        # Empty reason should fail
        with pytest.raises(ValueError):  # Pydantic ValidationError
            DocumentRejectRequest(reason="")

    def test_draft_save_request(self) -> None:
        """Test DraftSaveRequest model."""
        request = DraftSaveRequest(
            data={"management_id": "DRAFT-001"},
            saved_at="2025-01-15T10:00:00Z",
        )
        assert request.data["management_id"] == "DRAFT-001"
        assert request.saved_at == "2025-01-15T10:00:00Z"

    def test_pro_usage_response(self) -> None:
        """Test ProUsageResponse model."""
        response = ProUsageResponse(
            daily_count=10,
            daily_limit=50,
            monthly_count=200,
            monthly_limit=1000,
        )
        assert response.daily_count == 10
        assert response.daily_limit == 50
        assert response.monthly_count == 200
        assert response.monthly_limit == 1000

    def test_activity_item(self) -> None:
        """Test ActivityItem model."""
        item = ActivityItem(
            timestamp=datetime.now(JST),
            event="EXTRACTED",
            document_id="abc123",
            status="COMPLETED",
            message="Document abc123 extracted successfully",
        )
        assert item.event == "EXTRACTED"
        assert item.document_id == "abc123"

    def test_dashboard_response(self) -> None:
        """Test DashboardResponse model."""
        response = DashboardResponse(
            today_count=47,
            success_rate_7d=94.2,
            pending_review=3,
            pro_usage=ProUsageResponse(
                daily_count=5,
                daily_limit=50,
                monthly_count=100,
                monthly_limit=1000,
            ),
            recent_activity=[],
        )
        assert response.today_count == 47
        assert response.success_rate_7d == 94.2
        assert response.pending_review == 3

    def test_document_list_item(self) -> None:
        """Test DocumentListItem model."""
        item = DocumentListItem(
            document_id="hash123",
            status=DocumentStatus.FAILED,
            document_type="delivery_note",
            source_uri="gs://bucket/file.pdf",
            error_message="Invalid management_id",
            attempts=3,
            confidence=0.75,
            created_at=datetime.now(JST),
            updated_at=datetime.now(JST),
        )
        assert item.document_id == "hash123"
        assert item.status == DocumentStatus.FAILED
        assert item.attempts == 3

    def test_paginated_response(self) -> None:
        """Test PaginatedResponse model."""
        response = PaginatedResponse(
            items=[],
            total=100,
            page=2,
            pages=5,
            limit=20,
        )
        assert response.total == 100
        assert response.page == 2
        assert response.pages == 5

    def test_extraction_attempt(self) -> None:
        """Test ExtractionAttempt model."""
        attempt = ExtractionAttempt(
            attempt_number=1,
            model="gemini-1.5-flash",
            timestamp=datetime.now(JST),
            success=False,
            error_type="semantic",
            error_message="Gate validation failed",
            tokens_used=1500,
        )
        assert attempt.attempt_number == 1
        assert attempt.model == "gemini-1.5-flash"
        assert not attempt.success

    def test_migration_metadata(self) -> None:
        """Test MigrationMetadata model."""
        metadata = MigrationMetadata(
            from_version="delivery_note_v1",
            to_version="delivery_note_v2",
            migrated_at=datetime.now(JST),
            fields_defaulted=["total_amount", "tax_amount"],
        )
        assert metadata.from_version == "delivery_note_v1"
        assert len(metadata.fields_defaulted) == 2

    def test_document_detail_response(self) -> None:
        """Test DocumentDetailResponse model."""
        response = DocumentDetailResponse(
            document_id="hash123",
            status=DocumentStatus.FAILED,
            document_type="delivery_note",
            source_uri="gs://bucket/file.pdf",
            destination_uri=None,
            extracted_data={"management_id": "TEST-001"},
            corrected_data=None,
            validation_errors=["Invalid management_id format"],
            quality_warnings=["Total amount is zero"],
            migration_metadata=None,
            attempts=[],
            pdf_url="https://storage.googleapis.com/...",
            created_at=datetime.now(JST),
            updated_at=datetime.now(JST),
            processed_at=None,
            schema_version="delivery_note_v2",
            error_message="Gate validation failed",
        )
        assert response.document_id == "hash123"
        assert response.status == DocumentStatus.FAILED
        assert len(response.validation_errors) == 1

    def test_update_response(self) -> None:
        """Test UpdateResponse model."""
        response = UpdateResponse(
            status="saved",
            updated_at="2025-01-15T10:00:00+09:00",
        )
        assert response.status == "saved"

    def test_approve_response(self) -> None:
        """Test ApproveResponse model."""
        response = ApproveResponse()
        assert response.status == "approved"
        assert "queued" in response.message

    def test_reject_response(self) -> None:
        """Test RejectResponse model."""
        response = RejectResponse()
        assert response.status == "rejected"

    def test_draft_response(self) -> None:
        """Test DraftResponse model."""
        response = DraftResponse(
            doc_hash="hash123",
            data={"management_id": "DRAFT-001"},
            saved_at="2025-01-15T10:00:00Z",
            user_id="user@example.com",
        )
        assert response.doc_hash == "hash123"
        assert response.user_id == "user@example.com"

    def test_health_response(self) -> None:
        """Test HealthResponse model."""
        response = HealthResponse(
            status="healthy",
            version="1.0.0",
            timestamp=datetime.now(JST),
        )
        assert response.status == "healthy"
        assert response.version == "1.0.0"

    def test_error_response(self) -> None:
        """Test ErrorResponse model."""
        response = ErrorResponse(
            detail="Document not found",
            error_code="NOT_FOUND",
        )
        assert response.detail == "Document not found"
        assert response.error_code == "NOT_FOUND"


# =============================================================================
# Settings Tests
# =============================================================================


class TestSettings:
    """Test API settings and configuration."""

    def test_settings_dataclass(self) -> None:
        """Test Settings dataclass."""
        settings = Settings(
            project_id="test-project",
            firestore_database="(default)",
            gcs_input_bucket="test-input",
            gcs_output_bucket="test-output",
            gcs_quarantine_bucket="test-quarantine",
            bigquery_dataset="test_dataset",
            cors_origins=["http://localhost:5173"],
            environment="development",
        )
        assert settings.project_id == "test-project"
        assert settings.environment == "development"


# =============================================================================
# User Tests
# =============================================================================


class TestUser:
    """Test User model."""

    def test_user_dataclass(self) -> None:
        """Test User dataclass."""
        user = User(
            email="test@example.com",
            user_id="user_123",
        )
        assert user.email == "test@example.com"
        assert user.user_id == "user_123"


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_paginated_response(self) -> None:
        """Test PaginatedResponse with no items."""
        response = PaginatedResponse(
            items=[],
            total=0,
            page=1,
            pages=1,
            limit=20,
        )
        assert len(response.items) == 0
        assert response.total == 0

    def test_document_list_item_optional_fields(self) -> None:
        """Test DocumentListItem with optional fields as None."""
        item = DocumentListItem(
            document_id="hash123",
            status=DocumentStatus.PENDING,
            document_type=None,
            source_uri="gs://bucket/file.pdf",
            error_message=None,
            attempts=0,
            confidence=None,
            created_at=datetime.now(JST),
            updated_at=datetime.now(JST),
        )
        assert item.document_type is None
        assert item.error_message is None
        assert item.confidence is None

    def test_migration_metadata_empty_fields(self) -> None:
        """Test MigrationMetadata with no defaulted fields."""
        metadata = MigrationMetadata()
        assert metadata.from_version is None
        assert len(metadata.fields_defaulted) == 0

    def test_dashboard_response_empty_activity(self) -> None:
        """Test DashboardResponse with empty recent_activity."""
        response = DashboardResponse(
            today_count=0,
            success_rate_7d=100.0,
            pending_review=0,
            pro_usage=ProUsageResponse(
                daily_count=0,
                daily_limit=50,
                monthly_count=0,
                monthly_limit=1000,
            ),
        )
        assert len(response.recent_activity) == 0

    def test_document_detail_response_minimal(self) -> None:
        """Test DocumentDetailResponse with minimal required fields."""
        response = DocumentDetailResponse(
            document_id="hash123",
            status=DocumentStatus.PENDING,
            source_uri="gs://bucket/file.pdf",
            created_at=datetime.now(JST),
            updated_at=datetime.now(JST),
        )
        assert response.document_id == "hash123"
        assert response.extracted_data is None
        assert len(response.validation_errors) == 0
