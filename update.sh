#!/bin/bash
set -e

USER="$(whoami)"
APP_DIR="/home/$USER/squid_allow_app"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="squid_allow_app"

echo "Updating Squid PAW Manager..."

# Go to app directory
cd "$APP_DIR"

# Pull the latest changes from the remote repository
git pull origin main

# Activate the venv and update dependencies
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

# Update the allow list from the repo
echo "Updating allow list..."
sudo cp "$APP_DIR/allowed_paw.acl" /etc/squid/allowed_paw.acl
sudo chmod 666 /etc/squid/allowed_paw.acl
# Deploy custom Squid error page
sudo cp ERR_ACCESS_DENIED.html /usr/share/squid/errors/English/ERR_ACCESS_DENIED


# Restart Squid and the app service
echo "Restarting Squid service..."
sudo systemctl restart squid

echo "Restarting Flask app systemd service..."
sudo systemctl restart "$SERVICE_NAME"

echo "Update complete!"
