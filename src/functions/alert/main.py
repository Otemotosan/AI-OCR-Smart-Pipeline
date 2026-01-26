
import base64
import json
import os
import functions_framework
import requests
import structlog
from cloudevents.http import CloudEvent

logger = structlog.get_logger(__name__)

@functions_framework.cloud_event
def handle_dead_letter(event: CloudEvent) -> str:
    """
    Handle messages from dead letter queue.

    Sends Slack notification for failed documents that
    require human attention.

    Args:
        event: CloudEvent from Pub/Sub dead letter topic

    Returns:
        Status message string
    """
    logger.info("dead_letter_received", event_type=event["type"])

    # Decode Pub/Sub message
    try:
        message_data = event.data.get("message", {}).get("data", "")
        decoded = base64.b64decode(message_data).decode("utf-8")
        payload = json.loads(decoded)
    except Exception as e:
        logger.error("dead_letter_decode_failed", error=str(e))
        payload = {"raw_event": str(event.data)}

    # Prepare Slack notification
    slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "")

    if not slack_webhook_url:
        logger.warning("slack_webhook_not_configured")
        return "SKIPPED: Slack webhook not configured"

    environment = os.environ.get("ENVIRONMENT", "unknown")
    doc_hash = payload.get("doc_hash", "unknown")
    error_message = payload.get("error", "Unknown error")

    slack_message = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 OCR処理失敗 ({environment})",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Document ID:*\n`{doc_hash}`"},
                    {"type": "mrkdwn", "text": f"*Environment:*\n{environment}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error:*\n```{error_message[:500]}```",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "📋 Review UI で確認してください",
                    },
                ],
            },
        ],
    }

    try:
        response = requests.post(
            slack_webhook_url,
            json=slack_message,
            timeout=10,
        )
        response.raise_for_status()
        logger.info("slack_notification_sent", doc_hash=doc_hash)
        return "NOTIFIED: Slack message sent"
    except Exception as e:
        logger.error("slack_notification_failed", error=str(e))
        return f"FAILED: Slack notification error: {e}"
