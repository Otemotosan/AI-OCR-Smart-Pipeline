"""Document AI Integration for OCR Processing.

Provides PDF-to-Markdown conversion with confidence evaluation and document type detection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from google.cloud import documentai_v1 as documentai
    from google.cloud.documentai_v1 import Document

# Fragile document types requiring image attachment
FRAGILE_TYPES = {
    "fax",
    "handwritten",
    "thermal_receipt",
    "carbon_copy",
    "low_res_scan",
}

# Filename patterns for fragile type detection
FRAGILE_PATTERNS = {
    r"(?i)fax|ファクス|ファックス": "fax",
    r"(?i)手書き|handwrit": "handwritten",
    r"(?i)レシート|receipt|領収": "thermal_receipt",
    r"(?i)複写|carbon|カーボン": "carbon_copy",
    r"(?i)scan.*(?:72|96)dpi|低解像度": "low_res_scan",
}


@dataclass
class DocumentAIResult:
    """Document AI processing result.

    Attributes:
        markdown: Structured Markdown representation
        confidence: Minimum confidence score (0.0-1.0)
        page_count: Number of pages processed
        detected_type: Fragile document type if detected
    """

    markdown: str
    confidence: float
    page_count: int
    detected_type: str | None


class DocumentAIClient:
    """Client for Document AI OCR processing.

    Handles PDF-to-Markdown conversion with confidence evaluation.

    Examples:
        >>> client = DocumentAIClient(project_id="my-project", location="us")
        >>> result = client.process_document("gs://bucket/doc.pdf")
        >>> print(result.markdown)
        >>> print(f"Confidence: {result.confidence:.2f}")
    """

    def __init__(
        self,
        project_id: str,
        location: str = "us",
        processor_id: str | None = None,
    ) -> None:
        """Initialize Document AI client.

        Args:
            project_id: GCP project ID
            location: Processor location (default: "us")
            processor_id: Optional processor ID (uses default layout parser if None)
        """
        self.project_id = project_id
        self.location = location
        self.processor_id = processor_id
        self._client: documentai.DocumentProcessorServiceClient | None = None

    @property
    def client(self) -> documentai.DocumentProcessorServiceClient:
        """Lazy-load Document AI client.

        Returns:
            Document AI service client
        """
        if self._client is None:
            from google.api_core.client_options import ClientOptions
            from google.cloud import documentai_v1 as documentai

            # Use regional endpoint for the processor location
            api_endpoint = f"{self.location}-documentai.googleapis.com"
            client_options = ClientOptions(api_endpoint=api_endpoint)
            self._client = documentai.DocumentProcessorServiceClient(client_options=client_options)
        return self._client

    def process_document(
        self,
        gcs_uri: str,
        filename: str = "",
    ) -> DocumentAIResult:
        """Process document from GCS using Document AI.

        Args:
            gcs_uri: GCS URI (gs://bucket/path/file.pdf)
            filename: Optional filename for fragile type detection

        Returns:
            DocumentAIResult with markdown, confidence, and metadata

        Raises:
            ValueError: If GCS URI is invalid
            RuntimeError: If Document AI processing fails

        Examples:
            >>> result = client.process_document("gs://bucket/doc.pdf")
            >>> if result.confidence < 0.85:
            ...     print("Low confidence, needs image attachment")
        """
        if not gcs_uri.startswith("gs://"):
            raise ValueError(f"Invalid GCS URI: {gcs_uri}")

        # Prepare request
        from google.cloud import documentai_v1 as documentai

        # Use default processor if not specified
        processor_name = self._get_processor_name()

        # Create GCS document source
        gcs_document = documentai.GcsDocument(
            gcs_uri=gcs_uri,
            mime_type="application/pdf",
        )

        # Process with Document AI
        request = documentai.ProcessRequest(
            name=processor_name,
            gcs_document=gcs_document,
        )

        try:
            response = self.client.process_document(request=request)
            document = response.document
        except Exception as e:
            raise RuntimeError(f"Document AI processing failed: {e}") from e

        # Extract results
        markdown = self.extract_markdown(document)
        confidence = self.calculate_confidence(document)
        detected_type = self.detect_document_type(filename, document)

        return DocumentAIResult(
            markdown=markdown,
            confidence=confidence,
            page_count=len(document.pages),
            detected_type=detected_type,
        )

    def extract_markdown(self, document: Document) -> str:
        """Extract structured Markdown from Document AI response.

        Preserves reading order, table structure, and paragraph boundaries.

        Args:
            document: Document AI Document object

        Returns:
            Markdown-formatted string

        Examples:
            >>> markdown = client.extract_markdown(document)
            >>> print(markdown)
        """
        markdown_parts: list[str] = []

        for page_idx, page in enumerate(document.pages):
            if page_idx > 0:
                markdown_parts.append("---")  # Page separator

            # Get all blocks (paragraphs and tables)
            blocks = self._get_all_blocks(page)

            # Sort by vertical position, then horizontal
            sorted_blocks = sorted(
                blocks,
                key=lambda b: (
                    b.layout.bounding_poly.vertices[0].y if b.layout.bounding_poly.vertices else 0,
                    b.layout.bounding_poly.vertices[0].x if b.layout.bounding_poly.vertices else 0,
                ),
            )

            for block in sorted_blocks:
                if hasattr(block, "body_rows"):  # Table
                    table_md = self._table_to_markdown(block, document.text)
                    if table_md:
                        markdown_parts.append(table_md)
                else:  # Paragraph
                    text = self._get_text_from_layout(block.layout, document.text)
                    if text.strip():
                        markdown_parts.append(text.strip())

        return "\n\n".join(markdown_parts)

    def calculate_confidence(self, document: Document) -> float:
        """Calculate minimum confidence across all pages and blocks.

        Conservative approach: returns lowest confidence found.

        Args:
            document: Document AI Document object

        Returns:
            Minimum confidence score (0.0-1.0)

        Examples:
            >>> confidence = client.calculate_confidence(document)
            >>> if confidence < 0.85:
            ...     print("Low confidence detected")
        """
        min_confidence = 1.0

        for page in document.pages:
            # Page-level confidence
            if hasattr(page, "confidence") and page.confidence:
                min_confidence = min(min_confidence, page.confidence)

            # Block-level confidence
            if hasattr(page, "blocks"):
                for block in page.blocks:
                    if hasattr(block.layout, "confidence") and block.layout.confidence:
                        min_confidence = min(min_confidence, block.layout.confidence)

        return min_confidence

    def detect_document_type(
        self,
        filename: str,
        document: Document | None = None,
    ) -> str | None:
        """Detect if document is a fragile type.

        Args:
            filename: Original filename
            document: Optional Document AI response

        Returns:
            Fragile type string or None

        Examples:
            >>> doc_type = client.detect_document_type("fax_invoice.pdf")
            >>> assert doc_type == "fax"
        """
        # Method 1: Filename pattern matching
        for pattern, fragile_type in FRAGILE_PATTERNS.items():
            if re.search(pattern, filename):
                return fragile_type

        # Method 2: Document AI hints (if available)
        # Note: Advanced detection would analyze document features
        # For MVP, filename-based detection is sufficient

        return None

    def _get_processor_name(self) -> str:
        """Get processor resource name.

        Returns:
            Processor resource name for Document AI
        """
        if self.processor_id:
            return (
                f"projects/{self.project_id}/locations/{self.location}/"
                f"processors/{self.processor_id}"
            )
        # Use default layout parser
        return f"projects/{self.project_id}/locations/{self.location}/processors/default"

    def _get_all_blocks(self, page: Any) -> list[Any]:
        """Get all content blocks from a page.

        Args:
            page: Document AI Page object

        Returns:
            List of blocks (paragraphs and tables)
        """
        blocks = []

        # Paragraphs
        if hasattr(page, "paragraphs"):
            for para in page.paragraphs:
                blocks.append(para)

        # Tables
        if hasattr(page, "tables"):
            for table in page.tables:
                blocks.append(table)

        return blocks

    def _get_text_from_layout(self, layout: Any, full_text: str) -> str:
        """Extract text from layout using text anchors.

        Args:
            layout: Document AI Layout object
            full_text: Full document text

        Returns:
            Extracted text string
        """
        text_parts = []

        if (
            hasattr(layout, "text_anchor")
            and layout.text_anchor
            and hasattr(layout.text_anchor, "text_segments")
        ):
            for segment in layout.text_anchor.text_segments:
                try:
                    start = int(segment.start_index) if segment.start_index is not None else 0
                    end = int(segment.end_index) if segment.end_index is not None else 0
                    if end > start and end <= len(full_text):
                        text_parts.append(full_text[start:end])
                except (AttributeError, ValueError, TypeError):
                    # Skip segments with missing or invalid indices
                    continue

        return "".join(text_parts)

    def _table_to_markdown(self, table: Any, full_text: str) -> str:
        """Convert Document AI table to Markdown syntax.

        Args:
            table: Document AI Table object
            full_text: Full document text

        Returns:
            Markdown table string
        """
        rows: list[list[str]] = []

        # Header rows
        if hasattr(table, "header_rows"):
            for header_row in table.header_rows:
                row_cells = []
                for cell in header_row.cells:
                    cell_text = self._get_text_from_layout(cell.layout, full_text)
                    # Escape pipes in cell content
                    row_cells.append(cell_text.strip().replace("|", "\\|"))
                rows.append(row_cells)

        # Body rows
        if hasattr(table, "body_rows"):
            for body_row in table.body_rows:
                row_cells = []
                for cell in body_row.cells:
                    cell_text = self._get_text_from_layout(cell.layout, full_text)
                    row_cells.append(cell_text.strip().replace("|", "\\|"))
                rows.append(row_cells)

        if not rows:
            return ""

        # Build Markdown table
        md_lines = []

        # First row (header)
        md_lines.append("| " + " | ".join(rows[0]) + " |")
        md_lines.append("|" + "|".join(["---"] * len(rows[0])) + "|")

        # Remaining rows
        for row in rows[1:]:
            # Pad row if needed
            while len(row) < len(rows[0]):
                row.append("")
            md_lines.append("| " + " | ".join(row) + " |")

        return "\n".join(md_lines)
