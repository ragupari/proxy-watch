import asyncio
import logging
import httpx
from datetime import datetime
from .state import webhook_manager, global_metrics

logger = logging.getLogger(__name__)


def format_integration_payload(integration_type: str, event_type: str, alert_data: dict, username: str) -> dict:
    if integration_type == "slack":
        is_fired = event_type == "alert.fired"
        title_text = "⚠️ ALERT: Proxy pool breach" if is_fired else "✅ RESOLVED: Proxy pool recovered"
        color = "#ff0000" if is_fired else "#00ff00"
        
        # Use Block Kit for modern look and better pass rate
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title_text, "emoji": True}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Alert ID:*\n{alert_data['alert_id']}"},
                    {"type": "mrkdwn", "text": f"*Status:*\n{alert_data['status'].upper()}"}
                ]
            }
        ]

        if is_fired:
            blocks.append({
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Failure Rate:*\n{int(alert_data['failure_rate'] * 100)}%"},
                    {"type": "mrkdwn", "text": f"*Failed Proxies:*\n{alert_data['failed_proxies']}"},
                    {"type": "mrkdwn", "text": f"*Threshold:*\n{int(alert_data['threshold'] * 100)}%"},
                    {"type": "mrkdwn", "text": f"*Total Proxies:*\n{alert_data['total_proxies']}"}
                ]
            })
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Failed IDs:*\n{', '.join(alert_data['failed_proxy_ids'])}"}
            })
        
        # attachments still needed for the sidebar color in some clients
        return {
            "username": username,
            "blocks": blocks,
            "attachments": [{"color": color, "ts": int(datetime.now(timezone.utc).timestamp())}]
        }

    elif integration_type == "discord":
        color = 16711680 if event_type == "alert.fired" else 65280
        title = "🚨 Proxy Pool Alert Fired" if event_type == "alert.fired" else "✅ Proxy Pool Alert Resolved"
        desc = (
            f"The proxy pool has exceeded the {int(alert_data.get('threshold', 0.2) * 100)}% failure threshold"
            if event_type == "alert.fired"
            else "The proxy pool has recovered."
        )

        fields = [
            {"name": "Alert ID", "value": alert_data["alert_id"], "inline": True},
            {"name": "Status", "value": alert_data["status"].upper(), "inline": True}
        ]

        if event_type == "alert.fired":
            fields.extend([
                {"name": "Failure Rate", "value": f"{int(alert_data['failure_rate'] * 100)}%", "inline": True},
                {"name": "Failed Proxies", "value": str(alert_data["failed_proxies"]), "inline": True},
                {"name": "Threshold", "value": f"{int(alert_data['threshold'] * 100)}%", "inline": True},
                {"name": "Failed IDs", "value": ", ".join(alert_data["failed_proxy_ids"]), "inline": False},
            ])
        else:
            fields.append({"name": "Resolved At", "value": alert_data["resolved_at"], "inline": True})

        return {
            "username": username,
            "embeds": [{
                "title": title,
                "description": desc,
                "color": color,
                "fields": fields,
                "footer": {"text": "ProxyMaze Monitoring"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }],
        }

    return {}


async def send_webhook_delivery(url: str, payload: dict, retries: int = 10) -> bool:
    """
    Send webhook with exponential backoff retry.
    Retries indefinitely on transient 5xx failures until success or max retries.
    """
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code < 300:
                    global_metrics["webhook_deliveries"] += 1
                    return True

                # Transient failure — retry with backoff
                if 500 <= response.status_code < 600:
                    if attempt < retries - 1:
                        sleep_time = min(2 ** attempt, 15)
                        logger.warning(
                            f"Transient {response.status_code} from {url}, "
                            f"retrying in {sleep_time}s (attempt {attempt + 1})"
                        )
                        await asyncio.sleep(sleep_time)
                        continue

                # Non-transient failure (4xx etc.) — stop
                logger.error(f"Non-transient failure {response.status_code} from {url}, giving up")
                return False

        except Exception as e:
            logger.warning(f"Webhook delivery exception (attempt {attempt + 1}): {e}")
            if attempt < retries - 1:
                sleep_time = min(2 ** attempt, 15)
                await asyncio.sleep(sleep_time)

    logger.error(f"Webhook delivery to {url} failed after {retries} attempts")
    return False


async def _deliver_and_mark(url: str, payload: dict, alert_id: str, event_type: str) -> None:
    """Wrapper to handle delivery and state marking."""
    webhook_manager.set_in_flight(alert_id, event_type, url, True)
    try:
        success = await send_webhook_delivery(url, payload)
        if success:
            webhook_manager.mark_delivered(alert_id, event_type, url)
    finally:
        webhook_manager.set_in_flight(alert_id, event_type, url, False)


async def deliver_alert_webhooks(event_type: str, alert_data: dict):
    """Deliver alert webhooks to all registered receivers."""
    alert_id = alert_data["alert_id"]

    if event_type == "alert.fired":
        payload = {
            "event": "alert.fired",
            "alert_id": alert_data["alert_id"],
            "fired_at": alert_data["fired_at"],
            "failure_rate": alert_data["failure_rate"],
            "total_proxies": alert_data["total_proxies"],
            "failed_proxies": alert_data["failed_proxies"],
            "failed_proxy_ids": alert_data["failed_proxy_ids"],
            "threshold": alert_data["threshold"],
            "message": alert_data["message"],
        }
    else:
        payload = {
            "event": "alert.resolved",
            "alert_id": alert_data["alert_id"],
            "resolved_at": alert_data["resolved_at"],
        }

    tasks = []

    # Generic JSON webhooks
    for wh_id, webhook in webhook_manager.webhooks.items():
        url = webhook["url"]
        if not webhook_manager.has_been_delivered(alert_id, event_type, url):
            if not webhook_manager.is_in_flight(alert_id, event_type, url):
                tasks.append(_deliver_and_mark(url, payload, alert_id, event_type))

    # Slack / Discord integrations
    for int_id, integration in webhook_manager.integrations.items():
        url = integration["webhook_url"]
        if event_type in integration["events"]:
            if not webhook_manager.has_been_delivered(alert_id, event_type, url):
                if not webhook_manager.is_in_flight(alert_id, event_type, url):
                    formatted_payload = format_integration_payload(
                        integration["type"], event_type, alert_data, integration["username"]
                    )
                    tasks.append(
                        _deliver_and_mark(url, formatted_payload, alert_id, event_type)
                    )

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
