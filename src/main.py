from fastapi import FastAPI, HTTPException, status, Request
from typing import List, Dict, Any
import uuid

from .models import ConfigRequest, ProxiesRequest, WebhookRequest, IntegrationRequest
from .state import proxy_pool, alert_manager, webhook_manager, global_config, global_metrics
from .monitor import start_monitor, stop_monitor
from .utils import extract_proxy_id

app = FastAPI(title="ProxyMaze", version="1.0.0")

# Request logging storage
request_logs = []

@app.middleware("http")
async def log_requests(request: Request, call_next):
    from datetime import datetime, timezone
    ip = request.client.host
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    
    # Store log entry
    request_logs.append({
        "timestamp": timestamp,
        "method": request.method,
        "path": request.url.path,
        "ip": ip
    })
    
    # Keep only last 100 logs
    if len(request_logs) > 100:
        request_logs.pop(0)
        
    response = await call_next(request)
    return response

@app.on_event("startup")
async def startup_event():
    start_monitor()

@app.on_event("shutdown")
async def shutdown_event():
    await stop_monitor()

@app.get("/requests")
async def get_requests():
    return request_logs

@app.get("/")
async def root():
    return {"message": "Welcome to ProxyMaze4.0"}
    

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/config")
async def set_config(config: ConfigRequest):
    # Stop and start for updated timeout or check interval for immediate update
    if (
        global_config["check_interval_seconds"] != config.check_interval_seconds
        or global_config["request_timeout_ms"] != config.request_timeout_ms
    ):
        global_config["check_interval_seconds"] = config.check_interval_seconds
        global_config["request_timeout_ms"] = config.request_timeout_ms
        await stop_monitor()
        start_monitor()
    return global_config

@app.get("/config")
async def get_config():
    return global_config

@app.post("/proxies", status_code=status.HTTP_201_CREATED)
async def load_proxies(req: ProxiesRequest):
    if req.replace:
        proxy_pool.clear()
        
    added = []
    for url in req.proxies:
        pid = extract_proxy_id(url)
        proxy_pool.add_proxy(pid, url)
        added.append(proxy_pool.get_proxy(pid))
        
    return {
        "accepted": len(added),
        "proxies": [{"id": p["id"], "url": p["url"], "status": p["status"]} for p in added]
    }

@app.get("/proxies")
async def get_proxies():
    proxies = proxy_pool.list_proxies()
    total = len(proxies)
    down = len(proxy_pool.get_down_proxies())
    up = total - down
    
    # We round to 2 decimals exactly as in utils.py
    failure_rate = proxy_pool.get_failure_rate()
    
    return {
        "total": total,
        "up": up,
        "down": down,
        "failure_rate": failure_rate,
        "proxies": [
            {
                "id": p["id"],
                "url": p["url"],
                "status": p["status"],
                "last_checked_at": p["last_checked_at"],
                "consecutive_failures": p["consecutive_failures"]
            }
            for p in proxies
        ]
    }

@app.get("/proxies/{proxy_id}")
async def get_proxy(proxy_id: str):
    p = proxy_pool.get_proxy(proxy_id)
    if not p:
        raise HTTPException(status_code=404, detail="Proxy not found")
        
    return {
        "id": p["id"],
        "url": p["url"],
        "status": p["status"],
        "last_checked_at": p["last_checked_at"],
        "consecutive_failures": p["consecutive_failures"],
        "total_checks": p["total_checks"],
        "uptime_percentage": proxy_pool.get_uptime_percentage(proxy_id),
        "history": p["history"]
    }

@app.get("/proxies/{proxy_id}/history")
async def get_proxy_history(proxy_id: str):
    p = proxy_pool.get_proxy(proxy_id)
    if not p:
        raise HTTPException(status_code=404, detail="Proxy not found")
    return p["history"]

@app.delete("/proxies", status_code=status.HTTP_204_NO_CONTENT)
async def clear_proxies():
    proxy_pool.clear()

@app.get("/alerts")
async def get_alerts():
    return alert_manager.list_alerts()

@app.post("/webhooks", status_code=status.HTTP_201_CREATED)
async def register_webhook(req: WebhookRequest):
    wh_id = f"wh-{uuid.uuid4().hex[:6]}"
    webhook_manager.register_webhook(wh_id, req.url)
    return {
        "webhook_id": wh_id,
        "url": req.url
    }

@app.post("/integrations", status_code=status.HTTP_201_CREATED)
async def register_integration(req: IntegrationRequest):
    int_id = f"int-{uuid.uuid4().hex[:6]}"
    webhook_manager.register_integration(
        int_id, req.type, req.webhook_url, req.username, req.events
    )
    return {
        "integration_id": int_id,
        "type": req.type,
        "webhook_url": req.webhook_url
    }

@app.get("/metrics")
async def get_metrics():
    return {
        "total_checks": global_metrics["total_checks"],
        "current_pool_size": len(proxy_pool.proxies),
        "active_alerts": 1 if alert_manager.active_alert_id else 0,
        "total_alerts": len(alert_manager.alerts),
        "webhook_deliveries": global_metrics["webhook_deliveries"]
    }
