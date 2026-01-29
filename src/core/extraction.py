"""Gemini Extraction with Retry Logic and Model Selection.

Handles document data extraction with:
- Conditional image attachment (cost optimization)
- Retry with self-correction
- Model escalation (Flash → Pro)
- Error classification and routing
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import structlog

from src.core.gemini import (
    SemanticValidationError,
    SyntaxValidationError,
)

if TYPE_CHECKING:
    from google.cloud.documentai_v1 import Document
    from pydantic import BaseModel

logger = structlog.get_logger(__name__)

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
    from src.core.docai import DocumentAIClient

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


# ============================================================
# Extraction Result
# ============================================================


@dataclass
class ExtractionAttempt:
    """Record of a single extraction attempt.

    Attributes:
        model: Model used ("flash" or "pro")
        prompt_tokens: Estimated input tokens
        output_tokens: Estimated output tokens
        cost_usd: Cost in USD
        error: Error message if failed (None if successful)
        data: Extracted data if successful (None if failed)

    Examples:
        >>> attempt = ExtractionAttempt(
        ...     model="flash",
        ...     prompt_tokens=2000,
        ...     output_tokens=100,
        ...     cost_usd=0.0001,
        ...     error=None,
        ...     data={"management_id": "INV-001"}
        ... )
    """

    model: str
    prompt_tokens: int
    output_tokens: int
    cost_usd: float
    error: str | None = None
    data: dict[str, Any] | None = None


@dataclass
class ExtractionResult:
    """Result of extraction with audit trail.

    Attributes:
        schema: Validated schema instance if successful (None if failed)
        status: Final status ("SUCCESS" or "FAILED")
        attempts: List of all extraction attempts
        final_model: Final model used ("flash", "pro", or "none")
        total_cost: Total cost across all attempts in USD
        reason: Reason for failure (None if successful)

    Examples:
        >>> result = ExtractionResult(
        ...     schema=DeliveryNoteV2(...),
        ...     status="SUCCESS",
        ...     attempts=[attempt1, attempt2],
        ...     final_model="pro",
        ...     total_cost=0.0015,
        ...     reason=None
        ... )
    """

    schema: BaseModel | None
    status: Literal["SUCCESS", "FAILED"]
    attempts: list[ExtractionAttempt] = field(default_factory=list)
    final_model: str = "none"
    total_cost: float = 0.0
    reason: str | None = None


# ============================================================
# Self-Correction Loop
# ============================================================


def extract_with_retry(  # noqa: C901
    gemini_input: GeminiInput,
    schema_class: type[BaseModel],
    gemini_client: Any,  # GeminiClient from core.gemini
    budget_manager: Any,  # BudgetManager from core.budget
    gate_linter: Any,  # GateLinter from core.linters.gate
) -> ExtractionResult:
    """Extract data with self-correction and model escalation.

    Implements the retry flow:
    1. Initial Flash attempt
    2. Classify errors and retry with Flash (syntax/HTTP errors)
    3. Escalate to Pro on semantic errors (Gate Linter failures)
    4. Return FAILED if all retries exhausted

    Args:
        gemini_input: Prepared input with markdown and optional image
        schema_class: Pydantic schema class for validation
        gemini_client: GeminiClient instance for API calls
        budget_manager: BudgetManager for Pro budget tracking
        gate_linter: GateLinter for immutable validation

    Returns:
        ExtractionResult with validated schema or failure details

    Examples:
        >>> from core.gemini import GeminiClient
        >>> from core.budget import BudgetManager
        >>> from core.linters.gate import GateLinter
        >>> from core.schemas import DeliveryNoteV2
        >>>
        >>> client = GeminiClient(api_key="key")
        >>> budget = BudgetManager(firestore_client)
        >>> linter = GateLinter()
        >>>
        >>> input_data = GeminiInput(markdown="# Invoice...", include_image=False)
        >>> result = extract_with_retry(input_data, DeliveryNoteV2, client, budget, linter)
        >>> assert result.status == "SUCCESS"
        >>> assert result.schema is not None
    """
    # from src.core.gemini import SyntaxValidationError as GeminiSyntaxError
    from src.core.prompts import build_extraction_prompt

    attempts: list[ExtractionAttempt] = []
    flash_attempt_count = 0
    last_gate_errors: list[str] = []

    logger.info(
        "starting_extraction",
        schema=schema_class.__name__,
        include_image=gemini_input.include_image,
    )

    # === Phase 1: Flash Attempts ===
    while flash_attempt_count < FLASH_SYNTAX_RETRIES + 1:  # Initial + 2 retries
        try:
            flash_attempt_count += 1

            # Build prompt with previous attempt context
            previous_attempts = [{"data": a.data, "error": a.error} for a in attempts if a.error]
            prompt = build_extraction_prompt(
                gemini_input=gemini_input,
                schema_class=schema_class,
                previous_attempts=previous_attempts if previous_attempts else None,
                errors=last_gate_errors if last_gate_errors else None,
            )

            logger.info("calling_flash", attempt=flash_attempt_count)

            # Decode image if present
            image_bytes = None
            if gemini_input.include_image and gemini_input.image_base64:
                image_bytes = base64.b64decode(gemini_input.image_base64)

            # Call Flash model
            response = gemini_client.call_flash_v2(prompt, image_bytes)

            # Record attempt
            attempt = ExtractionAttempt(
                model="flash",
                prompt_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=response.cost_usd,
                data=response.data,
            )
            attempts.append(attempt)

            # Enforce document_type from schema class if available to prevent case mismatches
            # e.g. Gemini returns "OrderForm" but schema expects "order_form"
            has_model_fields = hasattr(schema_class, "model_fields")
            if has_model_fields and "document_type" in schema_class.model_fields:
                field = schema_class.model_fields["document_type"]
                # Only if default exists and is not None
                if field.default is not None:
                    # model_fields returns FieldInfo. default is the value.
                    response.data["document_type"] = field.default

            # Validate with Gate Linter
            gate_result = gate_linter.validate(response.data)

            if not gate_result.passed:
                # Semantic error - Gate Linter failed
                last_gate_errors = gate_result.errors
                error_msg = f"Gate Linter failed: {', '.join(gate_result.errors)}"
                attempt.error = error_msg
                logger.warning(
                    "gate_linter_failed",
                    attempt=flash_attempt_count,
                    errors=gate_result.errors,
                )

                # Classify as semantic error and check if we should escalate
                error_type = "semantic"
                next_model = select_model(
                    error_type=error_type,
                    flash_attempts=flash_attempt_count,
                    pro_budget_available=budget_manager.check_pro_budget(),
                )

                if next_model == "pro":
                    # Escalate to Pro
                    break
                elif next_model == "human":
                    # Exhausted retries
                    logger.error(
                        "flash_retries_exhausted",
                        attempts=flash_attempt_count,
                        errors=last_gate_errors,
                    )
                    return ExtractionResult(
                        schema=None,
                        status="FAILED",
                        attempts=attempts,
                        final_model="flash",
                        total_cost=sum(a.cost_usd for a in attempts),
                        reason=f"Flash retries exhausted: {error_msg}",
                    )
                # Otherwise retry with Flash
                continue

            # Validate with Pydantic schema
            try:
                validated_schema = schema_class(**response.data)
                logger.info(
                    "extraction_success",
                    model="flash",
                    attempts=flash_attempt_count,
                    cost=sum(a.cost_usd for a in attempts),
                )
                return ExtractionResult(
                    schema=validated_schema,
                    status="SUCCESS",
                    attempts=attempts,
                    final_model="flash",
                    total_cost=sum(a.cost_usd for a in attempts),
                )
            except Exception as e:
                # Pydantic validation failed
                attempt.error = f"Schema validation failed: {e}"
                logger.error("schema_validation_failed", error=str(e))
                # Treat as semantic error and escalate
                break

        except SyntaxValidationError as e:
            # Syntax error (invalid JSON)
            attempt = ExtractionAttempt(
                model="flash",
                prompt_tokens=2000,  # Estimate
                output_tokens=100,
                cost_usd=0.0,
                error=f"Syntax error: {e}",
            )
            attempts.append(attempt)

            logger.warning(
                "syntax_error",
                attempt=flash_attempt_count,
                error=str(e),
            )

            # Check if we should retry
            error_type = "syntax"
            next_model = select_model(
                error_type=error_type,
                flash_attempts=flash_attempt_count,
                pro_budget_available=False,  # Don't escalate to Pro for syntax errors
            )

            if next_model == "human":
                return ExtractionResult(
                    schema=None,
                    status="FAILED",
                    attempts=attempts,
                    final_model="flash",
                    total_cost=sum(a.cost_usd for a in attempts),
                    reason=f"Syntax errors exhausted: {e}",
                )
            # Otherwise retry with Flash
            continue

        except Exception as e:
            # Check for import mismatch
            if type(e).__name__ == "SyntaxValidationError":
                logger.warning("syntax_error_mismatch", error=str(e))
                # Treat as syntax error
                attempt = ExtractionAttempt(
                    model="flash",
                    prompt_tokens=2000,
                    output_tokens=100,
                    cost_usd=0.0,
                    error=f"Syntax error: {e}",
                )
                attempts.append(attempt)

                # Retry logic
                error_type = "syntax"
                next_model = select_model(
                    error_type=error_type,
                    flash_attempts=flash_attempt_count,
                    pro_budget_available=False,
                )
                if next_model == "human":
                    return ExtractionResult(
                        schema=None,
                        status="FAILED",
                        attempts=attempts,
                        final_model="flash",
                        total_cost=sum(a.cost_usd for a in attempts),
                        reason=f"Syntax errors exhausted: {e}",
                    )
                continue

            # Unexpected error
            logger.error("unexpected_error", error=str(e), type=type(e).__name__)
            attempt = ExtractionAttempt(
                model="flash",
                prompt_tokens=2000,
                output_tokens=0,
                cost_usd=0.0,
                error=f"Unexpected error: {e}",
            )
            attempts.append(attempt)
            return ExtractionResult(
                schema=None,
                status="FAILED",
                attempts=attempts,
                final_model="flash",
                total_cost=sum(a.cost_usd for a in attempts),
                reason=f"Unexpected error: {e}",
            )

    # === Phase 2: Pro Escalation ===
    logger.info("escalating_to_pro", flash_attempts=flash_attempt_count)

    # Check Pro budget
    if not budget_manager.check_pro_budget():
        logger.error("pro_budget_exhausted")
        return ExtractionResult(
            schema=None,
            status="FAILED",
            attempts=attempts,
            final_model="flash",
            total_cost=sum(a.cost_usd for a in attempts),
            reason="Pro budget exhausted",
        )

    try:
        # Increment Pro usage
        budget_manager.increment_pro_usage()

        # Build prompt with escalation note
        previous_attempts = [{"data": a.data, "error": a.error} for a in attempts if a.error]
        prompt = build_extraction_prompt(
            gemini_input=gemini_input,
            schema_class=schema_class,
            previous_attempts=previous_attempts,
            errors=last_gate_errors if last_gate_errors else None,
        )
        prompt += (
            "\n\nNOTE: Previous attempts with Flash failed. "
            "Apply deep reasoning and careful analysis."
        )

        # Decode image if present
        image_bytes = None
        if gemini_input.include_image and gemini_input.image_base64:
            image_bytes = base64.b64decode(gemini_input.image_base64)

        # Call Pro model
        logger.info("calling_pro")
        response = gemini_client.call_pro_v2(prompt, image_bytes)

        # Record attempt
        attempt = ExtractionAttempt(
            model="pro",
            prompt_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=response.cost_usd,
            data=response.data,
        )
        attempts.append(attempt)

        # Validate with Gate Linter
        gate_result = gate_linter.validate(response.data)

        if not gate_result.passed:
            # Pro also failed Gate Linter
            attempt.error = f"Gate Linter failed: {', '.join(gate_result.errors)}"
            logger.error(
                "pro_gate_linter_failed",
                errors=gate_result.errors,
            )
            return ExtractionResult(
                schema=None,
                status="FAILED",
                attempts=attempts,
                final_model="pro",
                total_cost=sum(a.cost_usd for a in attempts),
                reason=f"Pro failed Gate Linter: {', '.join(gate_result.errors)}",
            )

        # Validate with Pydantic schema
        try:
            validated_schema = schema_class(**response.data)
            logger.info(
                "extraction_success",
                model="pro",
                total_attempts=len(attempts),
                cost=sum(a.cost_usd for a in attempts),
            )
            return ExtractionResult(
                schema=validated_schema,
                status="SUCCESS",
                attempts=attempts,
                final_model="pro",
                total_cost=sum(a.cost_usd for a in attempts),
            )
        except Exception as e:
            # Pydantic validation failed
            attempt.error = f"Schema validation failed: {e}"
            logger.error("pro_schema_validation_failed", error=str(e))
            return ExtractionResult(
                schema=None,
                status="FAILED",
                attempts=attempts,
                final_model="pro",
                total_cost=sum(a.cost_usd for a in attempts),
                reason=f"Pro schema validation failed: {e}",
            )

    except SyntaxValidationError as e:
        # Pro returned invalid JSON (rare)
        logger.error("pro_syntax_error", error=str(e))
        attempt = ExtractionAttempt(
            model="pro",
            prompt_tokens=10000,
            output_tokens=100,
            cost_usd=0.0,
            error=f"Syntax error: {e}",
        )
        attempts.append(attempt)
        return ExtractionResult(
            schema=None,
            status="FAILED",
            attempts=attempts,
            final_model="pro",
            total_cost=sum(a.cost_usd for a in attempts),
            reason=f"Pro syntax error: {e}",
        )

    except Exception as e:
        # Check for import mismatch
        if type(e).__name__ == "SyntaxValidationError":
            logger.warning("pro_syntax_error_mismatch", error=str(e))
            attempt = ExtractionAttempt(
                model="pro",
                prompt_tokens=10000,
                output_tokens=100,
                cost_usd=0.0,
                error=f"Syntax error: {e}",
            )
            attempts.append(attempt)
            return ExtractionResult(
                schema=None,
                status="FAILED",
                attempts=attempts,
                final_model="pro",
                total_cost=sum(a.cost_usd for a in attempts),
                reason=f"Pro syntax error: {e}",
            )

        # Unexpected error during Pro call
        logger.error("pro_unexpected_error", error=str(e), type=type(e).__name__)
        attempt = ExtractionAttempt(
            model="pro",
            prompt_tokens=10000,
            output_tokens=0,
            cost_usd=0.0,
            error=f"Unexpected error: {e}",
        )
        attempts.append(attempt)
        return ExtractionResult(
            schema=None,
            status="FAILED",
            attempts=attempts,
            final_model="pro",
            total_cost=sum(a.cost_usd for a in attempts),
            reason=f"Pro unexpected error: {e}",
        )
