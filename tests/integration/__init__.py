"""Integration tests for AI-OCR Smart Pipeline.

Integration tests require external dependencies:
- Firestore emulator
- GCS emulator (or staging bucket)
- Document AI API access (or mocks)
- Gemini API access (or mocks)

Run with: pytest tests/integration -m integration
"""
