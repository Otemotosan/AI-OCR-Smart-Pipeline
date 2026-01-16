"""Draft (auto-save) API routes."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, HTTPException
from google.cloud import firestore

from api.deps import CurrentUser, FirestoreClient
from api.models import DraftResponse, DraftSaveRequest

logger = structlog.get_logger(__name__)
router = APIRouter()

JST = ZoneInfo("Asia/Tokyo")


@router.put("/documents/{doc_hash}/draft")
async def save_draft(
    doc_hash: str,
    body: DraftSaveRequest,
    db: FirestoreClient,
    user: CurrentUser,
) -> dict:
    """
    Save a draft to Firestore.

    Drafts are user-specific and will be cleaned up after approval.
    """
    logger.info(
        "Saving draft",
        doc_hash=doc_hash,
        user=user.email,
    )

    # Save to drafts collection
    db.collection("drafts").document(f"{doc_hash}_{user.email}").set(
        {
            "doc_hash": doc_hash,
            "data": body.data,
            "saved_at": body.saved_at,
            "user_id": user.email,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
    )

    return {"status": "saved"}


@router.get("/documents/{doc_hash}/draft", response_model=DraftResponse | None)
async def get_draft(
    doc_hash: str,
    db: FirestoreClient,
    user: CurrentUser,
) -> DraftResponse | None:
    """
    Get a draft from Firestore.

    Returns the user's draft for this document if one exists.
    """
    logger.info(
        "Fetching draft",
        doc_hash=doc_hash,
        user=user.email,
    )

    # Try user-specific draft first
    draft_doc = db.collection("drafts").document(f"{doc_hash}_{user.email}").get()

    if not draft_doc.exists:
        # Try generic draft (for backwards compatibility)
        draft_doc = db.collection("drafts").document(doc_hash).get()

        if not draft_doc.exists:
            raise HTTPException(status_code=404, detail="No draft found")

        draft = draft_doc.to_dict()

        # Check if draft belongs to another user
        if draft.get("user_id") and draft["user_id"] != user.email:
            raise HTTPException(
                status_code=403,
                detail="Draft belongs to another user",
            )
    else:
        draft = draft_doc.to_dict()

    return DraftResponse(
        doc_hash=draft.get("doc_hash", doc_hash),
        data=draft.get("data", {}),
        saved_at=draft.get("saved_at", datetime.now(JST).isoformat()),
        user_id=draft.get("user_id", user.email),
    )


@router.delete("/documents/{doc_hash}/draft")
async def delete_draft(
    doc_hash: str,
    db: FirestoreClient,
    user: CurrentUser,
) -> dict:
    """
    Delete a draft from Firestore.

    Called after document approval to clean up drafts.
    """
    logger.info(
        "Deleting draft",
        doc_hash=doc_hash,
        user=user.email,
    )

    # Delete user-specific draft
    db.collection("drafts").document(f"{doc_hash}_{user.email}").delete()

    # Also try to delete generic draft
    db.collection("drafts").document(doc_hash).delete()

    return {"status": "deleted"}


async def cleanup_draft(db: FirestoreClient, doc_hash: str) -> None:
    """
    Clean up all drafts for a document.

    Called after document approval/rejection to remove all user drafts.
    """
    # Query all drafts for this document
    drafts = db.collection("drafts").where("doc_hash", "==", doc_hash).stream()

    # Delete each draft
    for draft in drafts:
        draft.reference.delete()

    # Also delete by document ID pattern
    db.collection("drafts").document(doc_hash).delete()

    logger.info("Cleaned up drafts for document", doc_hash=doc_hash)
