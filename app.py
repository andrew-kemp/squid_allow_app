from flask import Flask, render_template, redirect
import subprocess
import os

# CONFIGURATION
SQUID_LOG_FILE = '/var/log/squid/access.log'
ALLOW_LIST_FILE = '/etc/squid/allowed_paw.acl'

app = Flask(__name__)

def get_blocked_domains():
    """Parse Squid log and extract unique blocked domains."""
    domains = set()
    if not os.path.exists(SQUID_LOG_FILE):
        return domains

    with open(SQUID_LOG_FILE) as f:
        for line in f:
            if 'TCP_DENIED' in line:
                parts = line.split()
                # Squid log format: timestamp action code client user method URL ...
                # Find the URL part (usually index 6)
                try:
                    url = parts[6]
                    # Extract domain from URL
                    if url.startswith('http'):
                        domain = url.split('/')[2]
                        domains.add(domain)
                except IndexError:
                    continue
    return sorted(domains)

def add_to_allow_list(domain):
    """Add domain to allow list and reload Squid."""
    # Check if already allowed
    with open(ALLOW_LIST_FILE, 'r') as f:
        lines = f.readlines()
    entry = f'.{domain}\n'
    if entry not in lines and domain not in [line.strip() for line in lines]:
        with open(ALLOW_LIST_FILE, 'a') as f:
            f.write(entry)
    # Reload Squid
    subprocess.run(['sudo', 'systemctl', 'reload', 'squid'])

@app.route('/')
def index():
    domains = get_blocked_domains()
    return render_template('index.html', domains=domains)

@app.route('/add/<domain>', methods=['POST'])
def add(domain):
    add_to_allow_list(domain)
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
