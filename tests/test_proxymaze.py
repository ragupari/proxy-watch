import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.state import proxy_pool, alert_manager, webhook_manager

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_state():
    proxy_pool.clear()
    alert_manager.alerts.clear()
    alert_manager.active_alert_id = None
    webhook_manager.webhooks.clear()
    webhook_manager.integrations.clear()
    webhook_manager.delivery_tracking.clear()

def test_proxy_pool():
    proxy_pool.add_proxy("px-101", "https://example.com/proxy/px-101")
    assert proxy_pool.get_proxy("px-101")["status"] == "pending"
    
    proxy_pool.record_check("px-101", "up", "2026-04-24T10:15:30Z")
    assert proxy_pool.get_proxy("px-101")["status"] == "up"
    assert proxy_pool.get_proxy("px-101")["total_checks"] == 1

def test_alert_manager():
    alert_id = alert_manager.fire_alert(0.30, 10, 3, ["px-101", "px-102", "px-103"], "2026-04-24T10:20:00Z")
    assert alert_manager.get_active_alert()["alert_id"] == alert_id
    assert alert_manager.get_active_alert()["status"] == "active"
    
    # No second alert while first active
    alert_id2 = alert_manager.fire_alert(0.40, 10, 4, ["px-101", "px-102", "px-103", "px-104"], "2026-04-24T10:25:00Z")
    assert alert_id2 == alert_id  # Same ID
    
    # Resolve
    resolved_id = alert_manager.resolve_alert("2026-04-24T10:30:00Z")
    assert alert_manager.get_active_alert() is None
    assert alert_manager.alerts[resolved_id]["status"] == "resolved"

def test_webhook_manager():
    wh_id = webhook_manager.register_webhook("wh-test", "https://example.com/webhook")
    assert webhook_manager.webhooks[wh_id]["url"] == "https://example.com/webhook"
    
    # Track deliveries
    assert not webhook_manager.has_been_delivered("alert-1", "fired", "https://example.com")
    webhook_manager.mark_delivered("alert-1", "fired", "https://example.com")
    assert webhook_manager.has_been_delivered("alert-1", "fired", "https://example.com")

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_proxy_loading():
    response = client.post("/proxies", json={
        "proxies": ["https://example.com/px-101"],
        "replace": True
    })
    assert response.status_code == 201
    assert response.json()["accepted"] == 1

def test_alert_lifecycle():
    client.post("/proxies", json={
        "proxies": ["https://example.com/px-1", "https://example.com/px-2"],
        "replace": True
    })
    
    # Get status
    response = client.get("/proxies")
    assert response.status_code == 200
    
    # Check alerts (should be empty initially)
    response = client.get("/alerts")
    assert response.json() == []
