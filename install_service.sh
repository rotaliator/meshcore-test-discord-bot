#!/bin/bash
# Install testbot service
# Run as root: sudo bash install_service.sh

SERVICE_FILE="testbot.service"
SERVICE_DEST="/etc/systemd/system/testbot.service"

if [ ! -f "$SERVICE_FILE" ]; then
    echo "Error: $SERVICE_FILE not found in current directory."
    exit 1
fi

cp "$SERVICE_FILE" "$SERVICE_DEST"
chmod 644 "$SERVICE_DEST"
systemctl daemon-reload
systemctl enable testbot.service
systemctl start testbot.service
echo "Service installed and started."
