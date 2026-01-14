"""Unit tests for Budget Manager."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from core.budget import (
    BUDGET_TIMEZONE,
    PRO_DAILY_LIMIT,
    PRO_MONTHLY_LIMIT,
    BudgetManager,
    ProBudgetExhaustedError,
)

# ============================================================
# Budget Checking Tests
# ============================================================


class TestBudgetChecking:
    """Test budget availability checking."""

    def test_check_budget_no_prior_usage(self) -> None:
        """Test budget check with no prior usage."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock no existing document
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)
        result = budget.check_pro_budget()

        assert result is True

    def test_check_budget_within_limits(self) -> None:
        """Test budget check when within both limits."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock existing usage within limits
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "daily": {"2025-01-13": 25},  # Below 50
            "monthly": {"2025-01": 500},  # Below 1000
        }
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)

        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
        ):
            result = budget.check_pro_budget()

        assert result is True

    def test_check_budget_daily_limit_reached(self) -> None:
        """Test budget check when daily limit reached."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock daily limit reached
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "daily": {"2025-01-13": 50},  # At limit
            "monthly": {"2025-01": 500},
        }
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)

        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
        ):
            result = budget.check_pro_budget()

        assert result is False

    def test_check_budget_daily_limit_exceeded(self) -> None:
        """Test budget check when daily limit exceeded."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock daily limit exceeded
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "daily": {"2025-01-13": 55},  # Over limit
            "monthly": {"2025-01": 500},
        }
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)

        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
        ):
            result = budget.check_pro_budget()

        assert result is False

    def test_check_budget_monthly_limit_reached(self) -> None:
        """Test budget check when monthly limit reached."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock monthly limit reached
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "daily": {"2025-01-13": 25},
            "monthly": {"2025-01": 1000},  # At limit
        }
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)

        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
        ):
            result = budget.check_pro_budget()

        assert result is False

    def test_check_budget_both_limits_exceeded(self) -> None:
        """Test budget check when both limits exceeded."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock both limits exceeded
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "daily": {"2025-01-13": 60},
            "monthly": {"2025-01": 1100},
        }
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)

        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
        ):
            result = budget.check_pro_budget()

        assert result is False


# ============================================================
# Increment Tests
# ============================================================


class TestIncrement:
    """Test usage increment operations."""

    def test_increment_pro_usage(self) -> None:
        """Test incrementing Pro usage counters."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        budget = BudgetManager(mock_db)

        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
        ):
            budget.increment_pro_usage()

        # Verify set was called with correct structure
        mock_doc_ref.set.assert_called_once()
        call_args = mock_doc_ref.set.call_args

        # Check that daily and monthly keys were set
        assert "daily" in call_args[0][0]
        assert "monthly" in call_args[0][0]
        assert "last_updated" in call_args[0][0]
        assert call_args[1]["merge"] is True

    def test_increment_creates_atomic_operation(self) -> None:
        """Test that increment uses Firestore atomic increment."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        budget = BudgetManager(mock_db)

        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
        ):
            budget.increment_pro_usage()

        # Verify set was called with merge=True
        mock_doc_ref.set.assert_called_once()
        call_args = mock_doc_ref.set.call_args
        assert call_args[1]["merge"] is True

        # Verify structure contains daily/monthly/last_updated
        data = call_args[0][0]
        assert "daily" in data
        assert "monthly" in data
        assert "last_updated" in data
        assert "2025-01-13" in data["daily"]
        assert "2025-01" in data["monthly"]


# ============================================================
# Get Usage Tests
# ============================================================


class TestGetUsage:
    """Test usage retrieval methods."""

    def test_get_daily_usage_no_data(self) -> None:
        """Test getting daily usage with no prior data."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock no existing document
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)
        result = budget.get_daily_usage()

        assert result == 0

    def test_get_daily_usage_with_data(self) -> None:
        """Test getting daily usage with existing data."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock existing usage
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "daily": {"2025-01-13": 15, "2025-01-12": 20},
            "monthly": {"2025-01": 500},
        }
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)

        with patch.object(budget, "_get_budget_date", return_value="2025-01-13"):
            result = budget.get_daily_usage()

        assert result == 15

    def test_get_monthly_usage_no_data(self) -> None:
        """Test getting monthly usage with no prior data."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock no existing document
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)
        result = budget.get_monthly_usage()

        assert result == 0

    def test_get_monthly_usage_with_data(self) -> None:
        """Test getting monthly usage with existing data."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock existing usage
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "daily": {"2025-01-13": 15},
            "monthly": {"2025-01": 500, "2024-12": 800},
        }
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)

        with patch.object(budget, "_get_budget_month", return_value="2025-01"):
            result = budget.get_monthly_usage()

        assert result == 500

    def test_get_daily_usage_missing_date_key(self) -> None:
        """Test getting daily usage when current date key doesn't exist."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock existing usage but not for today
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "daily": {"2025-01-12": 20},  # Different date
            "monthly": {"2025-01": 500},
        }
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)

        with patch.object(budget, "_get_budget_date", return_value="2025-01-13"):
            result = budget.get_daily_usage()

        assert result == 0  # Should return 0 for missing date key


