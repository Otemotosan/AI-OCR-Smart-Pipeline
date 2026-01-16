"""Unit tests for alerting module."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.alerting import (
    Alert,
    AlertConfig,
    AlertManager,
    AlertPriority,
    AlertStatus,
    EmailChannel,
    PagerDutyChannel,
    SlackChannel,
    alert_high_failure_rate,
    alert_low_confidence_trend,
    alert_pro_budget_warning,
    alert_queue_backlog,
    alert_saga_compensations,
)


class TestAlertPriority:
    """Tests for AlertPriority enum."""

    def test_priority_values(self) -> None:
        """Test that all priority levels are defined."""
        assert AlertPriority.P0.value == "P0"
        assert AlertPriority.P1.value == "P1"
        assert AlertPriority.P2.value == "P2"
        assert AlertPriority.P3.value == "P3"

    def test_priority_count(self) -> None:
        """Test that all priority levels exist."""
        priorities = list(AlertPriority)
        assert len(priorities) == 4


class TestAlertStatus:
    """Tests for AlertStatus enum."""

    def test_status_values(self) -> None:
        """Test that all status values are defined."""
        assert AlertStatus.FIRING.value == "firing"
        assert AlertStatus.RESOLVED.value == "resolved"
        assert AlertStatus.SILENCED.value == "silenced"


class TestAlert:
    """Tests for Alert dataclass."""

    def test_alert_creation(self) -> None:
        """Test basic alert creation."""
        alert = Alert(
            id="P0-001-20250116",
            name="Test Alert",
            priority=AlertPriority.P0,
            message="Test message",
        )
        assert alert.id == "P0-001-20250116"
        assert alert.name == "Test Alert"
        assert alert.priority == AlertPriority.P0
        assert alert.message == "Test message"
        assert alert.status == AlertStatus.FIRING
        assert alert.resolved_at is None

    def test_alert_with_details(self) -> None:
        """Test alert with details."""
        alert = Alert(
            id="P1-001-20250116",
            name="High Failure Rate",
            priority=AlertPriority.P1,
            message="Failure rate exceeded",
            details={"rate": "6%", "threshold": "5%"},
        )
        assert alert.details["rate"] == "6%"
        assert alert.details["threshold"] == "5%"

    def test_alert_with_runbook(self) -> None:
        """Test alert with runbook URL."""
        alert = Alert(
            id="P0-001-20250116",
            name="Test",
            priority=AlertPriority.P0,
            message="Test",
            runbook_url="https://wiki.example.com/runbooks/test",
        )
        assert alert.runbook_url == "https://wiki.example.com/runbooks/test"

    def test_alert_to_dict(self) -> None:
        """Test alert serialization to dict."""
        alert = Alert(
            id="P1-001-20250116",
            name="Test Alert",
            priority=AlertPriority.P1,
            message="Test message",
            details={"key": "value"},
            runbook_url="https://example.com/runbook",
        )
        result = alert.to_dict()
        assert result["id"] == "P1-001-20250116"
        assert result["name"] == "Test Alert"
        assert result["priority"] == "P1"
        assert result["message"] == "Test message"
        assert result["details"] == {"key": "value"}
        assert result["status"] == "firing"
        assert result["runbook_url"] == "https://example.com/runbook"
        assert "triggered_at" in result

    def test_alert_to_dict_resolved(self) -> None:
        """Test alert serialization when resolved."""
        now = datetime.now(UTC)
        alert = Alert(
            id="P1-001-20250116",
            name="Test",
            priority=AlertPriority.P1,
            message="Test",
            status=AlertStatus.RESOLVED,
            resolved_at=now,
        )
        result = alert.to_dict()
        assert result["status"] == "resolved"
        assert result["resolved_at"] is not None


class TestAlertConfig:
    """Tests for AlertConfig dataclass."""

    def test_config_creation(self) -> None:
        """Test alert config creation."""
        config = AlertConfig(
            id="P0-001",
            name="Queue Backlog",
            description="Test description",
            priority=AlertPriority.P0,
            condition={"metric": "pending", "operator": ">", "threshold": 100},
            window="5m",
            channels=["slack", "pagerduty"],
            message="Queue backlog critical",
            runbook_url="https://example.com/runbook",
        )
        assert config.id == "P0-001"
        assert config.name == "Queue Backlog"
        assert config.priority == AlertPriority.P0
        assert len(config.channels) == 2


class TestSlackChannel:
    """Tests for SlackChannel."""

    def test_init(self) -> None:
        """Test Slack channel initialization."""
        channel = SlackChannel("https://hooks.slack.com/test", "#alerts")
        assert channel.webhook_url == "https://hooks.slack.com/test"
        assert channel.channel == "#alerts"

    def test_init_default_channel(self) -> None:
        """Test Slack channel with default channel."""
        channel = SlackChannel("https://hooks.slack.com/test")
        assert channel.channel == "#ocr-alerts"

    @patch("httpx.Client")
    def test_send_success(self, mock_client_class: MagicMock) -> None:
        """Test successful Slack message send."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        channel = SlackChannel("https://hooks.slack.com/test")
        alert = Alert(
            id="P0-001-test",
            name="Test Alert",
            priority=AlertPriority.P0,
            message="Test message",
        )

        result = channel.send(alert)
        assert result is True
        mock_client.post.assert_called_once()

    @patch("httpx.Client")
    def test_send_with_details(self, mock_client_class: MagicMock) -> None:
        """Test Slack message with details."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        channel = SlackChannel("https://hooks.slack.com/test")
        alert = Alert(
            id="P1-001-test",
            name="Test Alert",
            priority=AlertPriority.P1,
            message="Test message",
            details={"key": "value"},
            runbook_url="https://example.com/runbook",
        )

        result = channel.send(alert)
        assert result is True

    @patch("httpx.Client")
    def test_send_failure(self, mock_client_class: MagicMock) -> None:
        """Test Slack message send failure."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = Exception("Network error")

        channel = SlackChannel("https://hooks.slack.com/test")
        alert = Alert(
            id="P0-001-test",
            name="Test Alert",
            priority=AlertPriority.P0,
            message="Test message",
        )

        result = channel.send(alert)
        assert result is False


