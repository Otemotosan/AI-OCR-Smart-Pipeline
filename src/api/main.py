"""FastAPI application for the AI-OCR Review UI."""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator, Callable, Coroutine
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.deps import get_settings
from api.models import ErrorResponse, HealthResponse
from api.routes import api_router

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Application Lifecycle
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle manager."""
    logger.info("Starting AI-OCR Review UI API")
    yield
    logger.info("Shutting down AI-OCR Review UI API")


# =============================================================================
# Application Setup
# =============================================================================

VERSION = "1.0.0"

app = FastAPI(
    title="AI-OCR Review UI API",
    description="API for human review of OCR extraction results",
    version=VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)


# =============================================================================
# Middleware
# =============================================================================


# CORS middleware
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(
    request: Request,
    call_next: Callable[[Request], Coroutine[Any, Any, Response]],
) -> Response:
    """Log all requests with timing."""
    start_time = datetime.now()

    # Generate request ID
    request_id = request.headers.get("X-Request-ID", str(start_time.timestamp()))

    # Add to structlog context
    with structlog.contextvars.bind_contextvars(request_id=request_id):
        logger.info(
            "Request started",
            method=request.method,
            path=request.url.path,
        )

        response = await call_next(request)

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(
            "Request completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

    return response


# =============================================================================
# Exception Handlers
# =============================================================================


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle uncaught exceptions."""
    logger.exception(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )

    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            detail="An internal error occurred. Please try again later.",
            error_code="INTERNAL_ERROR",
        ).model_dump(),
    )


# =============================================================================
# Routes
# =============================================================================


# Include API routes
app.include_router(api_router)


# Health check endpoint
@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    """Health check endpoint for load balancers and monitoring."""
    return HealthResponse(
        status="healthy",
        version=VERSION,
        timestamp=datetime.now(),
    )


# Root redirect to docs
@app.get("/")
async def root() -> dict:
    """Root endpoint - provides API info."""
    return {
        "name": "AI-OCR Review UI API",
        "version": VERSION,
        "docs": "/api/docs",
        "health": "/health",
    }


# =============================================================================
# Static Files (React Frontend)
# =============================================================================

# Mount static files for frontend (in production)
# The frontend build will be in /app/static after Docker build
static_path = Path(__file__).parent.parent.parent / "static"
if static_path.exists():
    app.mount("/", StaticFiles(directory=str(static_path), html=True), name="static")


# =============================================================================
# Development Server
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # nosec B104 # noqa: S104 - Required for Cloud Run container binding
        port=8080,
        reload=True,
        log_level="info",
    )
