const express = require('express');
const crypto = require('crypto');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
require('dotenv').config();

const app = express();
const port = process.env.PORT || 8000;
const secret = process.env.GITHUB_WEBHOOK_SECRET;
const appDir = __dirname;

// In-memory request logs
const requestLogs = [];
let isDeploying = false;

// Use raw body for signature verification
app.use(express.json({
    verify: (req, res, buf) => {
        req.rawBody = buf;
    }
}));

// Middleware for request logging (After body parsing)
app.use((req, res, next) => {
    // Skip logging for the /requests endpoint itself
    if (req.path === '/requests') {
        return next();
    }

    const logEntry = {
        timestamp: new Date().toISOString(),
        method: req.method,
        path: req.path,
        ip: req.ip || req.headers['x-forwarded-for'] || req.socket.remoteAddress,
        payload: req.body && Object.keys(req.body).length > 0 ? req.body : null
    };
    requestLogs.push(logEntry);
    if (requestLogs.length > 100) requestLogs.shift();
    next();
});

// Verification middleware
function verifySignature(req, res, next) {
    const signature = req.headers['x-hub-signature-256'];
    if (!signature) {
        return res.status(401).send('Signature missing');
    }

    const hmac = crypto.createHmac('sha256', secret);
    const digest = 'sha256=' + hmac.update(req.rawBody).digest('hex');

    if (!crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(digest))) {
        return res.status(401).send('Invalid signature');
    }
    next();
}

app.post('/github', verifySignature, (req, res) => {
    const event = req.headers['x-github-event'];
    
    if (event !== 'push') {
        return res.status(200).send('Event ignored');
    }

    if (isDeploying) {
        return res.status(409).json({ status: "error", message: "Deployment already in progress" });
    }

    isDeploying = true;
    console.log(`[${new Date().toISOString()}] Deployment started...`);

    // Return immediately to GitHub
    res.status(202).json({ status: "deployment started" });

    // Run deployment asynchronously
    const logStream = fs.createWriteStream(path.join(appDir, 'deploy.log'), { flags: 'a' });
    const deploy = spawn('bash', [path.join(appDir, 'run.sh')], {
        cwd: appDir,
        env: { ...process.env, PATH: process.env.PATH },
        shell: true // Prevent command injection by using spawn arguments correctly, 
                    // though here we are running a specific script.
    });

    deploy.stdout.on('data', (data) => {
        logStream.write(`[STDOUT] ${data}`);
        console.log(`STDOUT: ${data}`);
    });

    deploy.stderr.on('data', (data) => {
        logStream.write(`[STDERR] ${data}`);
        console.error(`STDERR: ${data}`);
    });

    deploy.on('close', (code) => {
        isDeploying = false;
        const msg = `[${new Date().toISOString()}] Deployment finished with code ${code}\n`;
        logStream.write(msg);
        console.log(msg);
        logStream.end();
    });
});

app.get('/requests', (req, res) => {
    res.json(requestLogs);
});

app.get('/health', (req, res) => {
    res.json({ status: "ok" });
});

app.listen(port, '0.0.0.0', () => {
    console.log(`Webhook server running on port ${port}`);
});
