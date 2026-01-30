"""Upload endpoint for file uploads to GCS."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from ..deps import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()

settings = get_settings()


class UploadResponse(BaseModel):
    """Response model for file upload."""

    status: str
    document_id: str
    source_uri: str
    message: str


def get_file_hash(content: bytes) -> str:
    """Calculate SHA256 hash of file content."""
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def save_to_local(content: bytes, filename: str) -> str:
    """Save file to local uploads directory for development."""
    # Create uploads directory if it doesn't exist
    uploads_dir = Path(__file__).parent.parent.parent.parent / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename with timestamp
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{filename}"
    file_path = uploads_dir / safe_filename

    # Write file
    file_path.write_bytes(content)

    return f"file://{file_path.absolute()}"


def save_to_gcs(content: bytes, filename: str, bucket_name: str) -> str:
    """Upload file to Google Cloud Storage."""
    from google.cloud import storage

    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    # Generate a unique blob name using timestamp and original filename
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    blob_name = f"{timestamp}_{filename}"
    blob = bucket.blob(blob_name)

    # Upload with content type
    blob.upload_from_string(content, content_type="application/pdf")

    return f"gs://{bucket_name}/{blob_name}"


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: Annotated[UploadFile, File(description="PDF file to upload")],
) -> UploadResponse:
    """
    Upload a PDF file for OCR processing.

    In production: uploads to GCS, triggering OCR Cloud Function
    In development: saves to local uploads directory
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported",
        )

    # Read file content
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
        )

    # Check file size (max 50MB)
    max_size = 50 * 1024 * 1024  # 50MB
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {max_size // (1024 * 1024)}MB",
        )

    # Calculate document ID from content hash
    document_id = get_file_hash(content)

    try:
        # Development mode: save locally
        if settings.environment == "development":
            source_uri = save_to_local(content, file.filename)
            message = (
                "File saved locally. "
                "Note: OCR processing requires GCS upload in staging/production."
            )
        else:
            # Production/staging: upload to GCS
            bucket_name = settings.gcs_input_bucket
            if not bucket_name:
                project_id = settings.gcp_project_id or "ai-ocr-smart-pipeline"
                env_suffix = "staging" if settings.environment != "production" else "prod"
                bucket_name = f"{project_id}-ocr-input-{env_suffix}"

            source_uri = save_to_gcs(content, file.filename, bucket_name)
            message = "File uploaded successfully. OCR processing will begin automatically."

        logger.info(
            "File uploaded successfully",
            extra={
                "document_id": document_id,
                "source_uri": source_uri,
                "file_size": len(content),
                "environment": settings.environment,
            },
        )

        return UploadResponse(
            status="uploaded",
            document_id=document_id,
            source_uri=source_uri,
            message=message,
        )

    except Exception as e:
        logger.exception("Failed to upload file")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {e!s}",
        ) from e

