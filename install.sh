#!/bin/bash
set -e

USER="$(whoami)"
APP_DIR="/opt/paw_proxy_pilot"
VENV_DIR="$APP_DIR/venv"
REPO_URL="https://github.com/andrew-kemp/squid_allow_app.git"

# === MySQL DB Settings ===
DB_NAME="paw_proxy_pilot"
DB_USER="paw_proxy_pilot_user"
DB_PASS=$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 24)

echo "Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv python3-pam git nginx squid openssl mysql-server libmysqlclient-dev build-essential libpam0g-dev python3-dev

echo "Cloning or updating PAW Proxy Pilot repository..."
if [ ! -d "$APP_DIR" ]; then
    sudo git clone "$REPO_URL" "$APP_DIR"
fi
sudo chown -R "$USER":"$USER" "$APP_DIR"

cd "$APP_DIR"

echo "Ensuring requirements.txt has all Python dependencies..."
grep -qxF "pam" requirements.txt || echo "pam" >> requirements.txt
grep -qxF "pyotp" requirements.txt || echo "pyotp" >> requirements.txt
grep -qxF "mysql-connector-python" requirements.txt || echo "mysql-connector-python" >> requirements.txt
grep -qxF "flask_sqlalchemy" requirements.txt || echo "flask_sqlalchemy" >> requirements.txt
grep -qxF "werkzeug" requirements.txt || echo "werkzeug" >> requirements.txt
grep -qxF "publicsuffix2" requirements.txt || echo "publicsuffix2" >> requirements.txt
grep -qxF "six" requirements.txt || echo "six" >> requirements.txt
grep -qxF "Flask" requirements.txt || echo "Flask" >> requirements.txt

echo "Setting up Python virtual environment..."
rm -rf "$VENV_DIR"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

echo "Configuring MySQL for PAW Proxy Pilot..."

MYSQL="mysql -u root"

$MYSQL <<SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
USE \`${DB_NAME}\`;

-- Enhanced users table for both PAM and MySQL users + MFA + admin
CREATE TABLE IF NOT EXISTS users (
    username VARCHAR(64) PRIMARY KEY,
    password_hash VARCHAR(128),      -- For MySQL users
    mfa_secret VARCHAR(64),
    mfa_enabled TINYINT DEFAULT 0,
    is_local_user TINYINT DEFAULT 0,  -- 1 = MySQL user, 0 = PAM/system user
    admin_level INT DEFAULT 0,        -- 0 = regular, 1+ = admin
    email VARCHAR(255)                -- For password recovery, notifications, etc.
);

-- Allowed domains table
CREATE TABLE IF NOT EXISTS allowed_domains (
    id INT AUTO_INCREMENT PRIMARY KEY,
    domain VARCHAR(255) NOT NULL
);

-- Blocked domains table
CREATE TABLE IF NOT EXISTS blocked_domains (
    id INT AUTO_INCREMENT PRIMARY KEY,
    domain VARCHAR(255) NOT NULL
);

-- Optionally, unconfirmed domains table (if you want to track them separately)
CREATE TABLE IF NOT EXISTS unconfirmed_domains (
    id INT AUTO_INCREMENT PRIMARY KEY,
    domain VARCHAR(255) NOT NULL
);
SQL

echo "Writing DB connection info to db_config.py..."
cat > "$APP_DIR/db_config.py" <<EOF
DB_CONFIG = {
    "host": "localhost",
    "user": "${DB_USER}",
    "password": "${DB_PASS}",
    "database": "${DB_NAME}"
}
EOF
chmod 600 "$APP_DIR/db_config.py"

echo "Copying base allow list..."
sudo cp "$APP_DIR/allowed_paw.acl" /etc/squid/allowed_paw.acl || touch /etc/squid/allowed_paw.acl
sudo chmod 666 /etc/squid/allowed_paw.acl

# ==== BEGIN: Use Working Squid Config ====
echo ""
echo "==== Writing Working Squid Configuration ===="

sudo tee /etc/squid/squid.conf > /dev/null <<EOF
acl localnet src 0.0.0.0-255.255.255.255
acl localnet src 10.0.0.0/8
acl localnet src 100.64.0.0/10
acl localnet src 169.254.0.0/16
acl localnet src 172.16.0.0/12
acl localnet src 192.168.8.0/22 192.168.144.0/20
acl localnet src fc00::/7
acl localnet src fe80::/10

acl SSL_ports port 443
acl Safe_ports port 80
acl Safe_ports port 21
acl Safe_ports port 443
acl Safe_ports port 70
acl Safe_ports port 210
acl Safe_ports port 1025-65535
acl Safe_ports port 280
acl Safe_ports port 488
acl Safe_ports port 591
acl Safe_ports port 777
acl PAW_Access dstdomain "/etc/squid/allowed_paw.acl"

http_access deny !Safe_ports
http_access deny CONNECT !SSL_ports
http_access allow localhost manager
http_access deny manager
http_access allow localhost
http_access deny to_localhost
http_access deny to_linklocal
include /etc/squid/conf.d/*.conf
http_access allow PAW_Access
http_access deny all
http_port 3128
cache_effective_group proxy
EOF

echo "New /etc/squid/squid.conf written."

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

echo "Setting up sudoers for squid restart..."
SUDOERS_LINE="$USER ALL=NOPASSWD: /bin/systemctl restart squid"
sudo grep -qxF "$SUDOERS_LINE" /etc/sudoers || echo "$SUDOERS_LINE" | sudo EDITOR='tee -a' visudo > /dev/null

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
