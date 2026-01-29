"""Unit tests for Gemini prompt builders."""

from __future__ import annotations

import json

from core.prompts import (
    MARKDOWN_ONLY_SYSTEM_PROMPT,
    MULTIMODAL_SYSTEM_PROMPT,
    build_correction_prompt,
    build_extraction_prompt,
    build_initial_prompt,
)
from core.schemas import DeliveryNoteV2


class TestSystemPrompts:
    """Test system prompt constants."""

    def test_multimodal_prompt_exists(self) -> None:
        """Test multimodal system prompt is defined."""
        assert MULTIMODAL_SYSTEM_PROMPT
        assert len(MULTIMODAL_SYSTEM_PROMPT) > 100

    def test_multimodal_prompt_contains_priority_rules(self) -> None:
        """Test multimodal prompt contains priority rules."""
        assert "Priority Rules" in MULTIMODAL_SYSTEM_PROMPT
        assert "STRUCTURE" in MULTIMODAL_SYSTEM_PROMPT
        assert "TEXT DETAILS" in MULTIMODAL_SYSTEM_PROMPT
        assert "CONFLICT RESOLUTION" in MULTIMODAL_SYSTEM_PROMPT

    def test_markdown_only_prompt_exists(self) -> None:
        """Test markdown-only system prompt is defined."""
        assert MARKDOWN_ONLY_SYSTEM_PROMPT
        assert len(MARKDOWN_ONLY_SYSTEM_PROMPT) > 50

    def test_markdown_only_prompt_mentions_structure(self) -> None:
        """Test markdown-only prompt explains structural preservation."""
        assert "Structural Markdown" in MARKDOWN_ONLY_SYSTEM_PROMPT
        assert "Table structures" in MARKDOWN_ONLY_SYSTEM_PROMPT


class TestBuildExtractionPrompt:
    """Test build_extraction_prompt function."""

    def test_markdown_only_mode(self) -> None:
        """Test prompt generation without image for schema-specific prompt."""
        from dataclasses import dataclass

        @dataclass
        class GeminiInput:
            markdown: str
            include_image: bool = False

        gemini_input = GeminiInput(markdown="# Test Document\n\nContent here.")

        prompt = build_extraction_prompt(gemini_input, DeliveryNoteV2)

        # DeliveryNoteV2 uses schema-specific prompt (DELIVERY_NOTE_SYSTEM_PROMPT)
        assert "納品書 (Delivery Notes)" in prompt
        # Should include schema description
        assert "DeliveryNoteV2" in prompt
        # Should include markdown content
        assert "# Test Document" in prompt
        assert "Content here." in prompt
        # Should include output instruction
        assert "Return ONLY valid JSON" in prompt

    def test_multimodal_mode(self) -> None:
        """Test prompt generation with image for schema-specific prompt."""
        from dataclasses import dataclass

        @dataclass
        class GeminiInput:
            markdown: str
            include_image: bool = True

        gemini_input = GeminiInput(markdown="# Test Document", include_image=True)

        prompt = build_extraction_prompt(gemini_input, DeliveryNoteV2)

        # DeliveryNoteV2 uses schema-specific prompt regardless of include_image
        # The schema-specific prompt is used for better extraction accuracy
        assert "納品書 (Delivery Notes)" in prompt
        assert "金額フィールド" in prompt or "Amounts" in prompt
        assert "management_id" in prompt

    def test_includes_schema_description(self) -> None:
        """Test that prompt includes schema field descriptions."""
        from dataclasses import dataclass

        @dataclass
        class GeminiInput:
            markdown: str
            include_image: bool = False

        gemini_input = GeminiInput(markdown="# Test")

        prompt = build_extraction_prompt(gemini_input, DeliveryNoteV2)

        # Should include schema fields
        assert "management_id" in prompt
        assert "company_name" in prompt
        assert "issue_date" in prompt
        assert "delivery_date" in prompt

    def test_retry_context_included(self) -> None:
        """Test prompt includes previous attempts and errors on retry."""
        from dataclasses import dataclass

        @dataclass
        class GeminiInput:
            markdown: str
            include_image: bool = False

        gemini_input = GeminiInput(markdown="# Test")

        previous_attempts = [
            {"management_id": "", "company_name": "Test Corp", "issue_date": "2025-01-13"}
        ]
        errors = ["management_id: Required field is empty"]

        prompt = build_extraction_prompt(
            gemini_input, DeliveryNoteV2, previous_attempts=previous_attempts, errors=errors
        )

        # Should include previous attempt section
        assert "Previous Attempt (FAILED)" in prompt
        assert "Previous Output" in prompt
        assert "Validation Errors" in prompt
        # Should include the actual previous attempt and errors
        assert "management_id: Required field is empty" in prompt
        assert "Test Corp" in prompt

    def test_no_retry_context_on_first_attempt(self) -> None:
        """Test prompt does not include retry context on first attempt."""
        from dataclasses import dataclass

        @dataclass
        class GeminiInput:
            markdown: str
            include_image: bool = False

        gemini_input = GeminiInput(markdown="# Test")

        prompt = build_extraction_prompt(gemini_input, DeliveryNoteV2)

        # Should NOT include previous attempt section
        assert "Previous Attempt" not in prompt
        assert "Validation Errors" not in prompt


