#!/bin/bash
set -e

USER="$(whoami)"
APP_DIR="/home/$USER/squid_allow_app"
VENV_DIR="$APP_DIR/venv"

echo "Installing dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv git nginx squid openssl

echo "Cloning Flask app..."
if [ ! -d "$APP_DIR" ]; then
    git clone https://github.com/andrew-kemp/squid_allow_app.git "$APP_DIR"
fi

cd "$APP_DIR"

echo "Setting up Python virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

echo "Copying base allow list..."
sudo cp "$APP_DIR/allowed_paw.acl" /etc/squid/allowed_paw.acl
sudo chmod 666 /etc/squid/allowed_paw.acl

# ==== BEGIN: Secure Squid Config Generation ====
echo ""
echo "==== Squid Secure Network/Host Configuration ===="

read -p "Enter the PAW subnet(s) to allow (comma or space separated, e.g. 10.1.2.0/24,10.2.3.0/24): " PAW_SUBNETS
PAW_SUBNETS="${PAW_SUBNETS//,/ }"

DEFAULT_IP=$(hostname -I | awk '{print $1}')
read -p "Enter the internal IP address for this proxy server [${DEFAULT_IP}]: " SQUID_IP
SQUID_IP=${SQUID_IP:-$DEFAULT_IP}

echo ""
echo "PAW subnets: $PAW_SUBNETS"
echo "Proxy IP: $SQUID_IP"

read -p "Proceed with these Squid settings? [y/N]: " CONFIRM
if [[ ! $CONFIRM =~ ^[Yy]$ ]]; then
    echo "Aborting Squid configuration."
    exit 1
fi

# Backup old squid.conf
if [ -f /etc/squid/squid.conf ]; then
    sudo cp /etc/squid/squid.conf /etc/squid/squid.conf.bak.$(date +%F_%T)
    echo "Existing squid.conf backed up."
fi

sudo tee /etc/squid/squid.conf > /dev/null <<EOF
# Squid Proxy for PAW/AVD - Minimal Hardened Configuration

http_port $SQUID_IP:3128
visible_hostname paw-avd-proxy

# Allow only specified PAW subnets
acl avd_paws src $PAW_SUBNETS

# Allow-list of destination domains (managed separately)
acl allowed_domains dstdomain "/etc/squid/allowed_paw.acl"

# Only allow HTTP and HTTPS ports
acl Safe_ports port 80
acl SSL_ports port 443

http_access deny !Safe_ports
http_access deny CONNECT !SSL_ports

# Allow access only from PAW subnets to allowed domains
http_access allow avd_paws allowed_domains

# Deny all other requests
http_access deny all

# Disable all caching (optional for PAW)
cache deny all

# Hide client details and Squid version
forwarded_for delete
via off

# Limit request and reply sizes
request_body_max_size 10 MB
reply_body_max_size 50 MB

# DNS hardening
dns_v4_first on

# Logging
access_log /var/log/squid/access.log
cache_log /var/log/squid/cache.log
logfile_rotate 14

# Resource tuning
cache_mem 64 MB
maximum_object_size_in_memory 128 KB

# End of config
EOF

echo "New /etc/squid/squid.conf written."

if [ ! -f /etc/squid/allowed_paw.acl ]; then
    echo "---------------------------------------------"
    echo "WARNING: /etc/squid/allowed_paw.acl does NOT exist."
    echo "Please create this file with one domain per line, e.g.:"
    echo "  .windowsupdate.com"
    echo "  .microsoft.com"
    echo "  .azure.com"
    echo "---------------------------------------------"
fi

sudo systemctl restart squid

# ==== END: Secure Squid Config Generation ====

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
echo "Access your app at https://$SQUID_IP/"
