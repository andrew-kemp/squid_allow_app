#!/bin/bash
set -e

USER="$(whoami)"
APP_DIR="/home/$USER/squid_allow_app"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="squid_allow_app"

echo "Updating Squid Allow List Flask app..."

# Go to app directory
cd "$APP_DIR"

# Pull the latest changes from the remote repository
git pull origin main

# Activate the venv and update dependencies
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

# Restart systemd service
echo "Restarting Flask app systemd service..."
sudo systemctl restart "$SERVICE_NAME"

echo "Update complete!"