class TestBuildCorrectionPrompt:
    """Test build_correction_prompt function."""

    def test_includes_error_analysis_instructions(self) -> None:
        """Test correction prompt includes analysis instructions."""
        previous_attempts = [{"management_id": "", "company_name": "Test"}]
        errors = ["management_id: Required field is empty"]

        prompt = build_correction_prompt(
            markdown="# Test Document",
            schema_class=DeliveryNoteV2,
            previous_attempts=previous_attempts,
            errors=errors,
        )

        # Should include correction instructions
        assert "Previous Attempt (FAILED)" in prompt
        assert "Identify WHY each error occurred" in prompt
        assert "Re-examine the document" in prompt
        assert "Provide corrected JSON addressing ALL errors" in prompt

    def test_includes_previous_output(self) -> None:
        """Test correction prompt includes previous extraction."""
        previous_attempts = [
            {"management_id": "INV-001", "company_name": "Wrong Name", "issue_date": "2025-01-13"}
        ]
        errors = ["company_name: Does not match document"]

        prompt = build_correction_prompt(
            markdown="# Test",
            schema_class=DeliveryNoteV2,
            previous_attempts=previous_attempts,
            errors=errors,
        )

        # Should include previous output as JSON
        assert "Previous Output" in prompt
        assert "INV-001" in prompt
        assert "Wrong Name" in prompt

    def test_includes_validation_errors(self) -> None:
        """Test correction prompt lists all validation errors."""
        previous_attempts = [{"management_id": "", "company_name": ""}]
        errors = [
            "management_id: Required field is empty",
            "company_name: Required field is empty",
        ]

        prompt = build_correction_prompt(
            markdown="# Test",
            schema_class=DeliveryNoteV2,
            previous_attempts=previous_attempts,
            errors=errors,
        )

        # Should list all errors
        assert "Validation Errors" in prompt
        assert "management_id: Required field is empty" in prompt
        assert "company_name: Required field is empty" in prompt

    def test_multimodal_mode_correction(self) -> None:
        """Test correction prompt with image included."""
        previous_attempts = [{"management_id": ""}]
        errors = ["management_id: Required field is empty"]

        prompt = build_correction_prompt(
            markdown="# Test",
            schema_class=DeliveryNoteV2,
            previous_attempts=previous_attempts,
            errors=errors,
            include_image=True,
        )

        # Should use multimodal system prompt
        assert "Priority Rules (CRITICAL)" in prompt
        assert "especially the Image if provided" in prompt

    def test_escalation_note_included(self) -> None:
        """Test escalation note for Pro model is included."""
        previous_attempts = [{"management_id": ""}]
        errors = ["management_id: Required field is empty"]
        escalation_note = "Previous attempts with Flash failed. Apply deep reasoning."

        prompt = build_correction_prompt(
            markdown="# Test",
            schema_class=DeliveryNoteV2,
            previous_attempts=previous_attempts,
            errors=errors,
            escalation_note=escalation_note,
        )

        # Should include escalation note
        assert "Escalation Note" in prompt
        assert "Apply deep reasoning" in prompt