# ============================================================
# Usage Statistics Tests
# ============================================================


class TestUsageStatistics:
    """Test comprehensive usage statistics."""

    def test_get_usage_stats_no_data(self) -> None:
        """Test usage stats with no prior data."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock no existing document
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)

        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
        ):
            stats = budget.get_usage_stats()

        assert stats["daily"] == 0
        assert stats["daily_limit"] == PRO_DAILY_LIMIT
        assert stats["daily_remaining"] == PRO_DAILY_LIMIT
        assert stats["monthly"] == 0
        assert stats["monthly_limit"] == PRO_MONTHLY_LIMIT
        assert stats["monthly_remaining"] == PRO_MONTHLY_LIMIT
        assert stats["date"] == "2025-01-13"
        assert stats["month"] == "2025-01"

    def test_get_usage_stats_with_data(self) -> None:
        """Test usage stats with existing data."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock existing usage
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "daily": {"2025-01-13": 15},
            "monthly": {"2025-01": 500},
        }
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)

        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
        ):
            stats = budget.get_usage_stats()

        assert stats["daily"] == 15
        assert stats["daily_limit"] == 50
        assert stats["daily_remaining"] == 35
        assert stats["monthly"] == 500
        assert stats["monthly_limit"] == 1000
        assert stats["monthly_remaining"] == 500

    def test_get_usage_stats_at_limit(self) -> None:
        """Test usage stats when at exact limits."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock at limits
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "daily": {"2025-01-13": 50},
            "monthly": {"2025-01": 1000},
        }
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)

        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
        ):
            stats = budget.get_usage_stats()

        assert stats["daily"] == 50
        assert stats["daily_remaining"] == 0
        assert stats["monthly"] == 1000
        assert stats["monthly_remaining"] == 0

    def test_get_usage_stats_over_limit(self) -> None:
        """Test usage stats when over limits (remaining never negative)."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock over limits
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "daily": {"2025-01-13": 60},
            "monthly": {"2025-01": 1100},
        }
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)

        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
        ):
            stats = budget.get_usage_stats()

        assert stats["daily"] == 60
        assert stats["daily_remaining"] == 0  # Never negative
        assert stats["monthly"] == 1100
        assert stats["monthly_remaining"] == 0  # Never negative


# ============================================================
# Timezone Tests
# ============================================================


class TestTimezone:
    """Test JST timezone handling."""

    def test_budget_timezone_is_jst(self) -> None:
        """Test that budget timezone is Asia/Tokyo."""
        assert ZoneInfo("Asia/Tokyo") == BUDGET_TIMEZONE

    def test_get_budget_date_returns_jst_date(self) -> None:
        """Test that budget date is in JST timezone."""
        mock_db = MagicMock()
        budget = BudgetManager(mock_db)

        # Mock a specific JST datetime
        with patch("core.budget.datetime") as mock_datetime:
            # January 13, 2025, 23:30 JST (almost midnight)
            mock_now = datetime(2025, 1, 13, 23, 30, 0, tzinfo=BUDGET_TIMEZONE)
            mock_datetime.now.return_value = mock_now

            date = budget._get_budget_date()

        assert date == "2025-01-13"

    def test_get_budget_month_returns_jst_month(self) -> None:
        """Test that budget month is in JST timezone."""
        mock_db = MagicMock()
        budget = BudgetManager(mock_db)

        # Mock a specific JST datetime
        with patch("core.budget.datetime") as mock_datetime:
            # January 31, 2025, 23:30 JST (almost end of month)
            mock_now = datetime(2025, 1, 31, 23, 30, 0, tzinfo=BUDGET_TIMEZONE)
            mock_datetime.now.return_value = mock_now

            month = budget._get_budget_month()

        assert month == "2025-01"

    def test_timezone_boundary_date_change(self) -> None:
        """Test date change at JST midnight vs UTC midnight."""
        mock_db = MagicMock()
        budget = BudgetManager(mock_db)

        # January 13, 2025, 00:30 JST (after JST midnight, before UTC midnight)
        # This is still January 12 in UTC
        with patch("core.budget.datetime") as mock_datetime:
            mock_now = datetime(2025, 1, 13, 0, 30, 0, tzinfo=BUDGET_TIMEZONE)
            mock_datetime.now.return_value = mock_now

            date = budget._get_budget_date()

        # Should use JST date (Jan 13), not UTC date (Jan 12)
        assert date == "2025-01-13"


# ============================================================
# Constants Tests
# ============================================================


