"""Gemini API Prompt Templates and Builders.

Provides system prompts and prompt construction for Document AI extraction
with adaptive multimodal and markdown-only strategies.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import BaseModel

    from src.core.extraction import GeminiInput

from src.core.schemas import generate_schema_description

# ============================================================
# System Prompts
# ============================================================

MULTIMODAL_SYSTEM_PROMPT = """
You are a document extraction specialist. You will receive:
1. Structural Markdown (reconstructed from OCR coordinates)
2. Original document image

## Priority Rules (CRITICAL)

### 1. STRUCTURE — Trust Markdown
- Table layouts and cell boundaries
- Field positions and reading order
- Section headers and groupings
- Row/column relationships

### 2. TEXT DETAILS — Trust Image
- Character-level accuracy (especially for Japanese kanji)
- Smudged, faded, or handwritten text
- Overlapping or crossed-out characters
- Stamps, seals, and signatures

### 3. CONFLICT RESOLUTION
When Markdown text differs from Image text:

| Difference Type | Action |
|-----------------|--------|
| Minor (1-2 chars, e.g., 商事→商亊) | Use Image reading |
| Structural (field swap, missing row) | Use Markdown structure, re-read text from Image |
| Ambiguous | Set confidence=0.5, include both in `extraction_notes` |

### 4. OUTPUT FORMAT
- Return strict JSON matching the provided schema
- Include `extraction_notes` field for any conflicts or uncertainties:
  ```json
  {
    "management_id": "INV-2025-001",
    "company_name": "山口商事",
    "extraction_notes": [
      "company_name: Markdown showed '山田商事', Image shows '山口商事' (smudged '田'→'口')"
    ]
  }
  ```

## Your Task
Extract the requested fields with maximum accuracy. Prioritize correctness over speed.
"""

MARKDOWN_ONLY_SYSTEM_PROMPT = """
You are a document extraction specialist analyzing OCR-extracted text.

The input is Structural Markdown reconstructed from Document AI coordinates.
This means:
- Table structures are preserved
- Reading order is maintained
- Spatial relationships are encoded

Extract the requested fields strictly according to the schema.
Return valid JSON only — no explanations.
"""

ORDER_FORM_SYSTEM_PROMPT = """
You are a document extraction specialist for **注文書 (Order Forms)**.

## Document Characteristics
This document contains:
- **表形式の明細行** (Table-format line items)
- **発注者・受注者情報** (Buyer/Supplier information)
- **金額計算** (Amount calculations: subtotal, tax, total)

## Extraction Priority

### 1. 明細行 (Line Items)
| ヘッダー | 品名 | 数量 | 単位 | 単価 | 金額 |
|----------|------|------|------|------|------|
| 読み方 | item_name | quantity | unit | unit_price | amount |

- 各行は `items` 配列に追加
- 空欄は `null` で出力
- 数値は数字のみ（「円」「個」等は除去）

### 2. 金額フィールド
- `subtotal`: 小計（税抜）
- `tax_amount`: 消費税額
- `total_amount`: 合計金額（税込）

### 3. 日付フィールド
- `order_date`: 注文日（YYYY-MM-DD形式）
- `delivery_date`: 納期（YYYY-MM-DD形式）

### 4. 会社情報
- `buyer_company`: 発注者（御中の前）
- `supplier_company`: 受注者（署名・社印から）

## Output Format
Return strict JSON matching the OrderFormV1 schema.
Include `extraction_notes` for any ambiguous readings.
"""

CLASSIFICATION_SYSTEM_PROMPT = """
You are a document classifier. Analyze ONLY the header/title area of the document.

## Your Task
Identify the document type from the header text.

## Document Types
- **order_form**: 注文書, 発注書, ORDER, PURCHASE ORDER
- **delivery_note**: 納品書, 納入書, DELIVERY NOTE
- **invoice**: 請求書, 御請求, INVOICE

## Compound Documents
For documents with multiple types (e.g., "確認書兼注文書"):
- Select the type with richer data (order_form > invoice > delivery_note)

## Output Format
Return JSON:
```json
{
  "candidates": [
    {"type": "order_form", "confidence": 0.95},
    {"type": "delivery_note", "confidence": 0.30}
  ]
}
```

