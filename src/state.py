from typing import Dict, List, Optional
from .utils import generate_alert_id, get_failure_rate, get_uptime_percentage

class ProxyPool:
    def __init__(self):
        self.proxies: Dict[str, Dict] = {}
    
    def add_proxy(self, proxy_id: str, url: str) -> None:
        self.proxies[proxy_id] = {
            "id": proxy_id,
            "url": url,
            "status": "pending",
            "last_checked_at": None,
            "consecutive_failures": 0,
            "total_checks": 0,
            "up_count": 0,
            "history": []
        }
    
    def record_check(self, proxy_id: str, status: str, checked_at: str) -> None:
        if proxy_id not in self.proxies:
            return
            
        proxy = self.proxies[proxy_id]
        proxy["status"] = status
        proxy["last_checked_at"] = checked_at
        proxy["total_checks"] += 1
        
        if status == "up":
            proxy["consecutive_failures"] = 0
            proxy["up_count"] += 1
        else:
            proxy["consecutive_failures"] += 1
            
        proxy["history"].append({
            "checked_at": checked_at,
            "status": status
        })
    
    def get_failure_rate(self) -> float:
        down_count = len(self.get_down_proxies())
        total_count = len(self.proxies)
        return get_failure_rate(down_count, total_count)
    
    def get_down_proxies(self) -> List[str]:
        return [pid for pid, p in self.proxies.items() if p["status"] == "down"]
    
    def get_proxy(self, proxy_id: str) -> Optional[Dict]:
        return self.proxies.get(proxy_id)
    
    def list_proxies(self) -> List[Dict]:
        return list(self.proxies.values())
    
    def clear(self) -> None:
        self.proxies.clear()
    
    def get_uptime_percentage(self, proxy_id: str) -> float:
        proxy = self.get_proxy(proxy_id)
        if not proxy:
            return 0.0
        return get_uptime_percentage(proxy["up_count"], proxy["total_checks"])


class AlertManager:
    def __init__(self):
        self.alerts: Dict[str, Dict] = {}
        self.active_alert_id: Optional[str] = None
    
    def fire_alert(self, failure_rate: float, total_proxies: int,
                   failed_proxies: int, failed_proxy_ids: List[str],
                   fired_at: str) -> str:
        if self.active_alert_id:
            return self.active_alert_id
            
        alert_id = generate_alert_id()
        self.alerts[alert_id] = {
            "alert_id": alert_id,
            "status": "active",
            "failure_rate": failure_rate,
            "total_proxies": total_proxies,
            "failed_proxies": failed_proxies,
            "failed_proxy_ids": failed_proxy_ids,
            "threshold": 0.2,
            "fired_at": fired_at,
            "resolved_at": None,
            "message": "Proxy pool failure rate exceeded threshold"
        }
        self.active_alert_id = alert_id
        return alert_id
    
    def resolve_alert(self, resolved_at: str) -> Optional[str]:
        if not self.active_alert_id:
            return None
            
        alert_id = self.active_alert_id
        self.alerts[alert_id]["status"] = "resolved"
        self.alerts[alert_id]["resolved_at"] = resolved_at
        self.active_alert_id = None
        return alert_id
    
    def get_active_alert(self) -> Optional[Dict]:
        if not self.active_alert_id:
            return None
        return self.alerts[self.active_alert_id]
    
    def list_alerts(self) -> List[Dict]:
        return list(self.alerts.values())


class WebhookManager:
    def __init__(self):
        self.webhooks: Dict[str, Dict] = {}
        self.integrations: Dict[str, Dict] = {}
        self.delivery_tracking: Dict[str, set] = {}
    
    def register_webhook(self, webhook_id: str, url: str) -> str:
        self.webhooks[webhook_id] = {
            "webhook_id": webhook_id,
            "url": url
        }
        return webhook_id
    
    def register_integration(self, integration_id: str, integration_type: str, 
                            webhook_url: str, username: str, events: List[str]) -> str:
        self.integrations[integration_id] = {
            "integration_id": integration_id,
            "type": integration_type,
            "webhook_url": webhook_url,
            "username": username,
            "events": events
        }
        return integration_id
    
    def has_been_delivered(self, alert_id: str, event_type: str, receiver_url: str) -> bool:
        key = f"{alert_id}_{event_type}_{receiver_url}"
        if alert_id not in self.delivery_tracking:
            self.delivery_tracking[alert_id] = set()
        return key in self.delivery_tracking[alert_id]
    
    def mark_delivered(self, alert_id: str, event_type: str, receiver_url: str) -> None:
        key = f"{alert_id}_{event_type}_{receiver_url}"
        if alert_id not in self.delivery_tracking:
            self.delivery_tracking[alert_id] = set()
        self.delivery_tracking[alert_id].add(key)


# Global instances
proxy_pool = ProxyPool()
alert_manager = AlertManager()
webhook_manager = WebhookManager()

global_config = {
    "check_interval_seconds": 15,
    "request_timeout_ms": 3000
}

global_metrics = {
    "total_checks": 0,
    "webhook_deliveries": 0
}
