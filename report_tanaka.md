# Processing Failed Report

## Document Information
- **Hash**: `sha256:ed6e0f52532b8c19d1f71276cb1dfb95cf48df80c3f58ba00761db04128f9fac`
- **Source**: `gs://ai-ocr-smart-pipeline-ocr-input-staging/test_請求書_田中工業1.pdf`
- **Failed At**: 2026-01-25T13:42:22.307361+00:00

## Extraction Attempts

### Attempt 1
```json
"ExtractionAttempt(model='flash', prompt_tokens=2000, output_tokens=49, cost_usd=0.000268375, error='Schema validation failed: 1 validation error for DeliveryNoteV2\\ndelivery_date\\n  Input should be a valid date [type=date_type, input_value=None, input_type=NoneType]\\n    For further information visit https://errors.pydantic.dev/2.12/v/date_type', data={'management_id': 'INV-2025-0456', 'company_name': '株式会社テスト', 'issue_date': '2025-01-25', 'delivery_date': None, 'payment_due_date': '2025-02-28', 'total_amount': 330000})"
```

## Validation Errors
- Saga failed at step: gcs_copy
- File not found: gs://ai-ocr-smart-pipeline-ocr-input-staging/test_請求書_田中工業1.pdf

## Required Action
Manual review required in the Review UI.

[Open in Review UI](https://review.example.com/document/sha256:ed6e0f52532b8c19d1f71276cb1dfb95cf48df80c3f58ba00761db04128f9fac)
