# Doc AI Confidence & Conditional Image Attachment

**Spec ID**: 04  
**Status**: Final  
**Dependencies**: Document AI, Gemini API

---

## 1. Design Philosophy

**Cost-Performance Balance**

| Input Mode | Token Cost | Use Case |
|------------|------------|----------|
| Markdown only | ~2K tokens | Default, high-confidence OCR |
| Markdown + Image | ~10K tokens | Low confidence, retries |

Image attachment increases cost 5x. Use conditionally.

---

## 2. Document AI to Gemini Pipeline

### 2.1 Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│              DOCUMENT AI → GEMINI PIPELINE                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PDF/Image                                                  │
│     │                                                       │
│     ▼                                                       │
│  ┌─────────────────┐                                       │
│  │  Document AI    │                                       │
│  │  Layout Parser  │                                       │
│  └────────┬────────┘                                       │
│           │                                                 │
│           ▼                                                 │
│  Document AI Response:                                      │
│  - pages[].paragraphs[].text                               │
│  - pages[].tables[].rows[].cells[].text                    │
│  - pages[].blocks[].layout.confidence                      │
│  - pages[].detected_languages[]                            │
│           │                                                 │
│           ▼                                                 │
│  ┌─────────────────┐                                       │
│  │ reconstruct_    │                                       │
│  │ markdown()      │                                       │
│  └────────┬────────┘                                       │
│           │                                                 │
│           ▼                                                 │
│  Structured Markdown:                                       │
│  - Paragraphs as text blocks                               │
│  - Tables as Markdown table syntax                         │
│  - Reading order preserved                                  │
│           │                                                 │
│           ▼                                                 │
│  ┌─────────────────┐                                       │
│  │ prepare_gemini_ │                                       │
│  │ input()         │──────▶ Attach image? (see §3)        │
│  └────────┬────────┘                                       │
│           │                                                 │
│           ▼                                                 │
│  GeminiInput(markdown, image?, confidence)                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Markdown Reconstruction

```python
from google.cloud import documentai_v1 as documentai
from typing import List

def reconstruct_markdown(document: documentai.Document) -> str:
    """
    Convert Document AI output to structured Markdown.
    
    Preserves:
    - Reading order (top-to-bottom, left-to-right)
    - Table structure
    - Paragraph boundaries
    
    Returns:
        Markdown string ready for Gemini
    """
    markdown_parts: List[str] = []
    
    for page_idx, page in enumerate(document.pages):
        if page_idx > 0:
            markdown_parts.append("\n---\n")  # Page separator
        
        # Sort blocks by vertical position, then horizontal
        sorted_blocks = sorted(
            _get_all_blocks(page),
            key=lambda b: (
                b.layout.bounding_poly.vertices[0].y,
                b.layout.bounding_poly.vertices[0].x
            )
        )
        
        for block in sorted_blocks:
            if hasattr(block, 'table'):
                # Convert table to Markdown
                markdown_parts.append(_table_to_markdown(block.table, document.text))
            else:
                # Extract text content
                text = _get_text_from_layout(block.layout, document.text)
                if text.strip():
                    markdown_parts.append(text.strip())
    
    return "\n\n".join(markdown_parts)


def _get_all_blocks(page: documentai.Document.Page):
    """Get all content blocks from a page."""
    blocks = []
    
    # Paragraphs
    for para in page.paragraphs:
        blocks.append(para)
    
    # Tables
    for table in page.tables:
        blocks.append(table)
    
    return blocks


def _get_text_from_layout(
    layout: documentai.Document.Page.Layout,
    full_text: str
) -> str:
    """
    Extract text from layout using text anchors.
    
    Document AI stores all text in document.text,
    with layouts referencing via start/end indices.
    """
    text_parts = []
    
    for segment in layout.text_anchor.text_segments:
        start = int(segment.start_index) if segment.start_index else 0
        end = int(segment.end_index)
        text_parts.append(full_text[start:end])
    
    return "".join(text_parts)


def _table_to_markdown(
    table: documentai.Document.Page.Table,
    full_text: str
) -> str:
    """
    Convert Document AI table to Markdown table syntax.
    
    Example output:
    | Header1 | Header2 |
    |---------|---------|
    | Cell1   | Cell2   |
    """
    rows: List[List[str]] = []
    
    # Header rows
    for header_row in table.header_rows:
        row_cells = []
        for cell in header_row.cells:
            cell_text = _get_text_from_layout(cell.layout, full_text)
            row_cells.append(cell_text.strip().replace("|", "\\|"))
        rows.append(row_cells)
    
    # Body rows
    for body_row in table.body_rows:
        row_cells = []
        for cell in body_row.cells:
            cell_text = _get_text_from_layout(cell.layout, full_text)
            row_cells.append(cell_text.strip().replace("|", "\\|"))
        rows.append(row_cells)
    
    if not rows:
        return ""
    
    # Build Markdown
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
```

