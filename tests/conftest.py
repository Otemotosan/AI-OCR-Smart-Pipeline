"""Pytest configuration and fixtures."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add src directory to Python path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


# ============================================================
# Mock Clients
# ============================================================


@pytest.fixture
def mock_firestore_client():
    """Mock Firestore client for testing.

    Returns:
        Mock Firestore client with collection/document structure
    """
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_document = MagicMock()
    mock_snapshot = MagicMock()

    # Setup chain: client.collection().document()
    mock_client.collection.return_value = mock_collection
    mock_collection.document.return_value = mock_document
    mock_document.get.return_value = mock_snapshot

    return mock_client


@pytest.fixture
def mock_gcs_client():
    """Mock Google Cloud Storage client for testing.

    Returns:
        Mock GCS client with bucket/blob structure
    """
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_blob = MagicMock()

    # Setup chain: client.bucket().blob()
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.blob.return_value = mock_blob

    return mock_client


# ============================================================
# Sample Data
# ============================================================


@pytest.fixture
def sample_delivery_note_v2():
    """Sample DeliveryNoteV2 data for testing.

    Returns:
        Dictionary with valid delivery note data
    """
    return {
        "management_id": "DN-2025-001",
        "company_name": "テスト株式会社",
        "issue_date": date(2025, 1, 13),
        "delivery_date": date(2025, 1, 15),
        "payment_due_date": date(2025, 2, 15),
        "total_amount": 150000,
        "document_type": "delivery_note",
    }


@pytest.fixture
def sample_invoice_v1():
    """Sample InvoiceV1 data for testing.

    Returns:
        Dictionary with valid invoice data
    """
    return {
        "management_id": "INV-2025-001",
        "company_name": "サンプル商事株式会社",
        "issue_date": date(2025, 1, 13),
        "payment_due_date": date(2025, 2, 28),
        "total_amount": 250000,
        "tax_amount": 25000,
        "document_type": "invoice",
    }


@pytest.fixture
def sample_markdown_output():
    """Sample Document AI markdown output for testing.

    Returns:
        Markdown string simulating Document AI output
    """
    return """# 納品書

管理番号: DN-2025-001
会社名: テスト株式会社
発行日: 2025年1月13日
納品日: 2025年1月15日
支払期限: 2025年2月15日

## 明細

| 品名 | 数量 | 単価 | 金額 |
|------|------|------|------|
| 商品A | 10 | 10,000 | 100,000 |
| 商品B | 5 | 10,000 | 50,000 |

**合計金額**: ¥150,000
"""


@pytest.fixture
def sample_gemini_response():
    """Sample Gemini JSON response for testing.

    Returns:
        Dictionary simulating Gemini extraction output
    """
    return {
        "management_id": "DN-2025-001",
        "company_name": "テスト株式会社",
        "issue_date": "2025-01-13",
        "delivery_date": "2025-01-15",
        "payment_due_date": "2025-02-15",
        "total_amount": 150000,
        "document_type": "delivery_note",
    }


# ============================================================
# Test Helpers
# ============================================================


@pytest.fixture
def create_mock_snapshot():
    """Factory fixture for creating mock Firestore snapshots.

    Returns:
        Function that creates configured mock snapshots
    """

    def _create(exists: bool = True, data: dict | None = None):
        snapshot = MagicMock()
        snapshot.exists = exists
        if data:
            snapshot.to_dict.return_value = data
        return snapshot

    return _create