class TestBuildInitialPrompt:
    """Test build_initial_prompt function."""

    def test_markdown_only_initial(self) -> None:
        """Test initial prompt without image."""
        prompt = build_initial_prompt(
            markdown="# Invoice\n\nAmount: ¥10,000", schema_class=DeliveryNoteV2
        )

        # Should use markdown-only system prompt
        assert "Structural Markdown" in prompt
        # Should include schema
        assert "DeliveryNoteV2" in prompt
        # Should include markdown
        assert "# Invoice" in prompt
        assert "Amount: ¥10,000" in prompt
        # Should NOT include previous attempts
        assert "Previous Attempt" not in prompt

    def test_multimodal_initial(self) -> None:
        """Test initial prompt with image."""
        prompt = build_initial_prompt(
            markdown="# Invoice", schema_class=DeliveryNoteV2, include_image=True
        )

        # Should use multimodal system prompt
        assert "Priority Rules (CRITICAL)" in prompt
        assert "Trust Markdown" in prompt
        assert "Trust Image" in prompt

    def test_includes_output_instructions(self) -> None:
        """Test initial prompt includes output format instructions."""
        prompt = build_initial_prompt(markdown="# Test", schema_class=DeliveryNoteV2)

        # Should include output instructions
        assert "Output" in prompt
        assert "Return ONLY valid JSON" in prompt
        assert "No markdown code fences" in prompt


class TestPromptStructure:
    """Test overall prompt structure and format."""

    def test_schema_description_valid_markdown(self) -> None:
        """Test schema description is valid markdown."""
        from dataclasses import dataclass

        @dataclass
        class GeminiInput:
            markdown: str
            include_image: bool = False

        gemini_input = GeminiInput(markdown="# Test")
        prompt = build_extraction_prompt(gemini_input, DeliveryNoteV2)

        # Should have proper markdown headers
        assert "## Required Schema" in prompt
        assert "## Document Content (Markdown)" in prompt
        assert "## Output" in prompt

    def test_markdown_content_properly_formatted(self) -> None:
        """Test markdown content is wrapped in code fence."""
        from dataclasses import dataclass

        @dataclass
        class GeminiInput:
            markdown: str
            include_image: bool = False

        test_markdown = "# Test\n\n| Col1 | Col2 |\n|------|------|\n| A | B |"
        gemini_input = GeminiInput(markdown=test_markdown)
        prompt = build_extraction_prompt(gemini_input, DeliveryNoteV2)

        # Should wrap markdown in code fence
        assert "```markdown" in prompt
        assert "# Test" in prompt
        # Table should be preserved
        assert "| Col1 | Col2 |" in prompt

    def test_previous_output_valid_json(self) -> None:
        """Test previous output is formatted as valid JSON."""
        previous_attempts = [
            {
                "management_id": "INV-001",
                "company_name": "テスト株式会社",
                "issue_date": "2025-01-13",
            }
        ]
        errors = ["Some error"]

        prompt = build_correction_prompt(
            markdown="# Test",
            schema_class=DeliveryNoteV2,
            previous_attempts=previous_attempts,
            errors=errors,
        )

        # Should contain valid JSON
        assert "```json" in prompt
        # Should preserve Japanese characters
        assert "テスト株式会社" in prompt

        # Extract JSON from prompt and validate it's parseable
        json_start = prompt.find("```json\n") + 8
        json_end = prompt.find("\n```", json_start)
        json_str = prompt[json_start:json_end]

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["management_id"] == "INV-001"
        assert parsed["company_name"] == "テスト株式会社"
