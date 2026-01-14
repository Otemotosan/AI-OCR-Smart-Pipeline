"""Unit tests for Gemini extraction logic."""

from __future__ import annotations

import json

from core.extraction import (
    CONFIDENCE_THRESHOLD,
    FLASH_HTTP5XX_RETRIES,
    FLASH_HTTP429_RETRIES,
    FLASH_SYNTAX_RETRIES,
    FRAGILE_DOCUMENT_TYPES,
    GeminiInput,
    ProBudgetExhaustedError,
    SemanticValidationError,
    SyntaxValidationError,
    classify_error,
    select_model,
    should_attach_image,
)


class TestGeminiInput:
    """Test GeminiInput dataclass."""

    def test_create_basic_input(self) -> None:
        """Test creating basic GeminiInput."""
        input_data = GeminiInput(markdown="# Test Document", include_image=False, reason=None)

        assert input_data.markdown == "# Test Document"
        assert input_data.include_image is False
        assert input_data.reason is None
        assert input_data.image_base64 is None

    def test_create_input_with_image(self) -> None:
        """Test creating GeminiInput with image."""
        input_data = GeminiInput(
            markdown="# Test",
            image_base64="base64encodedimage",
            include_image=True,
            reason="low_confidence:0.82",
        )

        assert input_data.include_image is True
        assert input_data.image_base64 == "base64encodedimage"
        assert input_data.reason == "low_confidence:0.82"


class TestShouldAttachImage:
    """Test image attachment decision logic."""

    def test_low_confidence_triggers_image(self) -> None:
        """Test low confidence triggers image attachment."""
        should_attach, reason = should_attach_image(
            confidence=0.82, gate_failed=False, attempt=0, doc_type=None
        )

        assert should_attach is True
        assert reason == "low_confidence:0.820"

    def test_high_confidence_no_image(self) -> None:
        """Test high confidence does not trigger image."""
        should_attach, reason = should_attach_image(
            confidence=0.95, gate_failed=False, attempt=0, doc_type=None
        )

        assert should_attach is False
        assert reason == "markdown_only"

    def test_gate_failure_triggers_image(self) -> None:
        """Test Gate Linter failure triggers image attachment."""
        should_attach, reason = should_attach_image(
            confidence=0.95,  # Even with high confidence
            gate_failed=True,
            attempt=0,
            doc_type=None,
        )

        assert should_attach is True
        assert reason == "gate_linter_failed"

    def test_retry_attempt_triggers_image(self) -> None:
        """Test retry attempt triggers image attachment."""
        should_attach, reason = should_attach_image(
            confidence=0.95, gate_failed=False, attempt=1, doc_type=None
        )

        assert should_attach is True
        assert reason == "retry_attempt:1"

    def test_fragile_type_triggers_image(self) -> None:
        """Test fragile document type triggers image attachment."""
        for fragile_type in FRAGILE_DOCUMENT_TYPES:
            should_attach, reason = should_attach_image(
                confidence=0.95, gate_failed=False, attempt=0, doc_type=fragile_type
            )

            assert should_attach is True
            assert reason == f"fragile_type:{fragile_type}"

    def test_threshold_boundary(self) -> None:
        """Test confidence threshold boundary."""
        # Exactly at threshold
        should_attach, _ = should_attach_image(
            confidence=CONFIDENCE_THRESHOLD,
            gate_failed=False,
            attempt=0,
            doc_type=None,
        )
        assert should_attach is False

        # Just below threshold
        should_attach, _ = should_attach_image(
            confidence=CONFIDENCE_THRESHOLD - 0.01,
            gate_failed=False,
            attempt=0,
            doc_type=None,
        )
        assert should_attach is True

    def test_priority_order(self) -> None:
        """Test that Gate failure has highest priority."""
        # Gate failure should override all other conditions
        should_attach, reason = should_attach_image(
            confidence=0.95,  # High confidence
            gate_failed=True,  # But Gate failed
            attempt=0,
            doc_type=None,
        )

        assert should_attach is True
        assert reason == "gate_linter_failed"


class TestErrorClassification:
    """Test error classification logic."""

    def test_syntax_error_json_decode(self) -> None:
        """Test JSON decode error classified as syntax."""
        try:
            json.loads("invalid json {")
        except json.JSONDecodeError as e:
            error_type = classify_error(e)

        assert error_type == "syntax"

    def test_syntax_error_custom(self) -> None:
        """Test SyntaxValidationError classified as syntax."""
        error = SyntaxValidationError("Invalid JSON structure")
        error_type = classify_error(error)

        assert error_type == "syntax"

    def test_semantic_error(self) -> None:
        """Test SemanticValidationError classified as semantic."""
        error = SemanticValidationError("Gate Linter validation failed")
        error_type = classify_error(error)

        assert error_type == "semantic"

    def test_http_429_error(self) -> None:
        """Test HTTP 429 error classification."""
        error = Exception("HTTP 429: Rate limit exceeded")
        error_type = classify_error(error)

        assert error_type == "http_429"

    def test_http_429_quota_variant(self) -> None:
        """Test quota error classified as HTTP 429."""
        error = Exception("Quota exceeded for this resource")
        error_type = classify_error(error)

        assert error_type == "http_429"

    def test_http_5xx_errors(self) -> None:
        """Test HTTP 5xx errors classification."""
        for code in ["500", "502", "503", "504"]:
            error = Exception(f"HTTP {code}: Server error")
            error_type = classify_error(error)

            assert error_type == "http_5xx", f"Failed for HTTP {code}"

    def test_unknown_error(self) -> None:
        """Test unknown error classification."""
        error = Exception("Some other error")
        error_type = classify_error(error)

        assert error_type == "unknown"

    def test_case_insensitive_http_detection(self) -> None:
        """Test HTTP error detection is case-insensitive."""
        error = Exception("RATE LIMIT EXCEEDED")
        error_type = classify_error(error)

        assert error_type == "http_429"


