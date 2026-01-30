"""API routes package."""

from __future__ import annotations

from fastapi import APIRouter

from .dashboard import router as dashboard_router
from .documents import router as documents_router
from .drafts import router as drafts_router
from .upload import router as upload_router

# Main API router
api_router = APIRouter(prefix="/api")

# Include sub-routers
api_router.include_router(dashboard_router, tags=["dashboard"])
api_router.include_router(documents_router, tags=["documents"])
api_router.include_router(drafts_router, tags=["drafts"])
api_router.include_router(upload_router, tags=["upload"])

__all__ = ["api_router"]