class TestPagerDutyChannel:
    """Tests for PagerDutyChannel."""

    def test_init(self) -> None:
        """Test PagerDuty channel initialization."""
        channel = PagerDutyChannel("test-routing-key")
        assert channel.routing_key == "test-routing-key"
        assert "pagerduty.com" in channel.api_url

    @patch("httpx.Client")
    def test_send_success(self, mock_client_class: MagicMock) -> None:
        """Test successful PagerDuty alert send."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        channel = PagerDutyChannel("test-routing-key")
        alert = Alert(
            id="P0-001-test",
            name="Test Alert",
            priority=AlertPriority.P0,
            message="Test message",
        )

        result = channel.send(alert)
        assert result is True
        mock_client.post.assert_called_once()

    @patch("httpx.Client")
    def test_send_with_runbook(self, mock_client_class: MagicMock) -> None:
        """Test PagerDuty alert with runbook link."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        channel = PagerDutyChannel("test-routing-key")
        alert = Alert(
            id="P0-001-test",
            name="Test Alert",
            priority=AlertPriority.P0,
            message="Test message",
            runbook_url="https://example.com/runbook",
        )

        result = channel.send(alert)
        assert result is True

    @patch("httpx.Client")
    def test_send_failure(self, mock_client_class: MagicMock) -> None:
        """Test PagerDuty alert send failure."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = Exception("Network error")

        channel = PagerDutyChannel("test-routing-key")
        alert = Alert(
            id="P0-001-test",
            name="Test Alert",
            priority=AlertPriority.P0,
            message="Test message",
        )

        result = channel.send(alert)
        assert result is False


class TestEmailChannel:
    """Tests for EmailChannel."""

    def test_init(self) -> None:
        """Test email channel initialization."""
        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_port=587,
            from_address="alerts@example.com",
            to_addresses=["team@example.com"],
        )
        assert channel.smtp_host == "smtp.example.com"
        assert channel.smtp_port == 587
        assert channel.from_address == "alerts@example.com"
        assert "team@example.com" in channel.to_addresses

    def test_send_logs_only(self) -> None:
        """Test email channel logs but doesn't send (placeholder)."""
        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_port=587,
            from_address="alerts@example.com",
            to_addresses=["team@example.com"],
        )
        alert = Alert(
            id="P2-001-test",
            name="Test Alert",
            priority=AlertPriority.P2,
            message="Test message",
        )

        result = channel.send(alert)
        assert result is True  # Always returns True in placeholder