class TestConstants:
    """Test module constants."""

    def test_pro_daily_limit(self) -> None:
        """Test PRO_DAILY_LIMIT constant."""
        assert PRO_DAILY_LIMIT == 50

    def test_pro_monthly_limit(self) -> None:
        """Test PRO_MONTHLY_LIMIT constant."""
        assert PRO_MONTHLY_LIMIT == 1000

    def test_pro_budget_exhausted_error(self) -> None:
        """Test ProBudgetExhaustedError exception."""
        with pytest.raises(ProBudgetExhaustedError):
            raise ProBudgetExhaustedError("Budget exceeded")


# ============================================================
# Integration Scenarios
# ============================================================


class TestIntegrationScenarios:
    """Test realistic usage scenarios."""

    def test_typical_usage_flow(self) -> None:
        """Test typical check-increment-check flow."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Initial state: no usage
        mock_snapshot1 = MagicMock()
        mock_snapshot1.exists = False

        # After increment: usage = 1
        mock_snapshot2 = MagicMock()
        mock_snapshot2.exists = True
        mock_snapshot2.to_dict.return_value = {
            "daily": {"2025-01-13": 1},
            "monthly": {"2025-01": 1},
        }

        mock_doc_ref.get.side_effect = [mock_snapshot1, mock_snapshot2]

        budget = BudgetManager(mock_db)

        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
        ):
            # Check budget (should be available)
            assert budget.check_pro_budget() is True

            # Increment usage
            budget.increment_pro_usage()

            # Check again (should still be available)
            assert budget.check_pro_budget() is True

    def test_daily_limit_enforcement(self) -> None:
        """Test that daily limit is enforced correctly."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        budget = BudgetManager(mock_db)

        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
        ):
            # Simulate approaching limit
            for count in range(48, 52):
                mock_snapshot = MagicMock()
                mock_snapshot.exists = True
                mock_snapshot.to_dict.return_value = {
                    "daily": {"2025-01-13": count},
                    "monthly": {"2025-01": count},
                }
                mock_doc_ref.get.return_value = mock_snapshot

                result = budget.check_pro_budget()

                if count < 50:
                    assert result is True, f"Should allow at count {count}"
                else:
                    assert result is False, f"Should block at count {count}"

    def test_new_day_resets_daily_counter(self) -> None:
        """Test that daily counter naturally resets with new date."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock usage from previous day
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "daily": {"2025-01-12": 50},  # Previous day at limit
            "monthly": {"2025-01": 500},
        }
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)

        # Check on new day
        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
        ):
            result = budget.check_pro_budget()

        # Should be available (new date key)
        assert result is True

    def test_new_month_resets_monthly_counter(self) -> None:
        """Test that monthly counter naturally resets with new month."""
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        # Mock usage from previous month
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {
            "daily": {"2025-02-01": 10},
            "monthly": {"2025-01": 1000},  # Previous month at limit
        }
        mock_doc_ref.get.return_value = mock_snapshot

        budget = BudgetManager(mock_db)

        # Check in new month
        with (
            patch.object(budget, "_get_budget_date", return_value="2025-02-01"),
            patch.object(budget, "_get_budget_month", return_value="2025-02"),
        ):
            result = budget.check_pro_budget()

        # Should be available (new month key)
        assert result is True


# ============================================================
# Fallback and Edge Cases
# ============================================================


class TestFallbackBehavior:
    """Test fallback behavior when google-cloud-firestore is not available."""

    def test_increment_with_import_error_fallback(self) -> None:
        """Test that increment works with fallback when Firestore import fails."""

        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        budget = BudgetManager(mock_db)

        # Create a custom importer that blocks google.cloud.firestore
        original_import = __import__

        def mock_import(name, *args, **kwargs):
            if name == "google.cloud.firestore":
                raise ImportError("Mocked import error for testing fallback")
            return original_import(name, *args, **kwargs)

        with (
            patch.object(budget, "_get_budget_date", return_value="2025-01-13"),
            patch.object(budget, "_get_budget_month", return_value="2025-01"),
            patch("builtins.__import__", mock_import),
        ):
            # Should still work with fallback (Increment returns plain int)
            budget.increment_pro_usage()

        # Verify set was called
        call_args = mock_doc_ref.set.call_args
        assert call_args is not None
        data = call_args[0][0]
        assert "daily" in data
        assert "monthly" in data

    def test_reset_if_needed_no_op(self) -> None:
        """Test reset_if_needed is a no-op (counters reset naturally)."""
        mock_db = MagicMock()
        budget = BudgetManager(mock_db)

        # Reset mock calls from __init__
        mock_db.reset_mock()

        # Should not raise any errors
        budget.reset_if_needed()

        # No additional Firestore operations should occur
        mock_db.collection.assert_not_called()
        mock_db.collection.return_value.document.assert_not_called()
