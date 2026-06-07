#!/bin/bash

echo "🚀 Deploying ITAM Edge Agent Architecture..."

APP_DIR="/home/djezzy"
PYTHON_BIN="/usr/bin/python3"

# 1. Install required packages
echo "📦 Installing system dependencies..."
sudo apt update && sudo apt install python3 python3-pip -y
pip3 install flask psutil requests --break-system-packages

# 2. Create the ITAM Local Edge Server Service
echo "⚙️ Creating Edge Server Service..."
cat <<EOF | sudo tee /etc/systemd/system/itam-server.service
[Unit]
Description=ITAM Local Edge Analyzer
After=network.target

[Service]
ExecStart=$PYTHON_BIN $APP_DIR/server.py
WorkingDirectory=$APP_DIR
User=djezzy
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 3. Create the ITAM Sync Service
echo "⚙️ Creating Edge Sync Service..."
cat <<EOF | sudo tee /etc/systemd/system/itam-sync.service
[Unit]
Description=ITAM Central Sync Service
After=network.target itam-server.service

[Service]
ExecStart=$PYTHON_BIN $APP_DIR/sync_service.py
WorkingDirectory=$APP_DIR
User=djezzy
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 4. Reload systemd and start services
echo "⚡ Starting background services..."
sudo systemctl daemon-reload
sudo systemctl enable itam-server.service
sudo systemctl enable itam-sync.service
sudo systemctl start itam-server.service
sudo systemctl start itam-sync.service

# 5. Set up the Cron job for the collector (runs every minute)
echo "⏱️ Configuring collector cron job..."
(crontab -l 2>/dev/null | grep -v "collector_linux.py"; echo "* * * * * $PYTHON_BIN $APP_DIR/collector_linux.py") | crontab -

echo "✅ Deployment Complete! The ITAM agent is now running permanently in the background."
