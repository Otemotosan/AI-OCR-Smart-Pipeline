# Processing Failed Report

## Document Information
- **Hash**: `sha256:d0c5783901b128af3ca02551faba686424fcd0b57301fad5839db21314a90734`
- **Source**: `gs://ai-ocr-smart-pipeline-ocr-input-staging/test_納品書_山田商事2.pdf`
- **Failed At**: 2026-01-25T13:42:28.128034+00:00

## Extraction Attempts

### Attempt 1
```json
"ExtractionAttempt(model='flash', prompt_tokens=2000, output_tokens=311, cost_usd=0.000366625, error=\"Gate Linter failed: management_id: Required field is empty, company_name: Required field is empty, issue_date: Required field is missing, document_type: Unknown type 'OrderForm'. Valid types: ['delivery_note', 'invoice', 'generic', 'order_form']\", data={'schema_version': None, 'document_type': 'OrderForm', 'order_number': None, 'order_date': '2025-01-25', 'delivery_date': None, 'buyer_company': '株式会社テスト', 'buyer_contact': None, 'supplier_company': '山田商事株式会社', 'supplier_contact': None, 'items': [{'item_name': '製品A', 'quantity': 10, 'unit': None, 'unit_price': 1000, 'amount': 10000}, {'item_name': '製品B', 'quantity': 5, 'unit': None, 'unit_price': 2000, 'amount': 10000}], 'subtotal': None, 'tax_amount': None, 'total_amount': 20000, 'notes': None, 'extraction_notes': [\"The document header indicates '納品書' (Delivery Note), but extraction was performed based on the '注文書' (Order Form) schema as per instructions.\", \"The field '発行日' (Issue Date) was mapped to 'order_date' as no specific '注文日' (Order Date) was found.\", \"No explicit 'subtotal' or 'tax_amount' were found, so they are set to null.\", \"The '単位' (unit) for line items was not explicitly specified in the document and is set to null.\", \"The '納品番号' (Delivery Number) 'DN-2025-0001' was ignored as there is no corresponding 'order_number' field for a delivery number in the schema.\"]})"
```

## Validation Errors
- Saga failed at step: gcs_copy
- File not found: gs://ai-ocr-smart-pipeline-ocr-input-staging/test_納品書_山田商事2.pdf

## Required Action
Manual review required in the Review UI.

[Open in Review UI](https://review.example.com/document/sha256:d0c5783901b128af3ca02551faba686424fcd0b57301fad5839db21314a90734)