---

## 3. Confidence Evaluation

### 3.1 Metric Source

Document AI returns confidence at multiple levels:
- `Page.confidence`: Overall page quality
- `Block.confidence`: Individual text block quality

**Strategy**: Use minimum of both (conservative).

### 3.2 Implementation

```python
from google.cloud import documentai_v1 as documentai

def evaluate_confidence(document: documentai.Document) -> float:
    """
    Returns the minimum confidence across all pages and blocks.
    
    Conservative approach: if ANY part is uncertain, 
    flag the whole document for image attachment.
    """
    min_confidence = 1.0
    
    for page in document.pages:
        # Page-level confidence
        if hasattr(page, 'confidence') and page.confidence < min_confidence:
            min_confidence = page.confidence
        
        # Block-level confidence
        for block in page.blocks:
            if hasattr(block.layout, 'confidence'):
                if block.layout.confidence < min_confidence:
                    min_confidence = block.layout.confidence
    
    return min_confidence
```

---

## 4. Image Attachment Decision

### 4.1 Threshold

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `CONFIDENCE_THRESHOLD` | 0.85 | Empirical starting point |

**Note**: Adjust based on production data. Track correlation between confidence and extraction success.

### 4.2 FRAGILE_TYPES Detection

Fragile document types require image attachment due to known OCR difficulties:

```python
import re
from typing import Optional

FRAGILE_TYPES = {"fax", "handwritten", "thermal_receipt", "carbon_copy", "low_res_scan"}

# Filename patterns for fragile type detection
FRAGILE_PATTERNS = {
    r"(?i)fax|ファクス|ファックス": "fax",
    r"(?i)手書き|handwrit": "handwritten",
    r"(?i)レシート|receipt|領収": "thermal_receipt",
    r"(?i)複写|carbon|カーボン": "carbon_copy",
    r"(?i)scan.*(?:72|96)dpi|低解像度": "low_res_scan",
}

def detect_fragile_type(
    filename: str,
    document: Optional[documentai.Document] = None
) -> Optional[str]:
    """
    Detect if document is a fragile type requiring image attachment.
    
    Detection methods:
    1. Filename pattern matching
    2. Document AI detected features (future)
    
    Args:
        filename: Original filename
        document: Optional Document AI response for feature-based detection
        
    Returns:
        Fragile type string or None if not fragile
    """
    # Method 1: Filename pattern matching
    for pattern, fragile_type in FRAGILE_PATTERNS.items():
        if re.search(pattern, filename):
            return fragile_type
    
    # Method 2: Document AI hints (if available)
    if document:
        # Check for handwriting detection
        for page in document.pages:
            for block in page.blocks:
                # Document AI may flag detected handwriting
                if hasattr(block, 'detected_handwriting') and block.detected_handwriting:
                    return "handwritten"
        
        # Check for very low confidence (possible scan quality issue)
        min_conf = evaluate_confidence(document)
        if min_conf < 0.5:
            return "low_res_scan"
    
    return None
```

### 4.3 Trigger Conditions

Include original image when:

1. **Confidence below threshold**: `min_confidence < 0.85`
2. **Gate Linter failed**: Previous attempt rejected
3. **Fragile document type**: Detected via filename or Document AI
4. **Retry attempt**: `attempt > 0`

### 4.4 Implementation

```python
from dataclasses import dataclass
from typing import Optional, Set
import base64

CONFIDENCE_THRESHOLD = 0.85

FRAGILE_DOCUMENT_TYPES: Set[str] = {
    "fax",
    "handwritten",
    "thermal_receipt",
    "carbon_copy",
    "low_res_scan"
}

@dataclass
class GeminiInput:
    """Input package for Gemini API call."""
    markdown: str
    image_base64: Optional[str] = None
    include_image: bool = False
    reason: Optional[str] = None

def prepare_gemini_input(
    document: documentai.Document,
    original_image: bytes,
    filename: str,
    gate_linter_failed: bool = False,
    attempt_number: int = 0
) -> GeminiInput:
    """
    Determine whether to include original image in Gemini request.
    
    Default: Markdown only (cost-efficient)
    Include image when:
      1. Gate Linter previously failed
      2. Doc AI confidence < 0.85
      3. Document type is detected as fragile
      4. Retry attempt (attempt > 0)
    
    Returns:
        GeminiInput with markdown and optional image
    """
    markdown = reconstruct_markdown(document)
    confidence = evaluate_confidence(document)
    fragile_type = detect_fragile_type(filename, document)
    
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
        reason=reason
    )
    
    if include_image:
        gemini_input.image_base64 = base64.b64encode(original_image).decode("utf-8")
    
    return gemini_input
```