Confidence:
- 0.90-1.00: Definitive title match (exact keyword in header)
- 0.70-0.89: Strong indicator (keyword present but not in title)
- 0.50-0.69: Weak indicator (related content, no keyword)
- 0.00-0.49: Unlikely match
"""

# ============================================================
# Prompt Builder
# ============================================================


def build_extraction_prompt(
    gemini_input: GeminiInput,
    schema_class: type[BaseModel],
    previous_attempts: list[dict] | None = None,
    errors: list[str] | None = None,
) -> str:
    """Build the complete prompt for Gemini API.

    Adapts based on:
    - Whether image is included (multimodal vs markdown-only)
    - Whether this is a retry (includes previous attempts and errors)
    - Previous extraction errors for self-correction

    Args:
        gemini_input: Input data with markdown and optional image
        schema_class: Pydantic model class for schema description
        previous_attempts: List of previous extraction attempts (optional)
        errors: List of validation errors from previous attempts (optional)

    Returns:
        Complete prompt string ready for Gemini API

    Examples:
        >>> from core.extraction import GeminiInput
        >>> from core.schemas import DeliveryNoteV2
        >>> gemini_input = GeminiInput(markdown="# Invoice...")
        >>> prompt = build_extraction_prompt(gemini_input, DeliveryNoteV2)
    """
    # Select system prompt based on schema type and input mode
    schema_name = schema_class.__name__

    # Schema-specific prompts take priority
    if "OrderForm" in schema_name:
        system = ORDER_FORM_SYSTEM_PROMPT
    elif gemini_input.include_image:
        system = MULTIMODAL_SYSTEM_PROMPT
    else:
        system = MARKDOWN_ONLY_SYSTEM_PROMPT

    # Build schema description
    schema_desc = generate_schema_description(schema_class)

    # Build main prompt
    prompt = f"""{system}

## Required Schema
{schema_desc}

## Document Content (Markdown)
```markdown
{gemini_input.markdown}
```
"""

    # Add retry context if applicable
    if previous_attempts and errors:
        prompt += f"""
## Previous Attempt (FAILED)
The previous extraction was rejected. Analyze the errors and correct.

### Previous Output
```json
{json.dumps(previous_attempts[-1], indent=2, ensure_ascii=False)}
```

### Validation Errors
{chr(10).join(f"- {e}" for e in errors)}

### Instructions
1. Identify WHY each error occurred
2. Re-examine the document (especially the Image if provided)
3. Provide corrected JSON addressing ALL errors
"""

    prompt += """
## Output
Return ONLY valid JSON. No markdown code fences. No explanations.
"""

    return prompt


# ============================================================
# Prompt Variants
# ============================================================


def build_correction_prompt(
    markdown: str,
    schema_class: type[BaseModel],
    previous_attempts: list[dict],
    errors: list[str],
    include_image: bool = False,
    escalation_note: str | None = None,
) -> str:
    """Build a self-correction prompt for retry attempts.

    Used when previous extraction failed validation. Includes error
    analysis and correction instructions.

    Args:
        markdown: Document markdown content
        schema_class: Pydantic model class for schema
        previous_attempts: List of previous extraction attempts
        errors: Validation errors from previous attempts
        include_image: Whether image is included in input
        escalation_note: Optional note for Pro escalation context

    Returns:
        Correction prompt string

    Examples:
        >>> prompt = build_correction_prompt(
        ...     markdown="# Invoice...",
        ...     schema_class=DeliveryNoteV2,
        ...     previous_attempts=[{"management_id": ""}],
        ...     errors=["management_id: Required field is empty"]
        ... )
    """
    # Select system prompt
    system = MULTIMODAL_SYSTEM_PROMPT if include_image else MARKDOWN_ONLY_SYSTEM_PROMPT

    # Build schema description
    schema_desc = generate_schema_description(schema_class)

    # Start prompt
    prompt = f"""{system}

## Required Schema
{schema_desc}

## Document Content (Markdown)
```markdown
{markdown}
```

## Previous Attempt (FAILED)
The previous extraction was rejected. Analyze the errors and correct.

### Previous Output
```json
{json.dumps(previous_attempts[-1], indent=2, ensure_ascii=False)}
```

### Validation Errors
{chr(10).join(f"- {e}" for e in errors)}

### Instructions
1. Identify WHY each error occurred
2. Re-examine the document (especially the Image if provided)
3. Provide corrected JSON addressing ALL errors
"""

    # Add escalation note if Pro model
    if escalation_note:
        prompt += f"""
### Escalation Note
{escalation_note}
"""

    prompt += """
## Output
Return ONLY valid JSON. No markdown code fences. No explanations.
"""

    return prompt


def build_initial_prompt(
    markdown: str,
    schema_class: type[BaseModel],
    include_image: bool = False,
) -> str:
    """Build initial extraction prompt (first attempt).

    Used for the first extraction attempt without any previous context.

    Args:
        markdown: Document markdown content
        schema_class: Pydantic model class for schema
        include_image: Whether image is included in input

    Returns:
        Initial extraction prompt string

    Examples:
        >>> prompt = build_initial_prompt(
        ...     markdown="# Invoice...",
        ...     schema_class=DeliveryNoteV2,
        ...     include_image=True
        ... )
    """
    # Select system prompt
    system = MULTIMODAL_SYSTEM_PROMPT if include_image else MARKDOWN_ONLY_SYSTEM_PROMPT

    # Build schema description
    schema_desc = generate_schema_description(schema_class)

    prompt = f"""{system}

## Required Schema
{schema_desc}

## Document Content (Markdown)
```markdown
{markdown}
```

## Output
Return ONLY valid JSON. No markdown code fences. No explanations.
"""

    return prompt