class TestModelSelection:
    """Test model selection logic."""

    def test_syntax_error_flash_retry(self) -> None:
        """Test syntax error triggers Flash retry."""
        # First retry
        model = select_model(error_type="syntax", flash_attempts=1, pro_budget_available=True)
        assert model == "flash"

        # Max retries not exhausted
        model = select_model(
            error_type="syntax",
            flash_attempts=FLASH_SYNTAX_RETRIES - 1,
            pro_budget_available=True,
        )
        assert model == "flash"

    def test_syntax_error_max_retries(self) -> None:
        """Test syntax error max retries triggers human review."""
        model = select_model(
            error_type="syntax",
            flash_attempts=FLASH_SYNTAX_RETRIES,
            pro_budget_available=True,
        )

        assert model == "human"

    def test_semantic_error_pro_escalation(self) -> None:
        """Test semantic error with budget escalates to Pro."""
        model = select_model(error_type="semantic", flash_attempts=1, pro_budget_available=True)

        assert model == "pro"

    def test_semantic_error_no_budget(self) -> None:
        """Test semantic error without budget triggers human review."""
        model = select_model(error_type="semantic", flash_attempts=1, pro_budget_available=False)

        assert model == "human"

    def test_http_429_retry_with_backoff(self) -> None:
        """Test HTTP 429 triggers Flash retry with backoff."""
        for attempts in range(1, FLASH_HTTP429_RETRIES):
            model = select_model(
                error_type="http_429",
                flash_attempts=attempts,
                pro_budget_available=True,
            )
            assert model == "flash"

        # Max retries exhausted
        model = select_model(
            error_type="http_429",
            flash_attempts=FLASH_HTTP429_RETRIES,
            pro_budget_available=True,
        )
        assert model == "human"

    def test_http_5xx_retry_with_fixed_interval(self) -> None:
        """Test HTTP 5xx triggers Flash retry with fixed interval."""
        for attempts in range(1, FLASH_HTTP5XX_RETRIES):
            model = select_model(
                error_type="http_5xx",
                flash_attempts=attempts,
                pro_budget_available=True,
            )
            assert model == "flash"

        # Max retries exhausted
        model = select_model(
            error_type="http_5xx",
            flash_attempts=FLASH_HTTP5XX_RETRIES,
            pro_budget_available=True,
        )
        assert model == "human"

    def test_unknown_error_human_review(self) -> None:
        """Test unknown error triggers human review."""
        model = select_model(error_type="unknown", flash_attempts=1, pro_budget_available=True)

        assert model == "human"

    def test_flash_attempts_zero_semantic(self) -> None:
        """Test semantic error on first attempt escalates to Pro."""
        model = select_model(error_type="semantic", flash_attempts=0, pro_budget_available=True)

        assert model == "pro"


class TestConstants:
    """Test module constants."""

    def test_confidence_threshold(self) -> None:
        """Test confidence threshold is set correctly."""
        assert CONFIDENCE_THRESHOLD == 0.85

    def test_fragile_types_defined(self) -> None:
        """Test all fragile types are defined."""
        expected_types = {
            "fax",
            "handwritten",
            "thermal_receipt",
            "carbon_copy",
            "low_res_scan",
        }
        assert expected_types == FRAGILE_DOCUMENT_TYPES

    def test_retry_limits_defined(self) -> None:
        """Test retry limits are defined."""
        assert FLASH_SYNTAX_RETRIES == 2
        assert FLASH_HTTP429_RETRIES == 5
        assert FLASH_HTTP5XX_RETRIES == 3


class TestExceptionTypes:
    """Test custom exception types."""

    def test_syntax_validation_error(self) -> None:
        """Test SyntaxValidationError can be raised."""
        with ExceptionRaised(SyntaxValidationError, "Test syntax error"):
            raise SyntaxValidationError("Test syntax error")

    def test_semantic_validation_error(self) -> None:
        """Test SemanticValidationError can be raised."""
        with ExceptionRaised(SemanticValidationError, "Test semantic error"):
            raise SemanticValidationError("Test semantic error")

    def test_pro_budget_exhausted_error(self) -> None:
        """Test ProBudgetExhaustedError can be raised."""
        with ExceptionRaised(ProBudgetExhaustedError, "Budget exhausted"):
            raise ProBudgetExhaustedError("Budget exhausted")


# Helper context manager for exception testing
class ExceptionRaised:
    """Context manager to test exception raising."""

    def __init__(self, exc_type: type, message: str) -> None:
        self.exc_type = exc_type
        self.message = message

    def __enter__(self) -> None:
        pass

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: object) -> bool:
        if exc_type is None:
            raise AssertionError(f"Expected {self.exc_type.__name__} to be raised")
        if not issubclass(exc_type, self.exc_type):
            return False
        if self.message not in str(exc_val):
            raise AssertionError(f"Expected message '{self.message}' not found in '{exc_val}'")
        return True
