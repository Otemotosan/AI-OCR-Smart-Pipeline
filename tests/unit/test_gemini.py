"""Unit tests for Gemini API client."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.core.gemini import (
    FLASH_INPUT_COST,
    FLASH_MODEL,
    FLASH_OUTPUT_COST,
    GeminiClient,
    GeminiResponse,
    MARKDOWN_ONLY_TOKENS,
    MARKDOWN_WITH_IMAGE_TOKENS,
    PRO_INPUT_COST,
    PRO_MODEL,
    PRO_OUTPUT_COST,
    ProBudgetExhaustedError,
    SemanticValidationError,
    SyntaxValidationError,
)

# ============================================================
# Data Class Tests
# ============================================================


class TestGeminiResponse:
    """Test GeminiResponse dataclass."""

    def test_create_response(self) -> None:
        """Test creating GeminiResponse."""
        response = GeminiResponse(
            data={"management_id": "INV-001"},
            raw_text='{"management_id": "INV-001"}',
            model_used="flash",
            input_tokens=2000,
            output_tokens=100,
            cost_usd=0.0001,
        )

        assert response.data == {"management_id": "INV-001"}
        assert response.raw_text == '{"management_id": "INV-001"}'
        assert response.model_used == "flash"
        assert response.input_tokens == 2000
        assert response.output_tokens == 100
        assert response.cost_usd == 0.0001


# ============================================================
# Client Tests
# ============================================================


class TestGeminiClient:
    """Test GeminiClient initialization and properties."""

    def test_initialize_client(self) -> None:
        """Test client initialization."""
        client = GeminiClient(api_key="test-api-key")

        assert client.api_key == "test-api-key"
        assert client._genai is None  # Lazy loading not triggered

    def test_genai_lazy_loading(self) -> None:
        """Test that genai property lazy loads the module."""
        client = GeminiClient(api_key="test-api-key")

        # Initially None
        assert client._genai is None

        # Mock the import within the property
        mock_genai = MagicMock()
        with patch("builtins.__import__") as mock_import:
            # Configure mock to return mock_genai for google.generativeai
            def side_effect(name, *args, **kwargs):
                if "google.generativeai" in name:
                    return mock_genai
                return MagicMock()

            mock_import.side_effect = side_effect

            # Access property to trigger lazy loading
            result = client.genai

        # After first access, should be cached
        assert client._genai is not None
        # Verify the result has the expected attributes from google.generativeai
        assert hasattr(result, "configure")
        assert hasattr(result, "GenerativeModel")


# ============================================================
# Flash Model Tests
# ============================================================


class TestFlashModelCalls:
    """Test Flash model API calls."""

    def test_call_flash_markdown_only(self) -> None:
        """Test Flash call with markdown only (no image)."""
        client = GeminiClient(api_key="test-key")

        # Mock the genai module and model
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"management_id": "INV-001", "company_name": "Acme Inc"}'
        mock_model.generate_content.return_value = mock_response

        mock_genai = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        # Set _genai directly to avoid lazy loading
        client._genai = mock_genai

        response = client.call_flash_v2(
            prompt="Extract data from: # Invoice...",
            image=None,
        )

        # Verify response
        assert response.data == {"management_id": "INV-001", "company_name": "Acme Inc"}
        assert response.model_used == FLASH_MODEL
        assert response.input_tokens == MARKDOWN_ONLY_TOKENS
        assert response.output_tokens > 0
        assert response.cost_usd > 0

        # Verify model was called correctly
        mock_genai.GenerativeModel.assert_called_once_with(FLASH_MODEL)
        mock_model.generate_content.assert_called_once()

    def test_call_flash_with_image(self) -> None:
        """Test Flash call with markdown + image."""
        client = GeminiClient(api_key="test-key")

        # Mock the genai module and model
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"management_id": "INV-001"}'
        mock_model.generate_content.return_value = mock_response

        mock_genai = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        # Set _genai directly to avoid lazy loading
        client._genai = mock_genai

        response = client.call_flash_v2(
            prompt="Extract data from: # Invoice...",
            image=b"fake_image_bytes",
        )

        # Verify response uses image token count
        assert response.input_tokens == MARKDOWN_WITH_IMAGE_TOKENS
        assert response.cost_usd > 0


# ============================================================
# Pro Model Tests
# ============================================================


class TestProModelCalls:
    """Test Pro model API calls."""

    def test_call_pro_markdown_only(self) -> None:
        """Test Pro call with markdown only."""
        client = GeminiClient(api_key="test-key")

        # Mock the genai module and model
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"management_id": "INV-001", "company_name": "Acme Inc"}'
        mock_model.generate_content.return_value = mock_response

        mock_genai = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        # Set _genai directly to avoid lazy loading
        client._genai = mock_genai

        response = client.call_pro_v2(
            prompt="Extract data from: # Invoice...",
            image=None,
        )

        # Verify response
        assert response.data == {"management_id": "INV-001", "company_name": "Acme Inc"}
        assert response.model_used == PRO_MODEL
        assert response.input_tokens == MARKDOWN_ONLY_TOKENS
        assert response.cost_usd > 0

        # Verify model was called correctly
        mock_genai.GenerativeModel.assert_called_once_with(PRO_MODEL)

    def test_call_pro_with_image(self) -> None:
        """Test Pro call with markdown + image."""
        client = GeminiClient(api_key="test-key")

        # Mock the genai module and model
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"management_id": "INV-001"}'
        mock_model.generate_content.return_value = mock_response

        mock_genai = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        # Set _genai directly to avoid lazy loading
        client._genai = mock_genai

        response = client.call_pro_v2(
            prompt="Extract data from: # Invoice...",
            image=b"fake_image_bytes",
        )

        # Verify response uses image token count
        assert response.input_tokens == MARKDOWN_WITH_IMAGE_TOKENS
        assert response.cost_usd > 0


# ============================================================
# JSON Parsing Tests
# ============================================================


class TestJSONParsing:
    """Test JSON response parsing."""

    def test_parse_clean_json(self) -> None:
        """Test parsing clean JSON response."""
        client = GeminiClient(api_key="test-key")
        json_str = '{"management_id": "INV-001", "company_name": "Acme Inc"}'

        result = client.parse_json_response(json_str)

        assert result == {"management_id": "INV-001", "company_name": "Acme Inc"}

    def test_parse_json_with_markdown_fences(self) -> None:
        """Test parsing JSON with markdown code fences."""
        client = GeminiClient(api_key="test-key")
        json_str = '```json\n{"management_id": "INV-001"}\n```'

        result = client.parse_json_response(json_str)

        assert result == {"management_id": "INV-001"}

    def test_parse_json_with_backticks_only(self) -> None:
        """Test parsing JSON with just backticks (no json language tag)."""
        client = GeminiClient(api_key="test-key")
        json_str = '```\n{"management_id": "INV-001"}\n```'

        result = client.parse_json_response(json_str)

        assert result == {"management_id": "INV-001"}

    def test_parse_json_with_whitespace(self) -> None:
        """Test parsing JSON with leading/trailing whitespace."""
        client = GeminiClient(api_key="test-key")
        json_str = '  \n  {"management_id": "INV-001"}  \n  '

        result = client.parse_json_response(json_str)

        assert result == {"management_id": "INV-001"}

    def test_parse_invalid_json_raises_error(self) -> None:
        """Test that invalid JSON raises JSONDecodeError."""
        client = GeminiClient(api_key="test-key")
        invalid_json = '{"management_id": "INV-001"'  # Missing closing brace

        with pytest.raises(json.JSONDecodeError):
            client.parse_json_response(invalid_json)


# ============================================================
# Cost Calculation Tests
# ============================================================


class TestCostCalculation:
    """Test cost estimation."""

    def test_calculate_flash_cost(self) -> None:
        """Test Flash model cost calculation."""
        client = GeminiClient(api_key="test-key")

        # 2000 input tokens, 100 output tokens
        cost = client._calculate_cost(
            input_tokens=2000,
            output_tokens=100,
            is_pro=False,
        )

        expected_input = (2000 / 1000) * FLASH_INPUT_COST
        expected_output = (100 / 1000) * FLASH_OUTPUT_COST
        expected_total = expected_input + expected_output

        assert cost == pytest.approx(expected_total)

    def test_calculate_pro_cost(self) -> None:
        """Test Pro model cost calculation."""
        client = GeminiClient(api_key="test-key")

        # 10000 input tokens, 200 output tokens
        cost = client._calculate_cost(
            input_tokens=10000,
            output_tokens=200,
            is_pro=True,
        )

        expected_input = (10000 / 1000) * PRO_INPUT_COST
        expected_output = (200 / 1000) * PRO_OUTPUT_COST
        expected_total = expected_input + expected_output

        assert cost == pytest.approx(expected_total)

    def test_pro_is_more_expensive_than_flash(self) -> None:
        """Test that Pro costs more than Flash for same tokens."""
        client = GeminiClient(api_key="test-key")

        flash_cost = client._calculate_cost(2000, 100, is_pro=False)
        pro_cost = client._calculate_cost(2000, 100, is_pro=True)

        assert pro_cost > flash_cost


# ============================================================
# Error Handling Tests
# ============================================================


class TestErrorHandling:
    """Test error handling and retry logic."""

    def test_syntax_error_on_invalid_json(self) -> None:
        """Test that invalid JSON from Flash raises SyntaxValidationError."""
        client = GeminiClient(api_key="test-key")

        # Mock the genai module to return invalid JSON
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "This is not JSON at all"
        mock_model.generate_content.return_value = mock_response

        mock_genai = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        # Set _genai directly to avoid lazy loading
        client._genai = mock_genai

        with pytest.raises(SyntaxValidationError) as exc_info:
            client.call_flash_v2(prompt="Extract...")

        assert "Invalid JSON from Flash" in str(exc_info.value)

    def test_syntax_error_on_invalid_json_pro(self) -> None:
        """Test that invalid JSON from Pro raises SyntaxValidationError."""
        client = GeminiClient(api_key="test-key")

        # Mock the genai module to return invalid JSON
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Not JSON"
        mock_model.generate_content.return_value = mock_response

        mock_genai = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model

        # Set _genai directly to avoid lazy loading
        client._genai = mock_genai

        with pytest.raises(SyntaxValidationError) as exc_info:
            client.call_pro_v2(prompt="Extract...")

        assert "Invalid JSON from Pro" in str(exc_info.value)


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Test module constants."""

    def test_model_names(self) -> None:
        """Test model name constants."""
        assert FLASH_MODEL == "gemini-2.5-flash"
        assert PRO_MODEL == "gemini-2.5-pro"

    def test_token_estimates(self) -> None:
        """Test token estimate constants."""
        assert MARKDOWN_ONLY_TOKENS == 2000
        assert MARKDOWN_WITH_IMAGE_TOKENS == 10000

    def test_cost_constants(self) -> None:
        """Test cost per 1K tokens."""
        assert FLASH_INPUT_COST == 0.000125
        assert FLASH_OUTPUT_COST == 0.000375
        assert PRO_INPUT_COST == 0.00125
        assert PRO_OUTPUT_COST == 0.005

    def test_pro_more_expensive_than_flash(self) -> None:
        """Test that Pro costs are higher than Flash."""
        assert PRO_INPUT_COST > FLASH_INPUT_COST
        assert PRO_OUTPUT_COST > FLASH_OUTPUT_COST


# ============================================================
# Exception Tests
# ============================================================


class TestExceptionTypes:
    """Test custom exception types."""

    def test_syntax_validation_error(self) -> None:
        """Test SyntaxValidationError can be raised."""
        with pytest.raises(SyntaxValidationError):
            raise SyntaxValidationError("Test syntax error")

    def test_semantic_validation_error(self) -> None:
        """Test SemanticValidationError can be raised."""
        with pytest.raises(SemanticValidationError):
            raise SemanticValidationError("Test semantic error")

    def test_pro_budget_exhausted_error(self) -> None:
        """Test ProBudgetExhaustedError can be raised."""
        with pytest.raises(ProBudgetExhaustedError):
            raise ProBudgetExhaustedError("Budget exhausted")
