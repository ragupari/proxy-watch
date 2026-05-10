import asyncio
import logging
import httpx
from datetime import datetime
from .state import webhook_manager, global_metrics

logger = logging.getLogger(__name__)


def format_integration_payload(integration_type: str, event_type: str, alert_data: dict, username: str) -> dict:
    if integration_type == "slack":
        color = "#ff0000" if event_type == "alert.fired" else "#00ff00"
        text = (
            f"⚠️  ALERT: Proxy pool failure rate at {int(alert_data.get('failure_rate', 0) * 100)}%"
            if event_type == "alert.fired"
            else "✅ RESOLVED: Proxy pool recovered"
        )

        fields = [{"title": "Alert ID", "value": alert_data["alert_id"]}]

        if event_type == "alert.fired":
            fields.extend([
                {"title": "Failure Rate", "value": f"{int(alert_data['failure_rate'] * 100)}%"},
                {"title": "Failed Proxies", "value": str(alert_data["failed_proxies"])},
                {"title": "Threshold", "value": f"{int(alert_data['threshold'] * 100)}%"},
                {"title": "Failed IDs", "value": ", ".join(alert_data["failed_proxy_ids"])},
                {"title": "Fired At", "value": alert_data["fired_at"]},
            ])
        else:
            fields.append({"title": "Resolved At", "value": alert_data["resolved_at"]})

        # FIX: ts must be an integer (not float) per spec
        ts = int(datetime.now().timestamp())

        return {
            "username": username,
            "text": text,
            "attachments": [{
                "color": color,
                "fields": fields,
                "footer": "ProxyMaze Alert",
                "ts": ts,
            }],
        }

    elif integration_type == "discord":
        color = 16711680 if event_type == "alert.fired" else 65280
        title = "🚨 Proxy Pool Alert Fired" if event_type == "alert.fired" else "✅ Proxy Pool Alert Resolved"
        desc = (
            f"The proxy pool has exceeded the {int(alert_data.get('threshold', 0.2) * 100)}% failure threshold"
            if event_type == "alert.fired"
            else "The proxy pool has recovered."
        )

        fields = [{"name": "Alert ID", "value": alert_data["alert_id"]}]

        if event_type == "alert.fired":
            fields.extend([
                {"name": "Failure Rate", "value": f"{int(alert_data['failure_rate'] * 100)}%"},
                {"name": "Failed Proxies", "value": str(alert_data["failed_proxies"])},
                {"name": "Threshold", "value": f"{int(alert_data['threshold'] * 100)}%"},
                {"name": "Failed IDs", "value": ", ".join(alert_data["failed_proxy_ids"])},
            ])
        else:
            fields.append({"name": "Resolved At", "value": alert_data["resolved_at"]})

        return {
            "username": username,
            "embeds": [{
                "title": title,
                "description": desc,
                "color": color,
                "fields": fields,
                "footer": {"text": "ProxyMaze Monitoring"},
            }],
        }

    return {}


async def send_webhook_delivery(url: str, payload: dict, retries: int = 10) -> bool:
    """
    Send webhook with exponential backoff retry.

    FIX: Retries indefinitely on transient 5xx failures until success,
    per spec: "retry until the delivery succeeds".
    Non-transient failures (4xx etc.) stop immediately.
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
                if response.status_code in [500, 502, 503, 504]:
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
    """
    FIX: Only mark as delivered AFTER a successful delivery.
    Previously mark_delivered was called before sending, so failed
    deliveries were silently skipped forever.
    """
    success = await send_webhook_delivery(url, payload)
    if success:
        webhook_manager.mark_delivered(alert_id, event_type, url)


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
        if not webhook_manager.has_been_delivered(alert_id, event_type, webhook["url"]):
            tasks.append(_deliver_and_mark(webhook["url"], payload, alert_id, event_type))

    # Slack / Discord integrations
    for int_id, integration in webhook_manager.integrations.items():
        if event_type in integration["events"]:
            if not webhook_manager.has_been_delivered(alert_id, event_type, integration["webhook_url"]):
                formatted_payload = format_integration_payload(
                    integration["type"], event_type, alert_data, integration["username"]
                )
                tasks.append(
                    _deliver_and_mark(integration["webhook_url"], formatted_payload, alert_id, event_type)
                )

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
