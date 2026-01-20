"""Gemini API Client with Retry Logic and Cost Tracking.

Provides Flash and Pro model calls with:
- Automatic retry handling (exponential backoff, fixed intervals)
- Budget enforcement through BudgetManager integration
- Structured logging with cost estimation
- JSON response parsing and validation
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
    wait_random,
)

if TYPE_CHECKING:
    import google.generativeai as genai
    from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable

logger = structlog.get_logger(__name__)

# ============================================================
# Constants
# ============================================================

# Model names
FLASH_MODEL = "gemini-1.5-flash"
PRO_MODEL = "gemini-1.5-pro"

# Cost per 1K tokens (USD)
FLASH_INPUT_COST = 0.000125  # $0.125 / 1M tokens
FLASH_OUTPUT_COST = 0.000375  # $0.375 / 1M tokens
PRO_INPUT_COST = 0.00125  # $1.25 / 1M tokens
PRO_OUTPUT_COST = 0.005  # $5.00 / 1M tokens

# Token estimates (approximate)
MARKDOWN_ONLY_TOKENS = 2000
MARKDOWN_WITH_IMAGE_TOKENS = 10000

# ============================================================
# Exceptions
# ============================================================


class SyntaxValidationError(Exception):
    """Raised when Gemini output is not valid JSON or fails schema validation."""


class SemanticValidationError(Exception):
    """Raised when extracted data fails Gate Linter validation."""


class ProBudgetExhaustedError(Exception):
    """Raised when Pro call budget is exceeded."""


# ============================================================
# Data Classes
# ============================================================


@dataclass
class GeminiResponse:
    """Response from Gemini API call.

    Attributes:
        data: Parsed JSON data from response
        raw_text: Raw text response
        model_used: Model name (flash or pro)
        input_tokens: Estimated input tokens
        output_tokens: Estimated output tokens
        cost_usd: Estimated cost in USD

    Examples:
        >>> response = GeminiResponse(
        ...     data={"management_id": "INV-001"},
        ...     raw_text='{"management_id": "INV-001"}',
        ...     model_used="flash",
        ...     input_tokens=2000,
        ...     output_tokens=100,
        ...     cost_usd=0.0001
        ... )
    """

    data: dict[str, Any]
    raw_text: str
    model_used: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


# ============================================================
# Retry Decorators
# ============================================================


# Import exceptions for retry logic
# Use fallback classes that are always valid Exception subclasses
# This ensures tenacity works even if google.api_core is mocked in tests
class _ResourceExhaustedError(Exception):
    """Fallback exception for rate limiting (HTTP 429)."""


class _ServiceUnavailableError(Exception):
    """Fallback exception for transient errors (HTTP 5xx)."""


try:
    from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable

    # Verify they are actual exception classes (not mocks from tests)
    if not isinstance(ResourceExhausted, type) or not issubclass(ResourceExhausted, Exception):
        ResourceExhausted = _ResourceExhaustedError  # type: ignore[misc]
    if not isinstance(ServiceUnavailable, type) or not issubclass(ServiceUnavailable, Exception):
        ServiceUnavailable = _ServiceUnavailableError  # type: ignore[misc]
except (ImportError, TypeError):
    # Fallback for testing without google-api-core
    ResourceExhausted = _ResourceExhaustedError  # type: ignore[misc]
    ServiceUnavailable = _ServiceUnavailableError  # type: ignore[misc]


# Rate limit retry (HTTP 429)
retry_rate_limit = retry(
    retry=retry_if_exception_type(ResourceExhausted),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=32) + wait_random(0, 2),
    reraise=True,
)

# Transient error retry (HTTP 5xx)
retry_transient = retry(
    retry=retry_if_exception_type(ServiceUnavailable),
    stop=stop_after_attempt(3),
    wait=wait_fixed(2),
    reraise=True,
)

# Syntax error retry (immediate)
retry_syntax = retry(
    retry=retry_if_exception_type(SyntaxValidationError),
    stop=stop_after_attempt(2),
    wait=wait_fixed(0),  # Immediate retry
    reraise=True,
)


# ============================================================
# Gemini Client
# ============================================================


class GeminiClient:
    """Client for Gemini API with retry logic and cost tracking.

    Provides methods to call Flash and Pro models with automatic retry handling,
    budget enforcement, and structured logging.

    Examples:
        >>> client = GeminiClient(api_key="your-api-key")
        >>> response = client.call_flash(
        ...     prompt="Extract data from: # Invoice...",
        ...     image=None
        ... )
        >>> response.data
        {'management_id': 'INV-001', 'company_name': 'Acme Inc'}
    """

    def __init__(self, api_key: str) -> None:
        """Initialize Gemini client.

        Args:
            api_key: Google API key for Gemini
        """
        self.api_key = api_key
        self._genai: genai | None = None

    @property
    def genai(self) -> Any:
        """Lazy load google.generativeai module.

        Returns:
            google.generativeai module
        """
        if self._genai is None:
            import google.generativeai as genai  # type: ignore[import-untyped]

            genai.configure(api_key=self.api_key)
            self._genai = genai
        return self._genai

    @retry_rate_limit
    @retry_transient
    def call_flash(
        self,
        prompt: str,
        image: bytes | None = None,
    ) -> GeminiResponse:
        """Call Gemini Flash model with retry logic.

        Args:
            prompt: Text prompt for extraction
            image: Optional image bytes (triggers multimodal mode)

        Returns:
            GeminiResponse with extracted data

        Raises:
            ResourceExhausted: Rate limit exceeded (429)
            ServiceUnavailable: Server error (5xx)
            SyntaxValidationError: JSON parse failure

        Examples:
            >>> client = GeminiClient(api_key="key")
            >>> response = client.call_flash("Extract: # Invoice...")
        """
        logger.info("calling_flash_model", has_image=image is not None)

        # Create content for API call
        content = [prompt]
        if image:
            content.append({"mime_type": "image/png", "data": image})

        # Call Gemini API
        model = self.genai.GenerativeModel(FLASH_MODEL)
        response = model.generate_content(content)

        # Parse JSON response
        raw_text = response.text
        try:
            data = self.parse_json_response(raw_text)
        except json.JSONDecodeError as e:
            logger.error("json_parse_error", error=str(e), raw_text=raw_text[:200])
            raise SyntaxValidationError(f"Invalid JSON from Flash: {e}") from e

        # Estimate tokens and cost
        input_tokens = MARKDOWN_WITH_IMAGE_TOKENS if image else MARKDOWN_ONLY_TOKENS
        output_tokens = len(raw_text) // 4  # Rough estimate: 4 chars = 1 token
        cost_usd = self._calculate_cost(
            input_tokens,
            output_tokens,
            is_pro=False,
        )

        logger.info(
            "flash_call_success",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

        return GeminiResponse(
            data=data,
            raw_text=raw_text,
            model_used=FLASH_MODEL,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

    @retry_rate_limit
    @retry_transient
    def call_pro(
        self,
        prompt: str,
        image: bytes | None = None,
    ) -> GeminiResponse:
        """Call Gemini Pro model with retry logic.

        Args:
            prompt: Text prompt for extraction
            image: Optional image bytes (triggers multimodal mode)

        Returns:
            GeminiResponse with extracted data

        Raises:
            ResourceExhausted: Rate limit exceeded (429)
            ServiceUnavailable: Server error (5xx)
            SyntaxValidationError: JSON parse failure

        Examples:
            >>> client = GeminiClient(api_key="key")
            >>> response = client.call_pro("Extract: # Invoice...")
        """
        logger.info("calling_pro_model", has_image=image is not None)

        # Create content for API call
        content = [prompt]
        if image:
            content.append({"mime_type": "image/png", "data": image})

        # Call Gemini API
        model = self.genai.GenerativeModel(PRO_MODEL)
        response = model.generate_content(content)

        # Parse JSON response
        raw_text = response.text
        try:
            data = self.parse_json_response(raw_text)
        except json.JSONDecodeError as e:
            logger.error("json_parse_error", error=str(e), raw_text=raw_text[:200])
            raise SyntaxValidationError(f"Invalid JSON from Pro: {e}") from e

        # Estimate tokens and cost
        input_tokens = MARKDOWN_WITH_IMAGE_TOKENS if image else MARKDOWN_ONLY_TOKENS
        output_tokens = len(raw_text) // 4  # Rough estimate: 4 chars = 1 token
        cost_usd = self._calculate_cost(
            input_tokens,
            output_tokens,
            is_pro=True,
        )

        logger.info(
            "pro_call_success",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

        return GeminiResponse(
            data=data,
            raw_text=raw_text,
            model_used=PRO_MODEL,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

    def parse_json_response(self, response: str) -> dict[str, Any]:
        """Parse JSON from Gemini response.

        Handles common formatting issues:
        - Removes markdown code fences (```json, ```)
        - Strips whitespace
        - Validates JSON structure

        Args:
            response: Raw text response from Gemini

        Returns:
            Parsed JSON data

        Raises:
            json.JSONDecodeError: If response is not valid JSON

        Examples:
            >>> client = GeminiClient(api_key="key")
            >>> client.parse_json_response('{"id": "123"}')
            {'id': '123'}
            >>> client.parse_json_response('```json\\n{"id": "123"}\\n```')
            {'id': '123'}
        """
        # Remove markdown code fences if present
        text = response.strip()
        if text.startswith("```json"):
            text = text[7:]  # Remove ```json
        if text.startswith("```"):
            text = text[3:]  # Remove ```
        if text.endswith("```"):
            text = text[:-3]  # Remove trailing ```

        # Parse JSON
        return json.loads(text.strip())

    def _calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        is_pro: bool,
    ) -> float:
        """Calculate estimated cost in USD.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            is_pro: Whether Pro model was used

        Returns:
            Estimated cost in USD

        Examples:
            >>> client = GeminiClient(api_key="key")
            >>> client._calculate_cost(2000, 100, is_pro=False)
            0.0006...
        """
        if is_pro:
            input_cost = (input_tokens / 1000) * PRO_INPUT_COST
            output_cost = (output_tokens / 1000) * PRO_OUTPUT_COST
        else:
            input_cost = (input_tokens / 1000) * FLASH_INPUT_COST
            output_cost = (output_tokens / 1000) * FLASH_OUTPUT_COST

        return input_cost + output_cost