---

## 5. Vision/Markdown Priority (Prompt Engineering)

### 4.1 Problem

When both Markdown and Image are sent, Gemini may see conflicting information:
- Markdown: "山田商事" (OCR result)
- Image: "山口商事" (actual text, smudged)

Which should Gemini trust?

### 4.2 Priority Rules

| Aspect | Trust Source | Rationale |
|--------|--------------|-----------|
| Structure (table layout, field position) | Markdown | Doc AI spatial analysis is reliable |
| Text details (characters, smudges) | Image | Human-like visual inspection |
| Conflict resolution | See rules below | Context-dependent |

### 4.3 System Prompt

```python
# core/prompts.py

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
```

### 4.4 Prompt Builder

```python
def build_extraction_prompt(
    gemini_input: GeminiInput,
    schema_class: type,
    previous_attempts: Optional[List[dict]] = None,
    errors: Optional[List[str]] = None
) -> str:
    """
    Build the complete prompt for Gemini.
    
    Adapts based on:
    - Whether image is included
    - Whether this is a retry
    - Previous extraction errors
    """
    # Select system prompt
    if gemini_input.include_image:
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
```

---

## 6. Cost Analysis

### 5.1 Per-Document Cost Estimate

| Scenario | Flash Cost | Pro Cost |
|----------|------------|----------|
| Markdown only, success | $0.0001 | N/A |
| Markdown + Image, success | $0.001 | N/A |
| Markdown → retry → Image | $0.0011 | N/A |
| Flash fail → Pro (Markdown) | $0.0001 | $0.005 |
| Flash fail → Pro (Image) | $0.001 | $0.02 |

### 5.2 Monthly Projection (100 docs)

| Scenario | Estimated Cost |
|----------|----------------|
| 95% success, 5% retry | ~$0.02 |
| 80% success, 15% Pro | ~$0.80 |
| 70% success, 20% Pro | ~$1.10 |

**Note**: Costs are estimates. Verify with actual API pricing.

---

## 7. Confidence Threshold Tuning

### 6.1 Data Collection

Track for each document:
```python
@dataclass
class ConfidenceMetrics:
    doc_hash: str
    doc_ai_confidence: float
    image_attached: bool
    extraction_success: bool
    model_used: str  # flash | pro
    gate_errors: List[str]
```

### 6.2 Analysis Query

```sql
-- Find optimal threshold
SELECT
  FLOOR(doc_ai_confidence * 20) / 20 AS confidence_bucket,
  COUNT(*) AS total,
  SUM(CASE WHEN extraction_success THEN 1 ELSE 0 END) AS success,
  SUM(CASE WHEN extraction_success THEN 1 ELSE 0 END) / COUNT(*) AS success_rate
FROM confidence_metrics
WHERE NOT image_attached  -- Markdown-only attempts
GROUP BY 1
ORDER BY 1;
```

### 6.3 Threshold Adjustment

If success rate drops below 90% at confidence X:
- Set `CONFIDENCE_THRESHOLD = X + 0.05`
- Monitor for 2 weeks
- Repeat

---

## 8. Monitoring

### Metrics

| Metric | Alert Threshold |
|--------|-----------------|
| Image attachment rate | >30% (cost concern) |
| Low confidence rate | >20% (OCR quality issue) |
| Confidence-success correlation | r < 0.7 (threshold needs tuning) |

### Log Events

```python
log_processing_event(
    "confidence_evaluated",
    doc_hash=hash,
    confidence=0.82,
    threshold=0.85,
    image_attached=True,
    reason="low_confidence:0.820"
)

log_processing_event(
    "vision_markdown_conflict",
    doc_hash=hash,
    field="company_name",
    markdown_value="山田商事",
    image_value="山口商事",
    resolution="image_preferred"
)
```
