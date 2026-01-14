"""Gemini Extraction with Retry Logic and Model Selection.

Handles document data extraction with:
- Conditional image attachment (cost optimization)
- Retry with self-correction
- Model escalation (Flash → Pro)
- Error classification and routing
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.cloud.documentai_v1 import Document

# ============================================================
# Constants
# ============================================================

CONFIDENCE_THRESHOLD = 0.85

FRAGILE_DOCUMENT_TYPES = {
    "fax",
    "handwritten",
    "thermal_receipt",
    "carbon_copy",
    "low_res_scan",
}

# ============================================================
# Data Classes
# ============================================================


@dataclass
class GeminiInput:
    """Input package for Gemini API call.

    Attributes:
        markdown: Structured markdown from Document AI
        image_base64: Optional base64-encoded original image
        include_image: Whether image should be included
        reason: Reason for image inclusion (if any)

    Examples:
        >>> input_data = GeminiInput(
        ...     markdown="# Invoice...",
        ...     include_image=True,
        ...     reason="low_confidence:0.82"
        ... )
    """

    markdown: str
    image_base64: str | None = None
    include_image: bool = False
    reason: str | None = None


# ============================================================
# Image Attachment Logic
# ============================================================


def prepare_gemini_input(
    document: Document,
    original_image: bytes,
    filename: str,
    gate_linter_failed: bool = False,
    attempt_number: int = 0,
) -> GeminiInput:
    """Determine whether to include original image in Gemini request.

    Default: Markdown only (cost-efficient ~2K tokens)
    Include image when (~10K tokens, 5x cost):
      1. Gate Linter previously failed (semantic validation error)
      2. Document AI confidence < 0.85 (OCR quality uncertain)
      3. Document type is detected as fragile (known OCR difficulties)
      4. Retry attempt (attempt > 0, first attempt failed)

    Args:
        document: Document AI Document object
        original_image: Original PDF/image bytes
        filename: Original filename for fragile type detection
        gate_linter_failed: Whether previous attempt failed Gate Linter
        attempt_number: Current attempt number (0 = first attempt)

    Returns:
        GeminiInput with markdown and optional image

    Examples:
        >>> from core.docai import DocumentAIClient
        >>> client = DocumentAIClient(project_id="test")
        >>> # Assume we have document and image
        >>> input_data = prepare_gemini_input(
        ...     document=doc,
        ...     original_image=image_bytes,
        ...     filename="invoice.pdf",
        ...     gate_linter_failed=False,
        ...     attempt_number=0
        ... )
        >>> input_data.include_image  # False on first attempt with good confidence
        False
    """
    from core.docai import DocumentAIClient

    # Extract markdown and confidence
    client = DocumentAIClient(project_id="dummy")  # Only using methods, not API calls
    markdown = client.extract_markdown(document)
    confidence = client.calculate_confidence(document)
    fragile_type = client.detect_document_type(filename, document)

    # Determine if image is needed
    include_image = False
    reason = None

    if gate_linter_failed:
        include_image = True
        reason = "gate_linter_failed"
    elif confidence < CONFIDENCE_THRESHOLD:
        include_image = True
        reason = f"low_confidence:{confidence:.3f}"
    elif fragile_type:
        include_image = True
        reason = f"fragile_type:{fragile_type}"
    elif attempt_number > 0:
        include_image = True
        reason = f"retry_attempt:{attempt_number}"

    # Build input
    gemini_input = GeminiInput(
        markdown=markdown,
        include_image=include_image,
        reason=reason,
    )

    if include_image:
        gemini_input.image_base64 = base64.b64encode(original_image).decode("utf-8")

    return gemini_input


def should_attach_image(
    confidence: float,
    gate_failed: bool,
    attempt: int,
    doc_type: str | None,
) -> tuple[bool, str]:
    """Determine if image should be attached (standalone version).

    Simpler version of prepare_gemini_input logic for testing
    and decision visibility.

    Args:
        confidence: Document AI confidence score (0.0-1.0)
        gate_failed: Whether Gate Linter validation failed
        attempt: Current attempt number (0 = first attempt)
        doc_type: Detected fragile document type (if any)

    Returns:
        Tuple of (should_attach, reason)

    Examples:
        >>> should_attach, reason = should_attach_image(
        ...     confidence=0.82,
        ...     gate_failed=False,
        ...     attempt=0,
        ...     doc_type=None
        ... )
        >>> should_attach
        True
        >>> reason
        'low_confidence:0.820'
    """
    if gate_failed:
        return True, "gate_linter_failed"

    if confidence < CONFIDENCE_THRESHOLD:
        return True, f"low_confidence:{confidence:.3f}"

    if doc_type in FRAGILE_DOCUMENT_TYPES:
        return True, f"fragile_type:{doc_type}"

    if attempt > 0:
        return True, f"retry_attempt:{attempt}"

    return False, "markdown_only"


# ============================================================
# Error Classification
# ============================================================


class SyntaxValidationError(Exception):
    """Raised when Gemini output is not valid JSON or fails schema validation."""


class SemanticValidationError(Exception):
    """Raised when extracted data fails Gate Linter validation."""


class ProBudgetExhaustedError(Exception):
    """Raised when Pro call budget is exceeded."""


def classify_error(error: Exception, gate_result: dict | None = None) -> str:
    """Classify error type for routing decision.

    Args:
        error: Exception that occurred
        gate_result: Optional Gate Linter result (if validation failed)

    Returns:
        Error type string: "syntax" | "semantic" | "http_429" | "http_5xx" | "unknown"

    Examples:
        >>> import json
        >>> try:
        ...     json.loads("invalid json")
        ... except json.JSONDecodeError as e:
        ...     error_type = classify_error(e)
        >>> error_type
        'syntax'
    """
    import json

    # Syntax errors (JSON parsing, schema validation)
    if isinstance(error, (json.JSONDecodeError, SyntaxValidationError)):
        return "syntax"

    # Semantic errors (Gate Linter validation failed)
    if isinstance(error, SemanticValidationError):
        return "semantic"

    # HTTP errors
    error_str = str(error).lower()
    if "429" in error_str or "rate limit" in error_str or "quota" in error_str:
        return "http_429"

    if any(code in error_str for code in ["500", "502", "503", "504"]):
        return "http_5xx"

    return "unknown"


# ============================================================
# Model Selection Logic
# ============================================================

# Retry limits by error type
FLASH_SYNTAX_RETRIES = 2
FLASH_HTTP429_RETRIES = 5
FLASH_HTTP5XX_RETRIES = 3


def select_model(
    error_type: str,
    flash_attempts: int,
    pro_budget_available: bool = True,
) -> str:
    """Select model based on error type and attempt count.

    Decision table:
    - Syntax error + attempts < 2 → Flash retry
    - HTTP 429 + attempts < 5 → Flash retry (with backoff)
    - HTTP 5xx + attempts < 3 → Flash retry (with fixed interval)
    - Semantic error + budget available → Pro escalation
    - Semantic error + no budget → Human review
    - Max retries exhausted → Human review

    Args:
        error_type: Error classification ("syntax" | "semantic" | "http_429" | "http_5xx")
        flash_attempts: Number of Flash attempts so far
        pro_budget_available: Whether Pro budget is available

    Returns:
        Model selection: "flash" | "pro" | "human"

    Examples:
        >>> select_model("syntax", flash_attempts=1)
        'flash'
        >>> select_model("syntax", flash_attempts=2)
        'human'
        >>> select_model("semantic", flash_attempts=1, pro_budget_available=True)
        'pro'
        >>> select_model("semantic", flash_attempts=1, pro_budget_available=False)
        'human'
    """
    # Syntax errors: Retry with Flash (max 2 attempts)
    if error_type == "syntax" and flash_attempts < FLASH_SYNTAX_RETRIES:
        return "flash"

    # HTTP 429: Retry with backoff (max 5 attempts)
    if error_type == "http_429" and flash_attempts < FLASH_HTTP429_RETRIES:
        return "flash"

    # HTTP 5xx: Retry with fixed interval (max 3 attempts)
    if error_type == "http_5xx" and flash_attempts < FLASH_HTTP5XX_RETRIES:
        return "flash"

    # Semantic error: Escalate to Pro (if budget available)
    if error_type == "semantic":
        if pro_budget_available:
            return "pro"
        else:
            return "human"

    # Max retries exhausted or unknown error
    return "human"
