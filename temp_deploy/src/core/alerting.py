"""Alerting system for AI-OCR Smart Pipeline.

This module provides alerting functionality for monitoring the pipeline
and notifying operators of issues.

See docs/specs/12_alerting.md for alerting requirements.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import httpx
import yaml

from src.core.logging import EventType, get_logger, log_error

logger = get_logger("alerting")


class AlertPriority(str, Enum):
    """Alert priority levels."""

    P0 = "P0"  # Critical - Immediate response required
    P1 = "P1"  # High - Respond within 1 hour
    P2 = "P2"  # Medium - Respond within 4 hours
    P3 = "P3"  # Low - Daily summary


class AlertStatus(str, Enum):
    """Alert status."""

    FIRING = "firing"
    RESOLVED = "resolved"
    SILENCED = "silenced"


@dataclass
class Alert:
    """Alert data structure."""

    id: str
    name: str
    priority: AlertPriority
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    status: AlertStatus = AlertStatus.FIRING
    triggered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved_at: datetime | None = None
    runbook_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "priority": self.priority.value,
            "message": self.message,
            "details": self.details,
            "status": self.status.value,
            "triggered_at": self.triggered_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "runbook_url": self.runbook_url,
        }


@dataclass
class AlertConfig:
    """Configuration for an alert definition."""

    id: str
    name: str
    description: str
    priority: AlertPriority
    condition: dict[str, Any]
    window: str
    channels: list[str]
    message: str
    runbook_url: str | None = None


class AlertChannel:
    """Base class for alert notification channels."""

    def send(self, alert: Alert) -> bool:
        """Send alert notification.

        Args:
            alert: Alert to send.

        Returns:
            True if sent successfully.
        """
        raise NotImplementedError


class SlackChannel(AlertChannel):
    """Slack notification channel."""

    def __init__(self, webhook_url: str, channel: str = "#ocr-alerts") -> None:
        """Initialize Slack channel.

        Args:
            webhook_url: Slack webhook URL.
            channel: Slack channel name.
        """
        self.webhook_url = webhook_url
        self.channel = channel

    def send(self, alert: Alert) -> bool:
        """Send alert to Slack.

        Args:
            alert: Alert to send.

        Returns:
            True if sent successfully.
        """
        try:
            # Build message based on priority
            priority_emoji = {
                AlertPriority.P0: ":rotating_light:",
                AlertPriority.P1: ":warning:",
                AlertPriority.P2: ":large_blue_circle:",
                AlertPriority.P3: ":information_source:",
            }

            priority_color = {
                AlertPriority.P0: "danger",
                AlertPriority.P1: "warning",
                AlertPriority.P2: "#439FE0",
                AlertPriority.P3: "good",
            }

            emoji = priority_emoji.get(alert.priority, ":bell:")
            color = priority_color.get(alert.priority, "warning")

            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} {alert.priority.value}: {alert.name}",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": alert.message,
                    },
                },
            ]

            # Add details if present
            if alert.details:
                detail_text = "\n".join(f"• *{k}*: {v}" for k, v in alert.details.items())
                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Details:*\n{detail_text}",
                        },
                    }
                )

            # Add runbook link if present
            if alert.runbook_url:
                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f":book: <{alert.runbook_url}|View Runbook>",
                        },
                    }
                )

            payload = {
                "channel": self.channel,
                "username": "OCR Pipeline Alerts",
                "icon_emoji": ":robot_face:",
                "attachments": [
                    {
                        "color": color,
                        "blocks": blocks,
                    }
                ],
            }

            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    self.webhook_url,
                    json=payload,
                )
                response.raise_for_status()

            logger.info(
                "slack_alert_sent",
                alert_id=alert.id,
                channel=self.channel,
            )
            return True

        except Exception as e:
            log_error(
                EventType.ALERT_TRIGGERED,
                error=e,
                alert_id=alert.id,
                channel="slack",
            )
            return False


class PagerDutyChannel(AlertChannel):
    """PagerDuty notification channel."""

    def __init__(self, routing_key: str) -> None:
        """Initialize PagerDuty channel.

        Args:
            routing_key: PagerDuty routing key.
        """
        self.routing_key = routing_key
        self.api_url = "https://events.pagerduty.com/v2/enqueue"

    def send(self, alert: Alert) -> bool:
        """Send alert to PagerDuty.

        Args:
            alert: Alert to send.

        Returns:
            True if sent successfully.
        """
        try:
            severity_map = {
                AlertPriority.P0: "critical",
                AlertPriority.P1: "error",
                AlertPriority.P2: "warning",
                AlertPriority.P3: "info",
            }

            payload = {
                "routing_key": self.routing_key,
                "event_action": "trigger",
                "dedup_key": alert.id,
                "payload": {
                    "summary": f"{alert.priority.value}: {alert.name}",
                    "severity": severity_map.get(alert.priority, "warning"),
                    "source": "ocr-pipeline",
                    "timestamp": alert.triggered_at.isoformat(),
                    "custom_details": {
                        "message": alert.message,
                        **alert.details,
                    },
                },
                "links": [],
            }

            if alert.runbook_url:
                payload["links"].append(
                    {
                        "href": alert.runbook_url,
                        "text": "Runbook",
                    }
                )

            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    self.api_url,
                    json=payload,
                )
                response.raise_for_status()

            logger.info(
                "pagerduty_alert_sent",
                alert_id=alert.id,
            )
            return True

        except Exception as e:
            log_error(
                EventType.ALERT_TRIGGERED,
                error=e,
                alert_id=alert.id,
                channel="pagerduty",
            )
            return False


class EmailChannel(AlertChannel):
    """Email notification channel (placeholder for SMTP implementation)."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        from_address: str,
        to_addresses: list[str],
    ) -> None:
        """Initialize email channel.

        Args:
            smtp_host: SMTP server host.
            smtp_port: SMTP server port.
            from_address: Sender email address.
            to_addresses: Recipient email addresses.
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.from_address = from_address
        self.to_addresses = to_addresses

    def send(self, alert: Alert) -> bool:
        """Send alert via email.

        Args:
            alert: Alert to send.

        Returns:
            True if sent successfully.
        """
        # Placeholder - would implement SMTP sending
        logger.info(
            "email_alert_logged",
            alert_id=alert.id,
            to=self.to_addresses,
            message="Email sending not implemented in development",
        )
        return True


class AlertManager:
    """Manager for alert configuration and sending."""

    def __init__(
        self,
        config_path: str | None = None,
        slack_webhook_url: str | None = None,
        pagerduty_routing_key: str | None = None,
    ) -> None:
        """Initialize alert manager.

        Args:
            config_path: Path to alerts.yaml configuration file.
            slack_webhook_url: Slack webhook URL override.
            pagerduty_routing_key: PagerDuty routing key override.
        """
        self.config_path = config_path or str(
            Path(__file__).parent.parent.parent / "config" / "alerts.yaml"
        )
        self.slack_webhook_url = slack_webhook_url or os.environ.get("SLACK_WEBHOOK_URL")
        self.pagerduty_routing_key = pagerduty_routing_key or os.environ.get(
            "PAGERDUTY_ROUTING_KEY"
        )

        self.alert_configs: dict[str, AlertConfig] = {}
        self.channels: dict[str, AlertChannel] = {}
        self._active_alerts: dict[str, Alert] = {}

        self._load_config()
        self._init_channels()

    def _load_config(self) -> None:
        """Load alert configuration from YAML file."""
        try:
            with Path(self.config_path).open(encoding="utf-8") as f:
                config = yaml.safe_load(f)

            for alert_def in config.get("alerts", []):
                alert_config = AlertConfig(
                    id=alert_def["id"],
                    name=alert_def["name"],
                    description=alert_def.get("description", ""),
                    priority=AlertPriority(alert_def["severity"]),
                    condition=alert_def.get("condition", {}),
                    window=alert_def.get("window", "5m"),
                    channels=[c.get("type", "slack") for c in alert_def.get("channels", [])],
                    message=alert_def.get("message", ""),
                    runbook_url=alert_def.get("runbook"),
                )
                self.alert_configs[alert_config.id] = alert_config

            logger.info(
                "alert_config_loaded",
                alert_count=len(self.alert_configs),
            )

        except FileNotFoundError:
            logger.warning(
                "alert_config_not_found",
                path=self.config_path,
            )
        except Exception as e:
            log_error(
                EventType.ALERT_TRIGGERED,
                error=e,
                message="Failed to load alert configuration",
            )

    def _init_channels(self) -> None:
        """Initialize notification channels."""
        if self.slack_webhook_url:
            self.channels["slack"] = SlackChannel(self.slack_webhook_url)

        if self.pagerduty_routing_key:
            self.channels["pagerduty"] = PagerDutyChannel(self.pagerduty_routing_key)

    def trigger(
        self,
        alert_id: str,
        details: dict[str, Any] | None = None,
        message_override: str | None = None,
    ) -> Alert | None:
        """Trigger an alert.

        Args:
            alert_id: ID of the alert definition to trigger.
            details: Additional details to include.
            message_override: Override the default message.

        Returns:
            The triggered Alert, or None if failed.
        """
        config = self.alert_configs.get(alert_id)
        if not config:
            logger.warning(
                "alert_config_not_found",
                alert_id=alert_id,
            )
            return None

        # Create alert instance
        alert = Alert(
            id=f"{alert_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            name=config.name,
            priority=config.priority,
            message=message_override or config.message,
            details=details or {},
            runbook_url=config.runbook_url,
        )

        # Track active alert
        self._active_alerts[alert.id] = alert

        # Send to configured channels
        for channel_name in config.channels:
            channel = self.channels.get(channel_name)
            if channel:
                channel.send(alert)
            else:
                logger.warning(
                    "alert_channel_not_configured",
                    channel=channel_name,
                    alert_id=alert.id,
                )

        logger.info(
            "alert_triggered",
            alert_id=alert.id,
            priority=alert.priority.value,
            name=alert.name,
        )

        return alert

    def resolve(self, alert_id: str) -> bool:
        """Resolve an active alert.

        Args:
            alert_id: ID of the alert to resolve.

        Returns:
            True if resolved successfully.
        """
        alert = self._active_alerts.get(alert_id)
        if not alert:
            return False

        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now(UTC)

        # For PagerDuty, send resolve event
        if "pagerduty" in self.channels:
            try:
                channel = self.channels["pagerduty"]
                if isinstance(channel, PagerDutyChannel):
                    with httpx.Client(timeout=10.0) as client:
                        response = client.post(
                            channel.api_url,
                            json={
                                "routing_key": channel.routing_key,
                                "event_action": "resolve",
                                "dedup_key": alert_id,
                            },
                        )
                        response.raise_for_status()
            except Exception as e:
                log_error(
                    EventType.ALERT_TRIGGERED,
                    error=e,
                    alert_id=alert_id,
                    message="Failed to resolve PagerDuty alert",
                )

        del self._active_alerts[alert_id]

        logger.info(
            "alert_resolved",
            alert_id=alert_id,
        )

        return True

    def get_active_alerts(self) -> list[Alert]:
        """Get all active alerts.

        Returns:
            List of active alerts.
        """
        return list(self._active_alerts.values())


# Convenience functions for common alerts


def alert_queue_backlog(pending_count: int) -> Alert | None:
    """Alert for queue backlog exceeding threshold.

    Args:
        pending_count: Number of pending documents.

    Returns:
        Triggered alert or None.
    """
    if pending_count <= 100:
        return None

    manager = AlertManager()
    return manager.trigger(
        "P0-001",
        details={
            "pending_count": pending_count,
            "threshold": 100,
        },
        message_override=(
            f"Document processing queue has {pending_count} pending items (threshold: 100)."
        ),
    )


def alert_high_failure_rate(failure_rate: float, total_processed: int) -> Alert | None:
    """Alert for high failure rate.

    Args:
        failure_rate: Failure rate as decimal (0.0 - 1.0).
        total_processed: Total documents processed.

    Returns:
        Triggered alert or None.
    """
    if failure_rate <= 0.05:
        return None

    manager = AlertManager()
    return manager.trigger(
        "P1-001",
        details={
            "failure_rate": f"{failure_rate:.1%}",
            "total_processed": total_processed,
            "failed_count": int(total_processed * failure_rate),
        },
        message_override=f"Document failure rate is {failure_rate:.1%} (threshold: 5%).",
    )


def alert_pro_budget_warning(daily_used: int, daily_limit: int) -> Alert | None:
    """Alert for Pro API budget usage.

    Args:
        daily_used: Number of Pro calls used today.
        daily_limit: Daily Pro call limit.

    Returns:
        Triggered alert or None.
    """
    usage_ratio = daily_used / daily_limit if daily_limit > 0 else 0
    if usage_ratio <= 0.8:
        return None

    manager = AlertManager()
    return manager.trigger(
        "P2-001",
        details={
            "daily_used": daily_used,
            "daily_limit": daily_limit,
            "usage_percentage": f"{usage_ratio:.0%}",
        },
        message_override=(
            f"Pro API usage at {usage_ratio:.0%} of daily budget ({daily_used}/{daily_limit})."
        ),
    )


def alert_low_confidence_trend(low_confidence_rate: float) -> Alert | None:
    """Alert for trend of low confidence OCR results.

    Args:
        low_confidence_rate: Rate of documents with low confidence.

    Returns:
        Triggered alert or None.
    """
    if low_confidence_rate <= 0.3:
        return None

    manager = AlertManager()
    return manager.trigger(
        "P2-003",
        details={
            "low_confidence_rate": f"{low_confidence_rate:.1%}",
            "threshold": "30%",
        },
        message_override=(
            f"{low_confidence_rate:.0%} of documents have low OCR confidence. Check scan quality."
        ),
    )


def alert_saga_compensations(compensation_count: int, time_window: str = "1h") -> Alert | None:
    """Alert for saga compensation spike.

    Args:
        compensation_count: Number of saga compensations.
        time_window: Time window for the count.

    Returns:
        Triggered alert or None.
    """
    if compensation_count <= 5:
        return None

    manager = AlertManager()
    return manager.trigger(
        "P1-002",
        details={
            "compensation_count": compensation_count,
            "time_window": time_window,
        },
        message_override=(
            f"Multiple saga rollbacks detected ({compensation_count} in {time_window}). "
            "Potential data integrity issue."
        ),
    )
