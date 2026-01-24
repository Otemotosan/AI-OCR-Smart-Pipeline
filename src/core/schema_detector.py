"""Schema Detection Module.

Provides intelligent schema selection through:
1. Folder-based routing (primary, cost-efficient)
2. Keyword-based detection (quick fallback)
3. Gemini classification (for ambiguous documents)

See CLAUDE.md: Multi-Schema Extraction Architecture
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pydantic import BaseModel

    from src.core.gemini import GeminiClient

from src.core.schemas import (
    DeliveryNoteV2,
    GenericDocumentV1,
    InvoiceV1,
    OrderFormV1,
)

logger = structlog.get_logger(__name__)

# ============================================================
# Folder-Based Routing
# ============================================================

FOLDER_SCHEMA_MAP: dict[str, type[BaseModel]] = {
    "order_forms": OrderFormV1,
    "delivery_notes": DeliveryNoteV2,
    "invoices": InvoiceV1,
}

# Default schema priority when no folder hint
DEFAULT_SCHEMA_PRIORITY: list[type[BaseModel]] = [
    DeliveryNoteV2,
    OrderFormV1,
    InvoiceV1,
]


def detect_schema_from_path(gcs_path: str) -> type[BaseModel] | None:
    """Detect schema from GCS folder path.

    Args:
        gcs_path: Full GCS URI (e.g., gs://bucket/order_forms/file.pdf)

    Returns:
        Schema class if folder matches, None otherwise

    Examples:
        >>> detect_schema_from_path("gs://bucket/order_forms/doc.pdf")
        <class 'OrderFormV1'>
        >>> detect_schema_from_path("gs://bucket/file.pdf")
        None
    """
    # Extract path components after bucket
    # gs://bucket/folder/file.pdf -> ["folder", "file.pdf"]
    path_match = re.match(r"gs://[^/]+/(.+)", gcs_path)
    if not path_match:
        return None

    path_parts = path_match.group(1).split("/")

    # Check first-level folder
    if len(path_parts) >= 2:
        folder_name = path_parts[0].lower()
        if folder_name in FOLDER_SCHEMA_MAP:
            schema = FOLDER_SCHEMA_MAP[folder_name]
            logger.info(
                "folder_routing_matched",
                folder=folder_name,
                schema=schema.__name__,
            )
            return schema

    return None


# ============================================================
# Keyword-Based Detection
# ============================================================

SCHEMA_KEYWORDS: dict[str, list[str]] = {
    "order_form": ["注文書", "発注書", "ご注文", "ORDER", "PURCHASE ORDER", "PO番号"],
    "delivery_note": ["納品書", "納入書", "DELIVERY", "PACKING"],
    "invoice": ["請求書", "御請求", "INVOICE", "INV-"],
}

# Priority for compound documents (higher = more data-rich)
SCHEMA_PRIORITY_SCORE: dict[str, int] = {
    "order_form": 3,  # Has line items
    "invoice": 2,  # Has billing info
    "delivery_note": 1,  # Basic delivery info
}


def detect_document_type_from_keywords(
    markdown: str,
    header_chars: int = 500,
) -> tuple[str | None, float]:
    """Detect document type from keywords in header.

    Prioritizes document header/title area for definitive labels.
    For compound documents (e.g., 確認書兼注文書), selects the one
    with richer data fields.

    Args:
        markdown: Document AI markdown output
        header_chars: Number of characters to analyze from header

    Returns:
        Tuple of (document_type, confidence)
        - document_type: "order_form", "delivery_note", "invoice", or None
        - confidence: 0.0-1.0 based on keyword match strength

    Examples:
        >>> detect_document_type_from_keywords("# 注文書\\n...")
        ('order_form', 0.95)
        >>> detect_document_type_from_keywords("# 確認書兼注文書\\n...")
        ('order_form', 0.90)  # Compound -> richer schema
    """
    header = markdown[:header_chars].upper()

    matches: list[tuple[str, float]] = []

    for doc_type, keywords in SCHEMA_KEYWORDS.items():
        for keyword in keywords:
            if keyword.upper() in header:
                # Higher confidence for earlier/title matches
                position = header.find(keyword.upper())
                # Earlier position = higher confidence
                position_bonus = max(0, (100 - position) / 100) * 0.1
                base_confidence = 0.85
                confidence = min(0.95, base_confidence + position_bonus)
                matches.append((doc_type, confidence))
                break  # One keyword per type is enough

    if not matches:
        logger.info("no_keyword_match", header_preview=header[:100])
        return None, 0.0

    if len(matches) == 1:
        return matches[0]

    # Multiple matches (compound document) - pick richest schema
    matches.sort(
        key=lambda x: (SCHEMA_PRIORITY_SCORE.get(x[0], 0), x[1]),
        reverse=True,
    )

    selected = matches[0]
    logger.info(
        "compound_document_detected",
        matches=[m[0] for m in matches],
        selected=selected[0],
    )

    # Slightly lower confidence for compound docs
    return selected[0], min(selected[1], 0.90)


# ============================================================
# Schema Selection
# ============================================================

DOC_TYPE_TO_SCHEMA: dict[str, type[BaseModel]] = {
    "order_form": OrderFormV1,
    "delivery_note": DeliveryNoteV2,
    "invoice": InvoiceV1,
    "generic": GenericDocumentV1,
}


def select_schema_priority(
    markdown: str,
    gcs_path: str,
    confidence_threshold: float = 0.85,
) -> list[type[BaseModel]]:
    """Select prioritized list of schemas to try.

    Flow:
    1. Check folder-based routing (instant, no cost)
    2. Detect from keywords (fast, no API cost)
    3. Return priority list for extraction attempts

    Args:
        markdown: Document AI markdown output
        gcs_path: GCS URI of the document
        confidence_threshold: Minimum confidence for single-schema attempt

    Returns:
        List of schema classes to try in order

    Examples:
        >>> select_schema_priority(md, "gs://b/order_forms/f.pdf")
        [OrderFormV1]  # Folder routing
        >>> select_schema_priority("# 注文書\\n...", "gs://b/f.pdf")
        [OrderFormV1, DeliveryNoteV2, InvoiceV1]  # Keyword + fallbacks
    """
    # 1. Folder-based routing (highest priority)
    folder_schema = detect_schema_from_path(gcs_path)
    if folder_schema:
        return [folder_schema]

    # 2. Keyword-based detection
    doc_type, confidence = detect_document_type_from_keywords(markdown)

    if doc_type and confidence >= confidence_threshold:
        # High confidence - prioritize detected type
        primary_schema = DOC_TYPE_TO_SCHEMA.get(doc_type)
        if primary_schema:
            # Add other schemas as fallback
            fallbacks = [s for s in DEFAULT_SCHEMA_PRIORITY if s != primary_schema]
            logger.info(
                "keyword_detection_success",
                doc_type=doc_type,
                confidence=confidence,
                primary=primary_schema.__name__,
            )
            return [primary_schema, *fallbacks]

    # 3. No clear detection - use default priority
    logger.info(
        "using_default_priority",
        doc_type=doc_type,
        confidence=confidence,
    )
    return DEFAULT_SCHEMA_PRIORITY.copy()


# ============================================================
# Gemini Classification (Future - for ambiguous cases)
# ============================================================


def classify_with_gemini(
    markdown: str,
    gemini_client: GeminiClient,
    header_chars: int = 500,
) -> list[tuple[str, float]]:
    """Classify document using Gemini API.

    Reserved for future use when keyword detection is insufficient.
    Uses lightweight classification prompt on header only.

    Args:
        markdown: Document AI markdown output
        gemini_client: GeminiClient instance
        header_chars: Characters to send for classification

    Returns:
        List of (document_type, confidence) tuples, sorted by confidence

    Note:
        This function is not currently called in the main flow.
        It will be enabled when classification accuracy needs improvement.
    """
    # TODO: Implement when needed
    # For now, fall back to keyword detection
    doc_type, confidence = detect_document_type_from_keywords(
        markdown,
        header_chars,
    )
    if doc_type:
        return [(doc_type, confidence)]
    return []
