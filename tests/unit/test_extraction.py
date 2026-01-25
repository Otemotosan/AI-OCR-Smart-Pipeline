"""Unit tests for Gemini extraction logic."""

from __future__ import annotations

import base64
import json

from src.core.extraction import (
    CONFIDENCE_THRESHOLD,
    FLASH_HTTP5XX_RETRIES,
    FLASH_HTTP429_RETRIES,
    FLASH_SYNTAX_RETRIES,
    FRAGILE_DOCUMENT_TYPES,
    ExtractionAttempt,
    ExtractionResult,
    GeminiInput,
    ProBudgetExhaustedError,
    SemanticValidationError,
    SyntaxValidationError,
    classify_error,
    extract_with_retry,
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


# ============================================================
# Extraction Result Tests
# ============================================================


class TestExtractionDataclasses:
    """Test ExtractionAttempt and ExtractionResult dataclasses."""

    def test_extraction_attempt_creation(self) -> None:
        """Test creating ExtractionAttempt."""

        attempt = ExtractionAttempt(
            model="flash",
            prompt_tokens=2000,
            output_tokens=100,
            cost_usd=0.0001,
            error=None,
            data={"management_id": "INV-001"},
        )

        assert attempt.model == "flash"
        assert attempt.prompt_tokens == 2000
        assert attempt.output_tokens == 100
        assert attempt.cost_usd == 0.0001
        assert attempt.error is None
        assert attempt.data == {"management_id": "INV-001"}

    def test_extraction_attempt_with_error(self) -> None:
        """Test ExtractionAttempt with error."""

        attempt = ExtractionAttempt(
            model="flash",
            prompt_tokens=2000,
            output_tokens=0,
            cost_usd=0.0,
            error="Syntax error: Invalid JSON",
            data=None,
        )

        assert attempt.model == "flash"
        assert attempt.error == "Syntax error: Invalid JSON"
        assert attempt.data is None

    def test_extraction_result_success(self) -> None:
        """Test ExtractionResult for successful extraction."""
        from unittest.mock import MagicMock

        mock_schema = MagicMock()
        attempt1 = ExtractionAttempt(
            model="flash",
            prompt_tokens=2000,
            output_tokens=100,
            cost_usd=0.0001,
            data={"management_id": "INV-001"},
        )

        result = ExtractionResult(
            schema=mock_schema,
            status="SUCCESS",
            attempts=[attempt1],
            final_model="flash",
            total_cost=0.0001,
            reason=None,
        )

        assert result.schema == mock_schema
        assert result.status == "SUCCESS"
        assert len(result.attempts) == 1
        assert result.final_model == "flash"
        assert result.total_cost == 0.0001
        assert result.reason is None

    def test_extraction_result_failed(self) -> None:
        """Test ExtractionResult for failed extraction."""

        attempt1 = ExtractionAttempt(
            model="flash",
            prompt_tokens=2000,
            output_tokens=0,
            cost_usd=0.0,
            error="Gate Linter failed",
            data=None,
        )
        attempt2 = ExtractionAttempt(
            model="pro",
            prompt_tokens=10000,
            output_tokens=0,
            cost_usd=0.001,
            error="Pro also failed",
            data=None,
        )

        result = ExtractionResult(
            schema=None,
            status="FAILED",
            attempts=[attempt1, attempt2],
            final_model="pro",
            total_cost=0.001,
            reason="Pro failed Gate Linter",
        )

        assert result.schema is None
        assert result.status == "FAILED"
        assert len(result.attempts) == 2
        assert result.final_model == "pro"
        assert result.total_cost == 0.001
        assert result.reason == "Pro failed Gate Linter"


# ============================================================
# extract_with_retry Tests
# ============================================================


class TestExtractWithRetry:
    """Test extract_with_retry function with various scenarios."""

    def test_successful_first_attempt(self) -> None:
        """Test successful extraction on first Flash attempt."""
        from unittest.mock import MagicMock

        from core.extraction import GeminiInput, extract_with_retry

        # Mock dependencies
        gemini_input = GeminiInput(markdown="# Invoice...", include_image=False)
        schema_class = MagicMock()
        schema_class.__name__ = "DeliveryNoteV2"

        # Mock GeminiClient response
        mock_response = MagicMock()
        mock_response.data = {"management_id": "INV-001", "company_name": "Acme Inc"}
        mock_response.input_tokens = 2000
        mock_response.output_tokens = 100
        mock_response.cost_usd = 0.0001

        gemini_client = MagicMock()
        gemini_client.call_flash_v2.return_value = mock_response

        # Mock BudgetManager
        budget_manager = MagicMock()
        budget_manager.check_pro_budget.return_value = True

        # Mock GateLinter
        mock_gate_result = MagicMock()
        mock_gate_result.passed = True
        gate_linter = MagicMock()
        gate_linter.validate.return_value = mock_gate_result

        # Mock schema validation
        mock_schema_instance = MagicMock()
        schema_class.return_value = mock_schema_instance

        # Execute
        result = extract_with_retry(
            gemini_input, schema_class, gemini_client, budget_manager, gate_linter
        )

        # Verify
        assert result.status == "SUCCESS"
        assert result.schema == mock_schema_instance
        assert result.final_model == "flash"
        assert len(result.attempts) == 1
        assert result.attempts[0].model == "flash"
        assert result.attempts[0].cost_usd == 0.0001
        assert result.total_cost == 0.0001

    def test_gate_linter_failure_then_pro_success(self) -> None:
        """Test Flash fails Gate Linter, escalates to Pro successfully."""
        from unittest.mock import MagicMock

        from core.extraction import GeminiInput, extract_with_retry

        gemini_input = GeminiInput(markdown="# Invoice...", include_image=False)
        schema_class = MagicMock()
        schema_class.__name__ = "DeliveryNoteV2"

        # Flash response (Gate Linter will fail)
        flash_response = MagicMock()
        flash_response.data = {"management_id": ""}  # Empty management_id (Gate fails)
        flash_response.input_tokens = 2000
        flash_response.output_tokens = 100
        flash_response.cost_usd = 0.0001

        # Pro response (succeeds)
        pro_response = MagicMock()
        pro_response.data = {"management_id": "INV-001", "company_name": "Acme Inc"}
        pro_response.input_tokens = 10000
        pro_response.output_tokens = 200
        pro_response.cost_usd = 0.001

        gemini_client = MagicMock()
        gemini_client.call_flash_v2.return_value = flash_response
        gemini_client.call_pro_v2.return_value = pro_response

        budget_manager = MagicMock()
        budget_manager.check_pro_budget.return_value = True

        # Gate Linter: fail Flash, pass Pro
        gate_linter = MagicMock()
        gate_linter.validate.side_effect = [
            MagicMock(passed=False, errors=["management_id is empty"]),  # Flash
            MagicMock(passed=True),  # Pro
        ]

        mock_schema_instance = MagicMock()
        schema_class.return_value = mock_schema_instance

        # Execute
        result = extract_with_retry(
            gemini_input, schema_class, gemini_client, budget_manager, gate_linter
        )

        # Verify
        assert result.status == "SUCCESS"
        assert result.final_model == "pro"
        assert len(result.attempts) == 2
        assert result.attempts[0].model == "flash"
        assert result.attempts[0].error is not None
        assert result.attempts[1].model == "pro"
        budget_manager.increment_pro_usage.assert_called_once()

    def test_pro_budget_exhausted(self) -> None:
        """Test Pro escalation blocked by budget limit."""
        from unittest.mock import MagicMock

        from core.extraction import GeminiInput, extract_with_retry

        gemini_input = GeminiInput(markdown="# Invoice...", include_image=False)
        schema_class = MagicMock()
        schema_class.__name__ = "DeliveryNoteV2"

        # Flash response (fails schema validation to trigger Pro escalation)
        flash_response = MagicMock()
        flash_response.data = {"management_id": "INV-001", "company_name": "Acme Inc"}
        flash_response.input_tokens = 2000
        flash_response.output_tokens = 100
        flash_response.cost_usd = 0.0001

        gemini_client = MagicMock()
        gemini_client.call_flash_v2.return_value = flash_response

        # Budget exhausted (returns False always)
        budget_manager = MagicMock()
        budget_manager.check_pro_budget.return_value = False

        # Gate passes, but schema validation fails (to trigger Pro escalation)
        gate_linter = MagicMock()
        gate_linter.validate.return_value = MagicMock(passed=True)

        # Schema validation fails to trigger Pro escalation
        schema_class.side_effect = Exception("Schema validation error")

        # Execute
        result = extract_with_retry(
            gemini_input, schema_class, gemini_client, budget_manager, gate_linter
        )

        # Verify
        assert result.status == "FAILED"
        assert result.reason == "Pro budget exhausted"
        assert result.final_model == "flash"
        gemini_client.call_pro_v2.assert_not_called()

    def test_syntax_error_retry_then_success(self) -> None:
        """Test syntax error on first attempt, success on retry."""
        from unittest.mock import MagicMock

        from src.core.extraction import GeminiInput, extract_with_retry
        from src.core.gemini import SyntaxValidationError

        gemini_input = GeminiInput(markdown="# Invoice...", include_image=False)
        schema_class = MagicMock()
        schema_class.__name__ = "DeliveryNoteV2"

        # Second attempt succeeds
        success_response = MagicMock()
        success_response.data = {"management_id": "INV-001", "company_name": "Acme Inc"}
        success_response.input_tokens = 2000
        success_response.output_tokens = 100
        success_response.cost_usd = 0.0001

        gemini_client = MagicMock()
        gemini_client.call_flash_v2.side_effect = [
            SyntaxValidationError("Invalid JSON"),  # First attempt
            success_response,  # Second attempt
        ]

        budget_manager = MagicMock()
        budget_manager.check_pro_budget.return_value = True

        gate_linter = MagicMock()
        gate_linter.validate.return_value = MagicMock(passed=True)

        mock_schema_instance = MagicMock()
        schema_class.return_value = mock_schema_instance

        # Execute
        result = extract_with_retry(
            gemini_input, schema_class, gemini_client, budget_manager, gate_linter
        )

        # Verify
        assert result.status == "SUCCESS"
        assert len(result.attempts) == 2
        assert result.attempts[0].error is not None
        assert "Syntax error" in result.attempts[0].error
        assert gemini_client.call_flash_v2.call_count == 2

    def test_all_retries_exhausted(self) -> None:
        """Test all Flash retries exhausted, no Pro escalation."""
        from unittest.mock import MagicMock

        from src.core.extraction import FLASH_SYNTAX_RETRIES, GeminiInput, extract_with_retry
        from src.core.gemini import SyntaxValidationError

        gemini_input = GeminiInput(markdown="# Invoice...", include_image=False)
        schema_class = MagicMock()
        schema_class.__name__ = "DeliveryNoteV2"

        gemini_client = MagicMock()
        # FLASH_SYNTAX_RETRIES = 2, so we get 2 attempts (initial fails immediately, then 1 retry)
        gemini_client.call_flash_v2.side_effect = [
            SyntaxValidationError("Invalid JSON 1"),
            SyntaxValidationError("Invalid JSON 2"),
        ]

        budget_manager = MagicMock()
        gate_linter = MagicMock()

        # Execute
        result = extract_with_retry(
            gemini_input, schema_class, gemini_client, budget_manager, gate_linter
        )

        # Verify
        assert result.status == "FAILED"
        assert "Syntax errors exhausted" in result.reason
        assert len(result.attempts) == FLASH_SYNTAX_RETRIES  # Should be 2
        gemini_client.call_pro_v2.assert_not_called()

    def test_flash_unexpected_error(self) -> None:
        """Test Flash call with unexpected error."""
        from unittest.mock import MagicMock

        gemini_input = GeminiInput(markdown="# Test Doc")
        schema_class = MagicMock()
        schema_class.__name__ = "TestSchema"

        # Mock GeminiClient to raise unexpected error
        gemini_client = MagicMock()
        gemini_client.call_flash_v2.side_effect = RuntimeError("Database connection failed")

        # Mock BudgetManager
        budget_manager = MagicMock()
        budget_manager.check_pro_budget.return_value = True

        # Mock GateLinter
        gate_linter = MagicMock()

        # Call extract_with_retry
        result = extract_with_retry(
            gemini_input, schema_class, gemini_client, budget_manager, gate_linter
        )

        # Verify
        assert result.status == "FAILED"
        assert "Unexpected error" in result.reason
        assert len(result.attempts) == 1
        assert "Database connection failed" in result.attempts[0].error
        gemini_client.call_pro_v2.assert_not_called()

    def test_pro_gate_linter_failure(self) -> None:
        """Test Pro escalation where Pro also fails Gate Linter."""
        from unittest.mock import MagicMock

        gemini_input = GeminiInput(markdown="# Test Doc")
        schema_class = MagicMock()
        schema_class.__name__ = "TestSchema"

        # Mock GeminiClient - Flash fails Gate, Pro also fails Gate
        gemini_client = MagicMock()
        flash_response = MagicMock()
        flash_response.data = {"field": "invalid"}
        flash_response.input_tokens = 2000
        flash_response.output_tokens = 100
        flash_response.cost_usd = 0.0001
        gemini_client.call_flash_v2.return_value = flash_response

        pro_response = MagicMock()
        pro_response.data = {"field": "still_invalid"}
        pro_response.input_tokens = 10000
        pro_response.output_tokens = 200
        pro_response.cost_usd = 0.001
        gemini_client.call_pro_v2.return_value = pro_response

        # Mock BudgetManager - has budget
        budget_manager = MagicMock()
        budget_manager.check_pro_budget.return_value = True

        # Mock GateLinter - both fail
        gate_linter = MagicMock()
        flash_gate_result = MagicMock()
        flash_gate_result.passed = False
        flash_gate_result.errors = ["Flash: Missing management_id"]

        pro_gate_result = MagicMock()
        pro_gate_result.passed = False
        pro_gate_result.errors = ["Pro: Missing management_id"]

        gate_linter.validate.side_effect = [flash_gate_result, pro_gate_result]

        # Call extract_with_retry
        result = extract_with_retry(
            gemini_input, schema_class, gemini_client, budget_manager, gate_linter
        )

        # Verify
        assert result.status == "FAILED"
        assert "Gate Linter failed" in result.attempts[-1].error
        assert len(result.attempts) == 2  # Flash + Pro
        assert result.final_model == "pro"
        budget_manager.increment_pro_usage.assert_called_once()

    def test_pro_schema_validation_failure(self) -> None:
        """Test Pro escalation where Pro passes Gate but fails Pydantic schema."""
        from unittest.mock import MagicMock

        gemini_input = GeminiInput(markdown="# Test Doc")

        # Schema that raises exception on invalid data
        schema_class = MagicMock()
        schema_class.__name__ = "TestSchema"
        schema_class.side_effect = Exception("Schema validation: date format invalid")

        # Mock GeminiClient - Flash fails Gate, Pro passes Gate
        gemini_client = MagicMock()
        flash_response = MagicMock()
        flash_response.data = {"field": "invalid"}
        flash_response.input_tokens = 2000
        flash_response.output_tokens = 100
        flash_response.cost_usd = 0.0001
        gemini_client.call_flash_v2.return_value = flash_response

        pro_response = MagicMock()
        pro_response.data = {"management_id": "INV-001", "date": "bad_date"}
        pro_response.input_tokens = 10000
        pro_response.output_tokens = 200
        pro_response.cost_usd = 0.001
        gemini_client.call_pro_v2.return_value = pro_response

        # Mock BudgetManager
        budget_manager = MagicMock()
        budget_manager.check_pro_budget.return_value = True

        # Mock GateLinter - Flash fails, Pro passes
        gate_linter = MagicMock()
        flash_gate_result = MagicMock()
        flash_gate_result.passed = False
        flash_gate_result.errors = ["Flash: Missing management_id"]

        pro_gate_result = MagicMock()
        pro_gate_result.passed = True

        gate_linter.validate.side_effect = [flash_gate_result, pro_gate_result]

        # Call extract_with_retry
        result = extract_with_retry(
            gemini_input, schema_class, gemini_client, budget_manager, gate_linter
        )

        # Verify
        assert result.status == "FAILED"
        assert "Pro schema validation failed" in result.reason
        assert "date format invalid" in result.reason
        assert len(result.attempts) == 2  # Flash + Pro
        assert result.final_model == "pro"

    def test_pro_syntax_error(self) -> None:
        """Test Pro escalation where Pro returns invalid JSON."""
        from unittest.mock import MagicMock

        from core.gemini import SyntaxValidationError

        gemini_input = GeminiInput(markdown="# Test Doc")
        schema_class = MagicMock()
        schema_class.__name__ = "TestSchema"

        # Mock GeminiClient - Flash fails Gate, Pro has syntax error
        gemini_client = MagicMock()
        flash_response = MagicMock()
        flash_response.data = {"field": "invalid"}
        flash_response.input_tokens = 2000
        flash_response.output_tokens = 100
        flash_response.cost_usd = 0.0001
        gemini_client.call_flash_v2.return_value = flash_response
        gemini_client.call_pro_v2.side_effect = SyntaxValidationError("Invalid JSON from Pro")

        # Mock BudgetManager
        budget_manager = MagicMock()
        budget_manager.check_pro_budget.return_value = True

        # Mock GateLinter - Flash fails
        gate_linter = MagicMock()
        flash_gate_result = MagicMock()
        flash_gate_result.passed = False
        flash_gate_result.errors = ["Flash: Missing management_id"]
        gate_linter.validate.return_value = flash_gate_result

        # Call extract_with_retry
        result = extract_with_retry(
            gemini_input, schema_class, gemini_client, budget_manager, gate_linter
        )

        # Verify
        assert result.status == "FAILED"
        assert "Pro syntax error" in result.reason
        assert len(result.attempts) == 2  # Flash + Pro attempt
        assert result.final_model == "pro"

    def test_pro_unexpected_error(self) -> None:
        """Test Pro escalation where Pro has unexpected error."""
        from unittest.mock import MagicMock

        gemini_input = GeminiInput(markdown="# Test Doc")
        schema_class = MagicMock()
        schema_class.__name__ = "TestSchema"

        # Mock GeminiClient - Flash fails Gate, Pro has unexpected error
        gemini_client = MagicMock()
        flash_response = MagicMock()
        flash_response.data = {"field": "invalid"}
        flash_response.input_tokens = 2000
        flash_response.output_tokens = 100
        flash_response.cost_usd = 0.0001
        gemini_client.call_flash_v2.return_value = flash_response
        gemini_client.call_pro_v2.side_effect = RuntimeError("Pro API timeout")

        # Mock BudgetManager
        budget_manager = MagicMock()
        budget_manager.check_pro_budget.return_value = True

        # Mock GateLinter - Flash fails
        gate_linter = MagicMock()
        flash_gate_result = MagicMock()
        flash_gate_result.passed = False
        flash_gate_result.errors = ["Flash: Missing management_id"]
        gate_linter.validate.return_value = flash_gate_result

        # Call extract_with_retry
        result = extract_with_retry(
            gemini_input, schema_class, gemini_client, budget_manager, gate_linter
        )

        # Verify
        assert result.status == "FAILED"
        assert "Pro unexpected error" in result.reason
        assert "Pro API timeout" in result.reason
        assert len(result.attempts) == 2  # Flash + Pro attempt
        assert result.final_model == "pro"

    def test_pro_with_image_attachment(self) -> None:
        """Test Pro escalation with image attachment."""
        from unittest.mock import MagicMock

        gemini_input = GeminiInput(
            markdown="# Test Doc",
            include_image=True,
            image_base64=base64.b64encode(b"fake_image_data").decode("utf-8"),
            reason="low_confidence:0.75",
        )

        # Mock schema class
        schema_class = MagicMock()
        schema_class.__name__ = "TestSchema"
        validated_schema = MagicMock()
        schema_class.return_value = validated_schema

        # Mock GeminiClient - Flash fails Gate, Pro succeeds
        gemini_client = MagicMock()
        flash_response = MagicMock()
        flash_response.data = {"field": "invalid"}
        flash_response.input_tokens = 10000  # With image
        flash_response.output_tokens = 100
        flash_response.cost_usd = 0.001
        gemini_client.call_flash_v2.return_value = flash_response

        pro_response = MagicMock()
        pro_response.data = {"management_id": "INV-001"}
        pro_response.input_tokens = 10000  # With image
        pro_response.output_tokens = 200
        pro_response.cost_usd = 0.01
        gemini_client.call_pro_v2.return_value = pro_response

        # Mock BudgetManager
        budget_manager = MagicMock()
        budget_manager.check_pro_budget.return_value = True

        # Mock GateLinter - Flash fails, Pro passes
        gate_linter = MagicMock()
        flash_gate_result = MagicMock()
        flash_gate_result.passed = False
        flash_gate_result.errors = ["Flash: Missing management_id"]

        pro_gate_result = MagicMock()
        pro_gate_result.passed = True

        gate_linter.validate.side_effect = [flash_gate_result, pro_gate_result]

        # Call extract_with_retry
        result = extract_with_retry(
            gemini_input, schema_class, gemini_client, budget_manager, gate_linter
        )

        # Verify
        assert result.status == "SUCCESS"
        assert result.schema == validated_schema
        assert len(result.attempts) == 2  # Flash + Pro
        assert result.final_model == "pro"

        # Verify Pro was called with image bytes
        # Verify Pro was called with image bytes (2nd positional arg)
        gemini_client.call_pro_v2.assert_called_once()
        call_args = gemini_client.call_pro_v2.call_args
        assert call_args[0][1] == b"fake_image_data"
