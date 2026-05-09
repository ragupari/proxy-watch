from pydantic import BaseModel, ConfigDict
from typing import List, Optional

class ConfigRequest(BaseModel):
    check_interval_seconds: int
    request_timeout_ms: int
    
    model_config = ConfigDict(extra='ignore')

class ProxiesRequest(BaseModel):
    proxies: List[str]
    replace: Optional[bool] = False
    
    model_config = ConfigDict(extra='ignore')

class WebhookRequest(BaseModel):
    url: str
    
    model_config = ConfigDict(extra='ignore')

class IntegrationRequest(BaseModel):
    type: str
    webhook_url: str
    username: Optional[str] = "ProxyWatch"
    events: Optional[List[str]] = ["alert.fired", "alert.resolved"]
    
    model_config = ConfigDict(extra='ignore')
