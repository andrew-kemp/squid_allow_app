import os
import subprocess
from flask import Flask, render_template, request, redirect, url_for
from publicsuffix2 import get_sld

app = Flask(__name__)

SQUID_LOG_FILE = "/var/log/squid/access.log"
ALLOW_LIST_FILE = "/etc/squid/allowed_paw.acl"

def get_blocked_domains():
    domains = set()
    if os.path.exists(SQUID_LOG_FILE):
        with open(SQUID_LOG_FILE, "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) > 6:
                    domain = parts[6]
                    if domain and not domain.startswith("http:") and not domain.startswith("https:"):
                        domains.add(domain)
    clean_domains = set()
    for domain in domains:
        if ':' in domain:
            domain = domain.split(':')[0]
        if domain.startswith("www."):
            domain = domain[4:]
        clean_domains.add(domain)
    return sorted(clean_domains)

def get_parent_domain(domain):
    parent = get_sld(domain)
    return f".{parent}" if parent and parent != domain else f".{domain}"

def get_allow_list():
    if not os.path.exists(ALLOW_LIST_FILE):
        return set()
    with open(ALLOW_LIST_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())

def add_to_allow_list(domain):
    entry = get_parent_domain(domain)
    current = get_allow_list()
    if entry not in current:
        with open(ALLOW_LIST_FILE, "a") as f:
            f.write(entry + "\n")

@app.route("/", methods=["GET"])
def index():
    blocked_domains = get_blocked_domains()
    allow_list = get_allow_list()

    display_domains = []
    for domain in blocked_domains:
        parent = get_parent_domain(domain)
        allowed = parent in allow_list
        # Only show domains NOT already allowed
        if not allowed:
            display_domains.append({
                "domain": domain,
                "parent": parent,
                "allowed": allowed
            })

    return render_template("index.html", domains=display_domains)

@app.route("/add_allow", methods=["POST"])
def add_allow():
    domain = request.form.get("domain")
    if domain:
        add_to_allow_list(domain)
    return redirect(url_for("index"))

@app.route("/restart_squid", methods=["POST"])
def restart_squid():
    try:
        # Restart Squid
        result = subprocess.run(
            ["/usr/bin/systemctl", "restart", "squid"],
            capture_output=True, text=True
        )
        # Check if restart succeeded
        if result.returncode != 0:
            return f"Error restarting squid:<br><pre>{result.stderr}</pre>", 500
        # Validate Squid is running
        status = subprocess.run(
            ["/usr/bin/systemctl", "is-active", "squid"],
            capture_output=True, text=True
        )
        if status.stdout.strip() != "active":
            return f"Squid did not start successfully.<br><pre>{status.stdout} {status.stderr}</pre>", 500
        return redirect(url_for("index"))
    except Exception as e:
        return f"Exception: {e}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