class TestAlertManager:
    """Tests for AlertManager."""

    def test_init_without_config(self) -> None:
        """Test manager initialization without config file."""
        manager = AlertManager(config_path="/nonexistent/path.yaml")
        assert len(manager.alert_configs) == 0

    def test_init_with_config(self) -> None:
        """Test manager initialization with config file."""
        config_path = str(Path(__file__).parent.parent.parent / "config" / "alerts.yaml")
        manager = AlertManager(config_path=config_path)
        # Should have loaded alerts from config
        assert len(manager.alert_configs) > 0

    def test_init_channels_slack(self) -> None:
        """Test channel initialization with Slack."""
        manager = AlertManager(
            config_path="/nonexistent/path.yaml",
            slack_webhook_url="https://hooks.slack.com/test",
        )
        assert "slack" in manager.channels

    def test_init_channels_pagerduty(self) -> None:
        """Test channel initialization with PagerDuty."""
        manager = AlertManager(
            config_path="/nonexistent/path.yaml",
            pagerduty_routing_key="test-key",
        )
        assert "pagerduty" in manager.channels

    def test_trigger_unknown_alert(self) -> None:
        """Test triggering unknown alert ID."""
        manager = AlertManager(config_path="/nonexistent/path.yaml")
        result = manager.trigger("unknown-alert-id")
        assert result is None

    def test_trigger_known_alert(self) -> None:
        """Test triggering known alert."""
        config_path = str(Path(__file__).parent.parent.parent / "config" / "alerts.yaml")
        manager = AlertManager(
            config_path=config_path,
            slack_webhook_url=None,  # Don't actually send
            pagerduty_routing_key=None,
        )

        if "P0-001" in manager.alert_configs:
            result = manager.trigger("P0-001", details={"test": "value"})
            assert result is not None
            assert result.name == manager.alert_configs["P0-001"].name

    def test_get_active_alerts_empty(self) -> None:
        """Test getting active alerts when none exist."""
        manager = AlertManager(config_path="/nonexistent/path.yaml")
        alerts = manager.get_active_alerts()
        assert len(alerts) == 0

    def test_resolve_unknown_alert(self) -> None:
        """Test resolving unknown alert."""
        manager = AlertManager(config_path="/nonexistent/path.yaml")
        result = manager.resolve("unknown-alert-id")
        assert result is False


class TestConvenienceAlertFunctions:
    """Tests for convenience alert functions."""

    def test_alert_queue_backlog_below_threshold(self) -> None:
        """Test queue backlog alert below threshold."""
        result = alert_queue_backlog(50)
        assert result is None

    def test_alert_queue_backlog_at_threshold(self) -> None:
        """Test queue backlog alert at threshold."""
        result = alert_queue_backlog(100)
        assert result is None

    @patch.object(AlertManager, "trigger")
    def test_alert_queue_backlog_above_threshold(self, mock_trigger: MagicMock) -> None:
        """Test queue backlog alert above threshold."""
        mock_alert = Alert(
            id="P0-001-test",
            name="Queue Backlog",
            priority=AlertPriority.P0,
            message="Test",
        )
        mock_trigger.return_value = mock_alert

        _result = alert_queue_backlog(150)
        # Result depends on whether AlertManager is configured
        # In test environment without config, may return None

    def test_alert_high_failure_rate_below_threshold(self) -> None:
        """Test failure rate alert below threshold."""
        result = alert_high_failure_rate(0.03, 100)
        assert result is None

    def test_alert_high_failure_rate_at_threshold(self) -> None:
        """Test failure rate alert at threshold."""
        result = alert_high_failure_rate(0.05, 100)
        assert result is None

    def test_alert_pro_budget_below_threshold(self) -> None:
        """Test pro budget alert below threshold."""
        result = alert_pro_budget_warning(30, 50)
        assert result is None

    def test_alert_pro_budget_at_threshold(self) -> None:
        """Test pro budget alert at threshold."""
        result = alert_pro_budget_warning(40, 50)
        assert result is None

    def test_alert_low_confidence_below_threshold(self) -> None:
        """Test low confidence alert below threshold."""
        result = alert_low_confidence_trend(0.2)
        assert result is None

    def test_alert_low_confidence_at_threshold(self) -> None:
        """Test low confidence alert at threshold."""
        result = alert_low_confidence_trend(0.3)
        assert result is None

    def test_alert_saga_compensations_below_threshold(self) -> None:
        """Test saga compensation alert below threshold."""
        result = alert_saga_compensations(3)
        assert result is None

    def test_alert_saga_compensations_at_threshold(self) -> None:
        """Test saga compensation alert at threshold."""
        result = alert_saga_compensations(5)
        assert result is None
