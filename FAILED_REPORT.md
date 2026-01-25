# Processing Failed Report

## Document Information
- **Hash**: `sha256:d0c5783901b128af3ca02551faba686424fcd0b57301fad5839db21314a90734`
- **Source**: `gs://ai-ocr-smart-pipeline-ocr-input-staging/test_納品書_山田商事2.pdf`
- **Failed At**: 2026-01-25T09:49:47.448269+00:00

## Extraction Attempts

### Attempt 1
```json
"ExtractionAttempt(model='flash', prompt_tokens=2000, output_tokens=41, cost_usd=0.000265375, error=None, data={'management_id': 'DN-2025-0001', 'company_name': '株式会社テスト', 'issue_date': '2025-01-25', 'delivery_date': '2025-01-25', 'total_amount': 20000})"
```

## Validation Errors
- Unexpected error: TypeError: ('Cannot convert to a Firestore Value', datetime.date(2025, 1, 25), 'Invalid type', <class 'datetime.date'>)

## Required Action
Manual review required in the Review UI.

[Open in Review UI](https://review.example.com/document/sha256:d0c5783901b128af3ca02551faba686424fcd0b57301fad5839db21314a90734)
