"""Dashboard API routes."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter
from google.api_core.exceptions import FailedPrecondition
from google.cloud.firestore_v1.base_query import FieldFilter

from api.deps import CurrentUser, FirestoreClient
from api.models import (
    ActivityItem,
    DashboardResponse,
    ProUsageResponse,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


def _handle_index_error(func_name: str, error: FailedPrecondition) -> None:
    """Log index errors with helpful message."""
    logger.warning(
        f"Firestore index missing for {func_name}. "
        "Run 'firebase deploy --only firestore:indexes' to create indexes.",
        error=str(error),
    )

# Constants
JST = ZoneInfo("Asia/Tokyo")
PRO_DAILY_LIMIT = 50
PRO_MONTHLY_LIMIT = 1000


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    db: FirestoreClient,
    user: CurrentUser,
) -> DashboardResponse:
    """
    Get dashboard summary data.

    Returns today's processing count, 7-day success rate,
    pending review count, Pro API usage, and recent activity.
    """
    logger.info("Fetching dashboard data", user=user.email)

    # Get counts and metrics
    today_count = await _count_documents_today(db)
    success_rate = await _calculate_success_rate(db, days=7)
    pending_review = await _count_pending_documents(db)
    pro_usage = await _get_pro_usage(db)
    recent_activity = await _get_recent_activity(db, limit=10)

    return DashboardResponse(
        today_count=today_count,
        success_rate_7d=success_rate,
        pending_review=pending_review,
        pro_usage=pro_usage,
        recent_activity=recent_activity,
    )


async def _count_documents_today(db: FirestoreClient) -> int:
    """Count documents processed today (JST)."""
    today_start = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        docs = (
            db.collection("processed_documents")
            .where(filter=FieldFilter("created_at", ">=", today_start))
            .count()
            .get()
        )
        return docs[0][0].value if docs else 0
    except FailedPrecondition as e:
        _handle_index_error("_count_documents_today", e)
        return 0


async def _calculate_success_rate(db: FirestoreClient, days: int = 7) -> float:
    """Calculate success rate over the past N days."""
    start_date = datetime.now(JST) - timedelta(days=days)

    try:
        # Count total documents
        total_query = (
            db.collection("processed_documents")
            .where(filter=FieldFilter("created_at", ">=", start_date))
            .count()
            .get()
        )
        total = total_query[0][0].value if total_query else 0

        if total == 0:
            return 100.0

        # Count successful documents
        success_query = (
            db.collection("processed_documents")
            .where(filter=FieldFilter("created_at", ">=", start_date))
            .where(filter=FieldFilter("status", "in", ["COMPLETED", "APPROVED"]))
            .count()
            .get()
        )
        success = success_query[0][0].value if success_query else 0

        return round((success / total) * 100, 1)
    except FailedPrecondition as e:
        _handle_index_error("_calculate_success_rate", e)
        return 100.0


async def _count_pending_documents(db: FirestoreClient) -> int:
    """Count documents pending human review."""
    try:
        docs = (
            db.collection("processed_documents")
            .where(filter=FieldFilter("status", "in", ["FAILED", "QUARANTINED"]))
            .count()
            .get()
        )
        return docs[0][0].value if docs else 0
    except FailedPrecondition as e:
        _handle_index_error("_count_pending_documents", e)
        return 0


async def _get_pro_usage(db: FirestoreClient) -> ProUsageResponse:
    """Get Pro API usage statistics."""
    now = datetime.now(JST)
    today_key = now.strftime("%Y-%m-%d")
    month_key = now.strftime("%Y-%m")

    # Get budget document
    budget_doc = db.collection("system_config").document("pro_budget").get()

    if not budget_doc.exists:
        return ProUsageResponse(
            daily_count=0,
            daily_limit=PRO_DAILY_LIMIT,
            monthly_count=0,
            monthly_limit=PRO_MONTHLY_LIMIT,
        )

    data = budget_doc.to_dict()
    daily_data = data.get("daily", {})
    monthly_data = data.get("monthly", {})

    return ProUsageResponse(
        daily_count=daily_data.get(today_key, 0),
        daily_limit=PRO_DAILY_LIMIT,
        monthly_count=monthly_data.get(month_key, 0),
        monthly_limit=PRO_MONTHLY_LIMIT,
    )


async def _get_recent_activity(
    db: FirestoreClient,
    limit: int = 10,
) -> list[ActivityItem]:
    """Get recent activity from audit log."""
    try:
        docs = (
            db.collection("audit_log")
            .order_by("timestamp", direction="DESCENDING")
            .limit(limit)
            .stream()
        )

        activities = []
        for doc in docs:
            data = doc.to_dict()
            activities.append(
                ActivityItem(
                    timestamp=data.get("timestamp", datetime.now(JST)),
                    event=data.get("event", "UNKNOWN"),
                    document_id=data.get("document_id", ""),
                    status=data.get("status", ""),
                    message=_format_activity_message(data),
                )
            )

        return activities
    except FailedPrecondition as e:
        _handle_index_error("_get_recent_activity", e)
        return []


def _format_activity_message(data: dict) -> str:
    """Format activity data into a human-readable message."""
    event = data.get("event", "")
    doc_id = data.get("document_id", "unknown")[:20]

    messages = {
        "CREATED": f"Document {doc_id} uploaded",
        "EXTRACTED": f"Document {doc_id} extracted successfully",
        "VALIDATED": f"Document {doc_id} validated",
        "CORRECTED": f"Document {doc_id} corrected by {data.get('user_id', 'user')}",
        "APPROVED": f"Document {doc_id} approved by {data.get('user_id', 'user')}",
        "FAILED": f"Document {doc_id} failed: {data.get('error_message', 'unknown error')[:50]}",
        "QUARANTINED": f"Document {doc_id} quarantined",
        "REJECTED": f"Document {doc_id} rejected",
    }

    return messages.get(event, f"Document {doc_id}: {event}")
