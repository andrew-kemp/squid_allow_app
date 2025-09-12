#!/bin/bash
set -e

USER="$(whoami)"
APP_DIR="/opt/paw_proxy_pilot"
VENV_DIR="$APP_DIR/venv"
REPO_URL="https://github.com/andrew-kemp/squid_allow_app.git"

echo "Installing dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv python3-pam git nginx squid openssl

echo "Cloning or updating PAW Proxy Pilot repository..."
if [ ! -d "$APP_DIR" ]; then
    sudo git clone "$REPO_URL" "$APP_DIR"
fi
sudo chown -R "$USER":"$USER" "$APP_DIR"

cd "$APP_DIR"

echo "Ensuring pam is in requirements.txt..."
if ! grep -q "^pam" requirements.txt; then
    echo "pam" >> requirements.txt
fi

echo "Setting up Python virtual environment..."
if [ -d "$VENV_DIR" ]; then
    rm -rf "$VENV_DIR"
fi
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

echo "Copying base allow list..."
sudo cp "$APP_DIR/allowed_paw.acl" /etc/squid/allowed_paw.acl
sudo chmod 666 /etc/squid/allowed_paw.acl

# ==== BEGIN: Use Working Squid Config ====
echo ""
echo "==== Writing Working Squid Configuration ===="

sudo tee /etc/squid/squid.conf > /dev/null <<EOF
acl localnet src 0.0.0.0-255.255.255.255 # RFC 1122 "this" network (LAN)
acl localnet src 10.0.0.0/8 # RFC 1918 local private network (LAN)
acl localnet src 100.64.0.0/10 # RFC 6598 shared address space (CGN)
acl localnet src 169.254.0.0/16 # RFC 3927 link-local (directly plugged) machines
acl localnet src 172.16.0.0/12 # RFC 1918 local private network (LAN)
acl localnet src 192.168.8.0/22 192.168.144.0/20 # RFC 1918 local private network (LAN)
acl localnet src fc00::/7 # RFC 4193 local private network range
acl localnet src fe80::/10 # RFC 4291 link-local (directly plugged) machines

acl SSL_ports port 443
acl Safe_ports port 80 # http
acl Safe_ports port 21 # ftp
acl Safe_ports port 443 # https
acl Safe_ports port 70 # gopher
acl Safe_ports port 210 # wais
acl Safe_ports port 1025-65535 # unregistered ports
acl Safe_ports port 280 # http-mgmt
acl Safe_ports port 488 # gss-http
acl Safe_ports port 591 # filemaker
acl Safe_ports port 777 # multiling http
acl PAW_Access dstdomain "/etc/squid/allowed_paw.acl"

# Deny requests to certain unsafe ports
http_access deny !Safe_ports

# Deny CONNECT to other than secure SSL ports
http_access deny CONNECT !SSL_ports

# Only allow cachemgr access from localhost
http_access allow localhost manager
http_access deny manager

http_access allow localhost

http_access deny to_localhost

# Protect cloud servers that provide local users with sensitive info about
# their server via certain well-known link-local (a.k.a. APIPA) addresses.
http_access deny to_linklocal

include /etc/squid/conf.d/*.conf

http_access allow PAW_Access
http_access deny all

# Squid normally listens to port 3128
http_port 3128

cache_effective_group proxy
EOF

echo "New /etc/squid/squid.conf written."

# Deploy custom Squid error page if you have one
if [ -f ERR_ACCESS_DENIED.html ]; then
    sudo cp ERR_ACCESS_DENIED.html /usr/share/squid/errors/English/ERR_ACCESS_DENIED
fi

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

# ==== END: Use Working Squid Config ====

echo "Setting up sudoers for squid restart..."
SUDOERS_LINE="$USER ALL=NOPASSWD: /bin/systemctl restart squid"
if ! sudo grep -q "$SUDOERS_LINE" /etc/sudoers; then
    echo "$SUDOERS_LINE" | sudo EDITOR='tee -a' visudo > /dev/null
fi

echo "Generating self-signed SSL cert for nginx..."
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/paw_proxy_pilot.key \
    -out /etc/nginx/ssl/paw_proxy_pilot.crt \
    -subj "/CN=$(hostname)"

echo "Configuring nginx reverse proxy for PAW Proxy Pilot..."
sudo tee /etc/nginx/sites-available/paw_proxy_pilot > /dev/null <<NGINXCONF
server {
    listen 443 ssl;
    server_name _;

    ssl_certificate /etc/nginx/ssl/paw_proxy_pilot.crt;
    ssl_certificate_key /etc/nginx/ssl/paw_proxy_pilot.key;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINXCONF

sudo ln -sf /etc/nginx/sites-available/paw_proxy_pilot /etc/nginx/sites-enabled/paw_proxy_pilot
sudo systemctl restart nginx

echo "Creating systemd service for PAW Proxy Pilot..."
sudo tee /etc/systemd/system/paw_proxy_pilot.service > /dev/null <<EOF
[Unit]
Description=PAW Proxy Pilot Flask App
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
sudo systemctl enable paw_proxy_pilot
sudo systemctl restart paw_proxy_pilot

echo "All setup complete!"
echo "Access PAW Proxy Pilot at https://$(hostname -I | awk '{print $1}')/"