# Processing Failed Report

## Document Information
- **Hash**: `sha256:ed6e0f52532b8c19d1f71276cb1dfb95cf48df80c3f58ba00761db04128f9fac`
- **Source**: `gs://ai-ocr-smart-pipeline-ocr-input-staging/invoice.pdf`
- **Failed At**: 2026-01-25T08:21:42.267664+00:00

## Extraction Attempts

### Attempt 1
```json
"ExtractionAttempt(model='flash', prompt_tokens=2000, output_tokens=51, cost_usd=0.000269125, error=None, data={'management_id': 'INV-2025-0456', 'company_name': '田中工業株式会社', 'issue_date': '2025-01-25', 'delivery_date': '2025-01-25', 'payment_due_date': '2025-02-28', 'total_amount': 330000})"
```

## Validation Errors
- Unexpected error: TypeError: ('Cannot convert to a Firestore Value', datetime.date(2025, 1, 25), 'Invalid type', <class 'datetime.date'>)

## Required Action
Manual review required in the Review UI.

[Open in Review UI](https://review.example.com/document/sha256:ed6e0f52532b8c19d1f71276cb1dfb95cf48df80c3f58ba00761db04128f9fac)
