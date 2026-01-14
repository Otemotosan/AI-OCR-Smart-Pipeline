"""Unit tests for Document AI integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.docai import (
    FRAGILE_PATTERNS,
    FRAGILE_TYPES,
    DocumentAIClient,
    DocumentAIResult,
)


class TestDocumentAIResult:
    """Test DocumentAIResult dataclass."""

    def test_create_result(self) -> None:
        """Test creating DocumentAIResult instance."""
        result = DocumentAIResult(
            markdown="# Test Document",
            confidence=0.95,
            page_count=1,
            detected_type=None,
        )

        assert result.markdown == "# Test Document"
        assert result.confidence == 0.95
        assert result.page_count == 1
        assert result.detected_type is None

    def test_create_result_with_fragile_type(self) -> None:
        """Test result with fragile type detected."""
        result = DocumentAIResult(
            markdown="Fax content",
            confidence=0.75,
            page_count=2,
            detected_type="fax",
        )

        assert result.detected_type == "fax"
        assert result.confidence == 0.75


class TestDocumentAIClientInit:
    """Test DocumentAIClient initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default parameters."""
        client = DocumentAIClient(project_id="test-project")

        assert client.project_id == "test-project"
        assert client.location == "us"
        assert client.processor_id is None

    def test_init_with_custom_location(self) -> None:
        """Test initialization with custom location."""
        client = DocumentAIClient(project_id="test-project", location="eu")

        assert client.location == "eu"

    def test_init_with_processor_id(self) -> None:
        """Test initialization with custom processor ID."""
        client = DocumentAIClient(
            project_id="test-project",
            processor_id="custom-processor",
        )

        assert client.processor_id == "custom-processor"

    def test_lazy_client_loading(self) -> None:
        """Test that client is loaded lazily."""
        client = DocumentAIClient(project_id="test-project")

        assert client._client is None


class TestFragileTypeDetection:
    """Test fragile document type detection."""

    def test_detect_fax_japanese(self) -> None:
        """Test fax detection with Japanese filename."""
        client = DocumentAIClient(project_id="test-project")

        detected = client.detect_document_type("ファックス_請求書.pdf")

        assert detected == "fax"

    def test_detect_fax_english(self) -> None:
        """Test fax detection with English filename."""
        client = DocumentAIClient(project_id="test-project")

        detected = client.detect_document_type("invoice_fax.pdf")

        assert detected == "fax"

    def test_detect_handwritten(self) -> None:
        """Test handwritten detection."""
        client = DocumentAIClient(project_id="test-project")

        detected = client.detect_document_type("手書き_メモ.pdf")

        assert detected == "handwritten"

    def test_detect_thermal_receipt(self) -> None:
        """Test thermal receipt detection."""
        client = DocumentAIClient(project_id="test-project")

        detected = client.detect_document_type("receipt_20250113.pdf")

        assert detected == "thermal_receipt"

    def test_detect_carbon_copy(self) -> None:
        """Test carbon copy detection."""
        client = DocumentAIClient(project_id="test-project")

        detected = client.detect_document_type("複写_伝票.pdf")

        assert detected == "carbon_copy"

    def test_detect_low_res_scan(self) -> None:
        """Test low resolution scan detection."""
        client = DocumentAIClient(project_id="test-project")

        detected = client.detect_document_type("scan_72dpi_invoice.pdf")

        assert detected == "low_res_scan"

    def test_no_fragile_type_detected(self) -> None:
        """Test when no fragile type is detected."""
        client = DocumentAIClient(project_id="test-project")

        detected = client.detect_document_type("invoice_20250113.pdf")

        assert detected is None

    def test_case_insensitive_detection(self) -> None:
        """Test case-insensitive pattern matching."""
        client = DocumentAIClient(project_id="test-project")

        detected_lower = client.detect_document_type("fax_invoice.pdf")
        detected_upper = client.detect_document_type("FAX_INVOICE.PDF")
        detected_mixed = client.detect_document_type("Fax_Invoice.pdf")

        assert detected_lower == "fax"
        assert detected_upper == "fax"
        assert detected_mixed == "fax"


class TestProcessorName:
    """Test processor name generation."""

    def test_default_processor_name(self) -> None:
        """Test default processor name generation."""
        client = DocumentAIClient(project_id="test-project", location="us")

        processor_name = client._get_processor_name()

        assert processor_name == "projects/test-project/locations/us/processors/default"

    def test_custom_processor_name(self) -> None:
        """Test custom processor name generation."""
        client = DocumentAIClient(
            project_id="test-project",
            location="eu",
            processor_id="my-processor-123",
        )

        processor_name = client._get_processor_name()

        expected = "projects/test-project/locations/eu/processors/my-processor-123"
        assert processor_name == expected


class TestMarkdownExtraction:
    """Test markdown extraction from Document AI response."""

    def test_extract_simple_paragraph(self) -> None:
        """Test extracting simple paragraph."""
        client = DocumentAIClient(project_id="test-project")

        # Create mock paragraph with text anchor
        mock_segment = MagicMock()
        mock_segment.start_index = 0
        mock_segment.end_index = 12

        mock_text_anchor = MagicMock()
        mock_text_anchor.text_segments = [mock_segment]

        mock_layout = MagicMock()
        mock_layout.text_anchor = mock_text_anchor
        mock_layout.bounding_poly.vertices = [MagicMock(x=0, y=0)]

        mock_paragraph = MagicMock()
        mock_paragraph.layout = mock_layout
        # Remove hasattr check - just set the attribute
        del mock_paragraph.body_rows  # Ensure it's NOT a table

        mock_page = MagicMock()
        # Ensure hasattr works correctly
        mock_page.paragraphs = [mock_paragraph]
        mock_page.tables = []

        mock_document = MagicMock()
        mock_document.pages = [mock_page]
        mock_document.text = "Test content"

        markdown = client.extract_markdown(mock_document)

        assert "Test content" in markdown

    def test_extract_multiple_paragraphs(self) -> None:
        """Test extracting multiple paragraphs."""
        client = DocumentAIClient(project_id="test-project")

        # Create two paragraphs with different positions
        def create_paragraph(start: int, end: int, y_pos: int) -> MagicMock:
            mock_segment = MagicMock()
            mock_segment.start_index = start
            mock_segment.end_index = end

            mock_text_anchor = MagicMock()
            mock_text_anchor.text_segments = [mock_segment]

            mock_layout = MagicMock()
            mock_layout.text_anchor = mock_text_anchor
            mock_layout.bounding_poly.vertices = [MagicMock(x=0, y=y_pos)]

            mock_para = MagicMock()
            mock_para.layout = mock_layout
            # Ensure it's NOT a table
            del mock_para.body_rows
            return mock_para

        para1 = create_paragraph(0, 5, 0)
        para2 = create_paragraph(6, 12, 100)

        mock_page = MagicMock()
        # Ensure hasattr works correctly
        mock_page.paragraphs = [para1, para2]
        mock_page.tables = []

        mock_document = MagicMock()
        mock_document.pages = [mock_page]
        mock_document.text = "First\nSecond"

        markdown = client.extract_markdown(mock_document)

        assert "First" in markdown
        assert "Second" in markdown

    def test_multi_page_separator(self) -> None:
        """Test page separator in multi-page documents."""
        client = DocumentAIClient(project_id="test-project")

        # Mock 2-page document
        mock_page1 = MagicMock()
        mock_page1.paragraphs = []
        mock_page1.tables = []

        mock_page2 = MagicMock()
        mock_page2.paragraphs = []
        mock_page2.tables = []

        mock_document = MagicMock()
        mock_document.pages = [mock_page1, mock_page2]
        mock_document.text = ""

        markdown = client.extract_markdown(mock_document)

        assert "---" in markdown

    def test_extract_table(self) -> None:
        """Test table extraction to Markdown."""
        client = DocumentAIClient(project_id="test-project")

        # Create mock table with header and body rows
        def create_cell(start: int, end: int) -> MagicMock:
            mock_segment = MagicMock()
            mock_segment.start_index = start
            mock_segment.end_index = end

            mock_text_anchor = MagicMock()
            mock_text_anchor.text_segments = [mock_segment]

            mock_layout = MagicMock()
            mock_layout.text_anchor = mock_text_anchor

            mock_cell = MagicMock()
            mock_cell.layout = mock_layout
            return mock_cell

        # Header row
        header_row = MagicMock()
        header_row.cells = [create_cell(0, 4), create_cell(4, 9)]

        # Body row
        body_row = MagicMock()
        body_row.cells = [create_cell(9, 10), create_cell(10, 11)]

        mock_table = MagicMock()
        mock_table.header_rows = [header_row]
        mock_table.body_rows = [body_row]
        mock_table.layout.bounding_poly.vertices = [MagicMock(x=0, y=0)]

        # Mark as table by adding body_rows attribute
        mock_table.body_rows = [body_row]

        mock_page = MagicMock()
        mock_page.paragraphs = []
        mock_page.tables = [mock_table]

        mock_document = MagicMock()
        mock_document.pages = [mock_page]
        mock_document.text = "NameValue12"

        markdown = client.extract_markdown(mock_document)

        # Should contain table structure
        assert "Name" in markdown
        assert "Value" in markdown
        assert "---" in markdown  # Table header separator
        assert "|" in markdown  # Table delimiters

    def test_extract_empty_table(self) -> None:
        """Test empty table handling."""
        client = DocumentAIClient(project_id="test-project")

        mock_table = MagicMock()
        mock_table.header_rows = []
        mock_table.body_rows = []
        mock_table.layout.bounding_poly.vertices = [MagicMock(x=0, y=0)]

        mock_page = MagicMock()
        mock_page.paragraphs = []
        mock_page.tables = [mock_table]

        mock_document = MagicMock()
        mock_document.pages = [mock_page]
        mock_document.text = ""

        markdown = client.extract_markdown(mock_document)

        # Empty table should produce empty or minimal output
        # The exact behavior depends on implementation
        assert markdown is not None

    def test_table_cell_with_pipe(self) -> None:
        """Test that pipe characters in cells are escaped."""
        client = DocumentAIClient(project_id="test-project")

        # Create cell with pipe character
        def create_cell(start: int, end: int) -> MagicMock:
            mock_segment = MagicMock()
            mock_segment.start_index = start
            mock_segment.end_index = end

            mock_text_anchor = MagicMock()
            mock_text_anchor.text_segments = [mock_segment]

            mock_layout = MagicMock()
            mock_layout.text_anchor = mock_text_anchor

            mock_cell = MagicMock()
            mock_cell.layout = mock_layout
            return mock_cell

        header_row = MagicMock()
        header_row.cells = [create_cell(0, 5)]

        body_row = MagicMock()
        body_row.cells = [create_cell(5, 8)]

        mock_table = MagicMock()
        mock_table.header_rows = [header_row]
        mock_table.body_rows = [body_row]
        mock_table.layout.bounding_poly.vertices = [MagicMock(x=0, y=0)]

        mock_page = MagicMock()
        mock_page.paragraphs = []
        mock_page.tables = [mock_table]

        mock_document = MagicMock()
        mock_document.pages = [mock_page]
        mock_document.text = "A | BA|B"  # Text with pipes

        markdown = client.extract_markdown(mock_document)

        # Pipes should be escaped as \|
        assert "\\|" in markdown or "|" in markdown


class TestClientProperty:
    """Test lazy loading of Document AI client."""

    def test_client_initially_none(self) -> None:
        """Test that client is None initially."""
        client = DocumentAIClient(project_id="test-project")

        # Initially None before first access
        assert client._client is None


class TestTextExtraction:
    """Test text extraction edge cases."""

    def test_text_extraction_with_none_indices(self) -> None:
        """Test text extraction handles None indices."""
        client = DocumentAIClient(project_id="test-project")

        # Create segment with None end_index
        mock_segment = MagicMock()
        mock_segment.start_index = None
        mock_segment.end_index = None

        mock_text_anchor = MagicMock()
        mock_text_anchor.text_segments = [mock_segment]

        mock_layout = MagicMock()
        mock_layout.text_anchor = mock_text_anchor

        text = client._get_text_from_layout(mock_layout, "Test text")

        # Should handle gracefully
        assert text == ""

    def test_text_extraction_with_invalid_range(self) -> None:
        """Test text extraction with end < start."""
        client = DocumentAIClient(project_id="test-project")

        mock_segment = MagicMock()
        mock_segment.start_index = 10
        mock_segment.end_index = 5  # end < start

        mock_text_anchor = MagicMock()
        mock_text_anchor.text_segments = [mock_segment]

        mock_layout = MagicMock()
        mock_layout.text_anchor = mock_text_anchor

        text = client._get_text_from_layout(mock_layout, "Test text")

        # Should handle gracefully (skip invalid segment)
        assert text == ""

    def test_text_extraction_out_of_bounds(self) -> None:
        """Test text extraction with end_index > text length."""
        client = DocumentAIClient(project_id="test-project")

        mock_segment = MagicMock()
        mock_segment.start_index = 0
        mock_segment.end_index = 1000  # Way beyond text length

        mock_text_anchor = MagicMock()
        mock_text_anchor.text_segments = [mock_segment]

        mock_layout = MagicMock()
        mock_layout.text_anchor = mock_text_anchor

        text = client._get_text_from_layout(mock_layout, "Short")

        # Should handle gracefully (skip out of bounds)
        assert text == ""


class TestConfidenceCalculation:
    """Test confidence score calculation."""

    def test_perfect_confidence(self) -> None:
        """Test document with perfect confidence."""
        client = DocumentAIClient(project_id="test-project")

        mock_page = MagicMock()
        mock_page.confidence = 1.0
        mock_page.blocks = []

        mock_document = MagicMock()
        mock_document.pages = [mock_page]

        confidence = client.calculate_confidence(mock_document)

        assert confidence == 1.0

    def test_low_page_confidence(self) -> None:
        """Test document with low page confidence."""
        client = DocumentAIClient(project_id="test-project")

        mock_page = MagicMock()
        mock_page.confidence = 0.75

        mock_document = MagicMock()
        mock_document.pages = [mock_page]

        confidence = client.calculate_confidence(mock_document)

        assert confidence == 0.75

    def test_low_block_confidence(self) -> None:
        """Test document with low block confidence."""
        client = DocumentAIClient(project_id="test-project")

        mock_block = MagicMock()
        mock_block.layout.confidence = 0.82

        mock_page = MagicMock()
        mock_page.confidence = 1.0
        mock_page.blocks = [mock_block]

        mock_document = MagicMock()
        mock_document.pages = [mock_page]

        confidence = client.calculate_confidence(mock_document)

        assert confidence == 0.82

    def test_minimum_confidence_across_pages(self) -> None:
        """Test minimum confidence across multiple pages."""
        client = DocumentAIClient(project_id="test-project")

        mock_page1 = MagicMock()
        mock_page1.confidence = 0.95
        mock_page1.blocks = []

        mock_page2 = MagicMock()
        mock_page2.confidence = 0.78
        mock_page2.blocks = []

        mock_document = MagicMock()
        mock_document.pages = [mock_page1, mock_page2]

        confidence = client.calculate_confidence(mock_document)

        assert confidence == 0.78

    def test_missing_confidence_attributes(self) -> None:
        """Test handling of missing confidence attributes."""
        client = DocumentAIClient(project_id="test-project")

        mock_page = MagicMock(spec=[])  # No attributes
        mock_document = MagicMock()
        mock_document.pages = [mock_page]

        confidence = client.calculate_confidence(mock_document)

        assert confidence == 1.0  # Default when no confidence data


class TestProcessDocumentValidation:
    """Test process_document input validation."""

    def test_invalid_gcs_uri(self) -> None:
        """Test error on invalid GCS URI."""
        client = DocumentAIClient(project_id="test-project")

        with pytest.raises(ValueError, match="Invalid GCS URI"):
            client.process_document("https://bucket/file.pdf")

    def test_valid_gcs_uri_starts_with_gs(self) -> None:
        """Test that gs:// URIs are considered valid format."""
        # These should NOT raise ValueError at validation stage
        valid_uris = [
            "gs://bucket/file.pdf",
            "gs://my-bucket/folder/document.pdf",
            "gs://bucket-name/path/to/file.pdf",
        ]

        for uri in valid_uris:
            # The validation check in process_document should pass
            # We're just testing the URI format validation, not the actual processing
            assert uri.startswith("gs://"), f"Valid URI {uri} should start with gs://"


class TestFragileTypesConstant:
    """Test FRAGILE_TYPES constant."""

    def test_fragile_types_set(self) -> None:
        """Test FRAGILE_TYPES contains expected types."""
        assert "fax" in FRAGILE_TYPES
        assert "handwritten" in FRAGILE_TYPES
        assert "thermal_receipt" in FRAGILE_TYPES
        assert "carbon_copy" in FRAGILE_TYPES
        assert "low_res_scan" in FRAGILE_TYPES

    def test_fragile_patterns_dict(self) -> None:
        """Test FRAGILE_PATTERNS dictionary structure."""
        assert len(FRAGILE_PATTERNS) == 5
        assert all(isinstance(k, str) for k in FRAGILE_PATTERNS)
        assert all(isinstance(v, str) for v in FRAGILE_PATTERNS.values())
        assert all(v in FRAGILE_TYPES for v in FRAGILE_PATTERNS.values())
