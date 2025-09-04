#!/bin/bash
set -e

USER="$(whoami)"
APP_DIR="/home/$USER/squid_allow_app"
VENV_DIR="$APP_DIR/venv"

echo "Installing dependencies..."
sudo apt-get install -y python3 python3-pip python3-venv git nginx squid openssl

echo "Cloning your Flask app..."
if [ ! -d "$APP_DIR" ]; then
    git clone https://github.com/andrew-kemp/squid_allow_app.git "$APP_DIR"
fi

cd "$APP_DIR"

echo "Setting up Python virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

echo "Configuring Squid to block all and use allow list..."
sudo touch /etc/squid/allowed_paw.acl
sudo chmod o+w /etc/squid/allowed_paw.acl

# Insert allow rules before any deny all!
sudo sed -i '/http_access deny all/i \
# Squid allow list management\n\
acl paw_access dstdomain "/etc/squid/allowed_paw.acl"\n\
http_access allow paw_access\n' /etc/squid/squid.conf

sudo systemctl restart squid

echo "Setting up sudoers for squid restart..."
SUDOERS_LINE="$USER ALL=NOPASSWD: /bin/systemctl restart squid"
if ! sudo grep -q "$SUDOERS_LINE" /etc/sudoers; then
    echo "$SUDOERS_LINE" | sudo EDITOR='tee -a' visudo > /dev/null
fi

echo "Generating self-signed SSL cert for nginx..."
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/squid_allow_app.key \
    -out /etc/nginx/ssl/squid_allow_app.crt \
    -subj "/CN=$(hostname)"

echo "Configuring nginx reverse proxy for Flask app..."
sudo tee /etc/nginx/sites-available/squid_allow_app > /dev/null <<NGINXCONF
server {
    listen 443 ssl;
    server_name _;

    ssl_certificate /etc/nginx/ssl/squid_allow_app.crt;
    ssl_certificate_key /etc/nginx/ssl/squid_allow_app.key;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINXCONF

sudo ln -sf /etc/nginx/sites-available/squid_allow_app /etc/nginx/sites-enabled/squid_allow_app
sudo systemctl restart nginx

echo "Creating systemd service for Flask app..."
sudo tee /etc/systemd/system/squid_allow_app.service > /dev/null <<EOF
[Unit]
Description=Squid Allow List Flask App
After=network.target

[Service]
User=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/python app.py

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable squid_allow_app
sudo systemctl start squid_allow_app

echo "All setup complete!"
echo "Access your app at https://$(hostname -I | awk '{print $1}')/"
