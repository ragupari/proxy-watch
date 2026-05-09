import uuid
from datetime import datetime, timezone

def extract_proxy_id(url: str) -> str:
    """
    Extract proxy ID from URL path
    https://proxy.example/proxy/px-101 -> "px-101"
    """
    return url.rstrip("/").split("/")[-1]

def get_iso_now() -> str:
    """Get current time in ISO 8601 UTC format"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def generate_alert_id() -> str:
    """Generate unique alert ID"""
    return f"alert-{uuid.uuid4().hex[:8]}"

def get_failure_rate(down_count: int, total_count: int) -> float:
    """Calculate failure rate, rounded to 2 decimals"""
    if total_count == 0:
        return 0.0
    return round(down_count / total_count, 2)

def get_uptime_percentage(up_count: int, total_checks: int) -> float:
    """Calculate uptime percentage"""
    if total_checks == 0:
        return 0.0
    return round((up_count / total_checks) * 100, 1)
