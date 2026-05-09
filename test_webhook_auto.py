import asyncio
import httpx
from fastapi import FastAPI, Request
import uvicorn
import threading
import time
import subprocess
import os

app = FastAPI()

received_payloads = []

@app.post("/webhook")
async def receive_webhook(request: Request):
    payload = await request.json()
    received_payloads.append(payload)
    return {"status": "ok"}

@app.get("/proxy/{id}")
async def proxy_endpoint(id: str):
    return httpx.Response(500)

def run_capture_server():
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="error")

def main():
    # Start capture server
    threading.Thread(target=run_capture_server, daemon=True).start()
    time.sleep(2)
    
    # Start ProxyMaze on port 8001 using the LATEST code
    env = os.environ.copy()
    proxymaze_proc = subprocess.Popen(
        ["python3", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(3) # Wait for startup
    
    try:
        with httpx.Client() as client:
            # Register webhook
            client.post("http://localhost:8001/webhooks", json={"url": "http://localhost:8080/webhook"})
            
            # Add failing proxies to trigger alert
            client.post("http://localhost:8001/proxies", json={
                "proxies": ["http://localhost:8080/proxy/px-fail"],
                "replace": True
            })
            
            print("\nWaiting for webhook delivery (up to 15s)...")
            for _ in range(15):
                if received_payloads:
                    break
                time.sleep(1)
                
            print("\n--- TEST RESULTS ---")
            if received_payloads:
                print("Webhook Successfully Received!")
                import json
                print(json.dumps(received_payloads[0], indent=2))
            else:
                print("No webhook received.")
            print("--------------------\n")
            
    finally:
        proxymaze_proc.terminate()
        proxymaze_proc.wait()

if __name__ == "__main__":
    main()
