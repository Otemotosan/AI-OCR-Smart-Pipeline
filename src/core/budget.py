"""Budget Manager for Pro API Usage Tracking.

Enforces daily and monthly limits for Gemini Pro API calls with JST timezone
alignment for business day budget resets.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from google.cloud import firestore

# Constants
PRO_DAILY_LIMIT = 50
PRO_MONTHLY_LIMIT = 1000
BUDGET_TIMEZONE = ZoneInfo("Asia/Tokyo")


class ProBudgetExhaustedError(Exception):
    """Raised when Pro call budget is exceeded."""


class BudgetManager:
    """Manage Pro API budget with daily and monthly limits.

    Uses Firestore backend with JST timezone for budget resets.
    Budget counters reset at JST midnight (daily) and month start (monthly).

    Examples:
        >>> budget = BudgetManager(firestore_client)
        >>> if budget.check_pro_budget():
        ...     # Call Pro API
        ...     budget.increment_pro_usage()
        >>> usage = budget.get_usage_stats()
        >>> print(f"Daily: {usage['daily']}/{usage['daily_limit']}")
    """

    def __init__(self, firestore_client: firestore.Client) -> None:
        """Initialize Budget Manager.

        Args:
            firestore_client: Firestore client instance
        """
        self.db = firestore_client
        self._budget_ref = self.db.collection("system_config").document("pro_budget")

    def check_pro_budget(self) -> bool:
        """Check if Pro calls are within budget limits.

        Returns:
            True if budget available (within daily AND monthly limits), False otherwise

        Examples:
            >>> if budget.check_pro_budget():
            ...     # Safe to call Pro API
            ...     budget.increment_pro_usage()
        """
        doc = self._budget_ref.get()

        if not doc.exists:
            return True  # No usage yet

        data = doc.to_dict()
        today = self._get_budget_date()
        month = self._get_budget_month()

        daily_count = data.get("daily", {}).get(today, 0)
        monthly_count = data.get("monthly", {}).get(month, 0)

        return not (
            daily_count >= PRO_DAILY_LIMIT or monthly_count >= PRO_MONTHLY_LIMIT
        )

    def increment_pro_usage(self) -> None:
        """Atomically increment Pro usage counters.

        Increments both daily and monthly counters using Firestore atomic increment.

        Examples:
            >>> budget.increment_pro_usage()
        """
        # Import at runtime to allow mocking in tests
        try:
            from google.cloud.firestore import Increment
        except ImportError:
            # Fallback for testing without google-cloud-firestore installed
            def Increment(x: int) -> int:  # noqa: N802
                return x

        today = self._get_budget_date()
        month = self._get_budget_month()

        self._budget_ref.set(
            {
                "daily": {today: Increment(1)},
                "monthly": {month: Increment(1)},
                "last_updated": datetime.now(BUDGET_TIMEZONE),
            },
            merge=True,
        )

    def get_daily_usage(self) -> int:
        """Get current daily Pro usage count.

        Returns:
            Number of Pro calls made today (JST timezone)

        Examples:
            >>> count = budget.get_daily_usage()
            >>> print(f"Used {count}/{PRO_DAILY_LIMIT} today")
        """
        doc = self._budget_ref.get()

        if not doc.exists:
            return 0

        data = doc.to_dict()
        today = self._get_budget_date()

        return data.get("daily", {}).get(today, 0)

    def get_monthly_usage(self) -> int:
        """Get current monthly Pro usage count.

        Returns:
            Number of Pro calls made this month (JST timezone)

        Examples:
            >>> count = budget.get_monthly_usage()
            >>> print(f"Used {count}/{PRO_MONTHLY_LIMIT} this month")
        """
        doc = self._budget_ref.get()

        if not doc.exists:
            return 0

        data = doc.to_dict()
        month = self._get_budget_month()

        return data.get("monthly", {}).get(month, 0)

    def get_usage_stats(self) -> dict:
        """Get comprehensive usage statistics.

        Returns:
            Dictionary with daily/monthly usage and limits

        Examples:
            >>> stats = budget.get_usage_stats()
            >>> print(stats)
            {
                'daily': 12,
                'daily_limit': 50,
                'daily_remaining': 38,
                'monthly': 245,
                'monthly_limit': 1000,
                'monthly_remaining': 755,
                'date': '2025-01-13',
                'month': '2025-01'
            }
        """
        daily = self.get_daily_usage()
        monthly = self.get_monthly_usage()

        return {
            "daily": daily,
            "daily_limit": PRO_DAILY_LIMIT,
            "daily_remaining": max(0, PRO_DAILY_LIMIT - daily),
            "monthly": monthly,
            "monthly_limit": PRO_MONTHLY_LIMIT,
            "monthly_remaining": max(0, PRO_MONTHLY_LIMIT - monthly),
            "date": self._get_budget_date(),
            "month": self._get_budget_month(),
        }

    def reset_if_needed(self) -> None:
        """Reset budget counters if needed.

        Note: With Firestore structure using date/month keys, counters
        naturally reset when date/month changes. This method is primarily
        for explicit reset operations or cleanup of old data.

        Examples:
            >>> budget.reset_if_needed()  # Clean up old date/month keys
        """
        # With current Firestore structure (date/month as keys),
        # counters naturally reset when accessing new date/month.
        # This method can be used for explicit cleanup of old keys
        # if storage becomes a concern, but is not required for normal operation.
        pass

    def _get_budget_date(self) -> str:
        """Get current date in budget timezone (JST).

        Returns:
            Date string in ISO format (YYYY-MM-DD)
        """
        return datetime.now(BUDGET_TIMEZONE).date().isoformat()

    def _get_budget_month(self) -> str:
        """Get current month in budget timezone (JST).

        Returns:
            Month string in format YYYY-MM
        """
        return datetime.now(BUDGET_TIMEZONE).strftime("%Y-%m")
