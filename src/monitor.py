import asyncio
import logging
import httpx
from .utils import get_iso_now
from .state import proxy_pool, alert_manager, global_config, global_metrics
from .webhooks import deliver_alert_webhooks

logger = logging.getLogger(__name__)

monitoring_active = False
monitoring_task = None
background_tasks = set()


async def probe_proxy(url: str, timeout_ms: int) -> str:
    """
    Probe a single proxy URL.

    Returns:
        "up"   — 2xx response received within timeout_ms
        "down" — timeout, connection error, connection refusal, OR any 5xx response
    """
    timeout_sec = timeout_ms / 1000.0

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            response = await client.get(url, follow_redirects=True)
            # FIX: 5xx responses must also be classified as "down" per spec
            if 200 <= response.status_code < 300:
                return "up"
            else:
                return "down"
    except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError):
        return "down"
    except Exception:
        return "down"


async def check_and_deliver_alerts():
    proxies = proxy_pool.list_proxies()
    if not proxies:
        return

    tasks = [probe_proxy(p["url"], global_config["request_timeout_ms"]) for p in proxies]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    now = get_iso_now()

    for proxy, result in zip(proxies, results):
        status = "down" if isinstance(result, Exception) else result
        proxy_pool.record_check(proxy["id"], status, now)
        global_metrics["total_checks"] += 1

    failure_rate = proxy_pool.get_failure_rate()
    down_proxies = sorted(proxy_pool.get_down_proxies())
    down_count = len(down_proxies)
    total_proxies = len(proxies)

    active_alert = alert_manager.get_active_alert()

    if failure_rate >= 0.20:
        if not active_alert:
            # Only fire a NEW alert if there is no active alert.
            # This prevents duplicate active alerts and duplicate fired webhooks
            # during a persistent breach (criterion 4.7).
            alert_id = alert_manager.fire_alert(
                failure_rate, total_proxies, down_count, down_proxies, get_iso_now()
            )
            alert_data = alert_manager.alerts[alert_id]
            task = asyncio.create_task(deliver_alert_webhooks("alert.fired", alert_data))
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)
    else:
        if active_alert:
            alert_id = alert_manager.resolve_alert(get_iso_now())
            if alert_id:
                alert_data = alert_manager.alerts[alert_id]
                task = asyncio.create_task(deliver_alert_webhooks("alert.resolved", alert_data))
                background_tasks.add(task)
                task.add_done_callback(background_tasks.discard)


async def background_monitoring_loop():
    global monitoring_active
    monitoring_active = True

    while monitoring_active:
        try:
            await check_and_deliver_alerts()
        except Exception as e:
            logger.error(f"Monitoring error: {e}")

        await asyncio.sleep(global_config["check_interval_seconds"])


def start_monitor():
    global monitoring_task
    monitoring_task = asyncio.create_task(background_monitoring_loop())


async def stop_monitor():
    global monitoring_active
    monitoring_active = False
    if monitoring_task:
        monitoring_task.cancel()
        try:
            await monitoring_task
        except asyncio.CancelledError:
            pass

    # Await all in-flight webhook deliveries before shutdown
    if background_tasks:
        await asyncio.gather(*background_tasks, return_exceptions=True)
