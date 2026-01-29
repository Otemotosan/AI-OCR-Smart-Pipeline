"""
Unit tests for DatabaseClient serialization logic.
Verifying fixes for datetime.date Firestore serialization bugs.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from src.core.database import AuditEventType, DatabaseClient


class TestDatabaseSerialization:
    """Tests for automatic datetime.date serialization in DatabaseClient."""

    @pytest.fixture
    def mock_firestore(self):
        client = MagicMock()
        client.collection.return_value.document.return_value = MagicMock()
        return client

    @pytest.fixture
    def db_client(self, mock_firestore):
        return DatabaseClient(mock_firestore)

    def test_save_extraction_converts_dates(self, db_client, mock_firestore):
        """Test that save_extraction converts date objects in attempts to strings."""
        doc_id = "test-hash"
        # attempts containing a date object that causes TypeError in Firestore
        attempts = [
            {
                "data": {"delivery_date": date(2025, 1, 25), "items": [{"date": date(2025, 2, 1)}]},
                "error": None,
            }
        ]
        extracted_data = {"invoice_date": date(2025, 1, 20)}

        db_client.save_extraction(
            doc_id=doc_id,
            extracted_data=extracted_data,
            attempts=attempts,
            schema_version="v1",
        )

        # Verify call arguments
        doc_ref = mock_firestore.collection.return_value.document.return_value
        doc_ref.update.assert_called_once()

        args = doc_ref.update.call_args[0][0]

        # Check extracted_data conversion
        assert args["extracted_data"]["invoice_date"] == "2025-01-20"

        # Check attempts conversion (THE BUG FIX)
        assert args["attempts"][0]["data"]["delivery_date"] == "2025-01-25"
        assert args["attempts"][0]["data"]["items"][0]["date"] == "2025-02-01"

    def test_log_audit_event_converts_dates(self, db_client, mock_firestore):
        """Test that log_audit_event converts date objects in details to strings."""
        doc_id = "test-hash"
        details = {"attempts": [{"date": date(2025, 3, 1)}], "error_date": date(2025, 3, 2)}

        db_client.log_audit_event(
            doc_id=doc_id,
            event=AuditEventType.FAILED,
            details=details,
        )

        # Verify call arguments
        collection = mock_firestore.collection.return_value
        collection.add.assert_called_once()

        args = collection.add.call_args[0][0]

        # Check details conversion (THE BUG FIX)
        assert args["details"]["attempts"][0]["date"] == "2025-03-01"
        assert args["details"]["error_date"] == "2025-03-02"
