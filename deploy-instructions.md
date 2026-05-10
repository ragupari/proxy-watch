# GitHub Webhook Deployment Instructions

## 1. Prepare your VPS
Ensure Node.js and Git are installed on your Ubuntu Linux server.

```bash
sudo apt update
sudo apt install nodejs npm git
```

## 2. Set up the Webhook Server
Copy the files to your server and install dependencies:

```bash
npm install
cp example.env .env
# Edit .env and set GITHUB_WEBHOOK_SECRET
nano .env
```

## 3. Configure GitHub
1. Go to your GitHub Repository -> Settings -> Webhooks.
2. Click **Add webhook**.
3. **Payload URL**: `http://<your-vps-ip>:8000/github`
4. **Content type**: `application/json`
5. **Secret**: Enter the value you set in `GITHUB_WEBHOOK_SECRET`.
6. **Events**: Select **Just the push event**.
7. Click **Add webhook**.

## 4. Run with PM2
To keep the server running in the background and auto-restart on crashes or reboots:

```bash
sudo npm install -g pm2
pm2 start webhook-server.js --name "github-webhook"
pm2 save
pm2 startup
```

To view logs:
```bash
pm2 logs github-webhook
tail -f deploy.log
```

## 5. Security Notes
- The server uses `crypto.timingSafeEqual` to prevent timing attacks on the signature.
- The deployment script runs asynchronously to avoid GitHub timeout (10s limit).
- A lock mechanism prevents multiple concurrent deployments.
- Ensure your `run.sh` has executable permissions: `chmod +x run.sh`.
