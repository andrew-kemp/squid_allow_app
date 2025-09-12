#!/bin/bash
set -e

# CONFIGURABLE VARIABLES
APP_USER="squidallow"                  # Set this to the correct user that owns/runs the app
APP_DIR="/opt/squid_allow_app"         # The new standard install path
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="squid_allow_app"

ALLOW_LIST_SRC="$APP_DIR/allowed_paw.acl"
ALLOW_LIST_DEST="/etc/squid/allowed_paw.acl"
SQUID_ERR_SRC="$APP_DIR/ERR_ACCESS_DENIED.html"
SQUID_ERR_DEST="/usr/share/squid/errors/English/ERR_ACCESS_DENIED"

# --- UPDATE START ---
echo "Updating Squid Allow Manager..."

# Ensure script is run as the correct user
if [[ "$(whoami)" != "$APP_USER" ]]; then
    echo "This script must be run as $APP_USER (current: $(whoami))."
    exit 1
fi

cd "$APP_DIR"

echo "Pulling latest code from git..."
git pull origin main

echo "Activating virtual environment and updating dependencies..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

echo "Updating allow list..."
sudo cp "$ALLOW_LIST_SRC" "$ALLOW_LIST_DEST"
sudo chmod 666 "$ALLOW_LIST_DEST"

echo "Deploying Squid custom error page..."
sudo cp "$SQUID_ERR_SRC" "$SQUID_ERR_DEST"

echo "Restarting Squid service..."
sudo systemctl restart squid

echo "Restarting Flask app systemd service..."
sudo systemctl restart "$SERVICE_NAME"

echo "Update complete!"
