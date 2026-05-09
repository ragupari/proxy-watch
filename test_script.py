import asyncio
import httpx
from fastapi import FastAPI, Request
import uvicorn
import threading
import time

app = FastAPI()

received_payloads = []

@app.post("/webhook")
async def receive_webhook(request: Request):
    payload = await request.json()
    received_payloads.append(payload)
    print("RECEIVED WEBHOOK:", payload)
    return {"status": "ok"}

@app.get("/proxy/{id}")
async def proxy_endpoint(id: str):
    if id == "px-fail":
        return httpx.Response(500)
    return {"status": "ok"}

def run_server():
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="error")

def main():
    threading.Thread(target=run_server, daemon=True).start()
    time.sleep(2)
    
    with httpx.Client() as client:
        # Register webhook
        res = client.post("http://localhost:8000/webhooks", json={"url": "http://localhost:8080/webhook"})
        print("Register webhook:", res.json())
        
        # Add proxies
        res = client.post("http://localhost:8000/proxies", json={
            "proxies": [
                "http://localhost:8080/proxy/px-fail",
                "http://localhost:8080/proxy/px-fail2"
            ],
            "replace": True
        })
        print("Add proxies:", res.json())
        
        time.sleep(20)
        print("Received payloads:", received_payloads)

if __name__ == "__main__":
    main()
