"""API dependencies for authentication and resource access."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request
from google.cloud import bigquery, firestore, storage

logger = structlog.get_logger(__name__)


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class Settings:
    """Application settings."""

    project_id: str
    firestore_database: str
    gcs_input_bucket: str
    gcs_output_bucket: str
    gcs_quarantine_bucket: str
    bigquery_dataset: str
    cors_origins: list[str]
    environment: str


@lru_cache
def get_settings() -> Settings:
    """Get application settings from environment."""
    return Settings(
        project_id=os.getenv("PROJECT_ID", ""),
        firestore_database=os.getenv("FIRESTORE_DATABASE", "(default)"),
        gcs_input_bucket=os.getenv("GCS_INPUT_BUCKET", ""),
        gcs_output_bucket=os.getenv("GCS_OUTPUT_BUCKET", ""),
        gcs_quarantine_bucket=os.getenv("GCS_QUARANTINE_BUCKET", ""),
        bigquery_dataset=os.getenv("BIGQUERY_DATASET", "ocr_pipeline"),
        cors_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
        environment=os.getenv("ENVIRONMENT", "development"),
    )


# =============================================================================
# User Authentication (IAP)
# =============================================================================


@dataclass
class User:
    """Authenticated user from IAP."""

    email: str
    user_id: str


def get_iap_user(request: Request) -> User:
    """
    Extract user information from IAP headers.

    In production, IAP adds these headers:
    - X-Goog-Authenticated-User-Email: accounts.google.com:user@example.com
    - X-Goog-Authenticated-User-Id: accounts.google.com:123456789

    In development, allow bypass with custom headers or environment variable.
    """
    settings = get_settings()

    # Development mode: allow test user
    if settings.environment == "development":
        test_email = request.headers.get("X-Test-User-Email")
        if test_email:
            return User(email=test_email, user_id=f"test_{test_email}")

        # Default test user for local development
        dev_user = os.getenv("DEV_USER_EMAIL", "dev@example.com")
        return User(email=dev_user, user_id=f"dev_{dev_user}")

    # Production: require IAP headers
    email_header = request.headers.get("X-Goog-Authenticated-User-Email")
    id_header = request.headers.get("X-Goog-Authenticated-User-Id")

    if not email_header or not id_header:
        logger.warning("Missing IAP headers", headers=dict(request.headers))
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please access through Identity-Aware Proxy.",
        )

    # Parse IAP format: "accounts.google.com:user@example.com"
    email = email_header.split(":")[-1] if ":" in email_header else email_header
    user_id = id_header.split(":")[-1] if ":" in id_header else id_header

    return User(email=email, user_id=user_id)


# Type alias for dependency injection
CurrentUser = Annotated[User, Depends(get_iap_user)]


# =============================================================================
# Database Clients
# =============================================================================


@lru_cache
def get_firestore_client() -> firestore.Client:
    """Get Firestore client (cached)."""
    settings = get_settings()
    return firestore.Client(
        project=settings.project_id if settings.project_id else None,
        database=settings.firestore_database,
    )


@lru_cache
def get_storage_client() -> storage.Client:
    """Get Cloud Storage client (cached)."""
    settings = get_settings()
    return storage.Client(project=settings.project_id if settings.project_id else None)


@lru_cache
def get_bigquery_client() -> bigquery.Client:
    """Get BigQuery client (cached)."""
    settings = get_settings()
    return bigquery.Client(project=settings.project_id if settings.project_id else None)


# Dependency types
FirestoreClient = Annotated[firestore.Client, Depends(get_firestore_client)]
StorageClient = Annotated[storage.Client, Depends(get_storage_client)]
BigQueryClient = Annotated[bigquery.Client, Depends(get_bigquery_client)]


# =============================================================================
# Signed URL Generation
# =============================================================================


def generate_signed_url(
    client: storage.Client,
    gcs_uri: str,
    expiry_seconds: int = 3600,
) -> str:
    """
    Generate a signed URL for accessing a GCS object.

    Args:
        client: Storage client
        gcs_uri: GCS URI (gs://bucket/path)
        expiry_seconds: URL expiry time in seconds

    Returns:
        Signed URL for direct access
    """
    from datetime import timedelta

    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")

    # Parse gs://bucket/path
    parts = gcs_uri[5:].split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid GCS URI format: {gcs_uri}")

    bucket_name, blob_path = parts
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)

    # Generate signed URL
    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(seconds=expiry_seconds),
        method="GET",
    )

    return url
