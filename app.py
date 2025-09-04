import os
import subprocess
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = 'change_this_to_a_secret_key'

ALLOWED_PAW_ACL = "/etc/squid/allowed_paw.acl"

def get_allow_list():
    if not os.path.exists(ALLOWED_PAW_ACL):
        return set()
    with open(ALLOWED_PAW_ACL) as f:
        return set(line.strip() for line in f if line.strip())

def get_blocked_domains():
    # Replace this with your actual blocked domain parsing logic
    # For demo: imagine it's a static list or parsed from a log file
    return [
        "example.com",
        "testsite.net",
        "blocked.org",
        "alloweddomain.com"
    ]

def get_parent_domain(domain):
    # Simple parent domain extraction (you can make this more robust)
    return domain

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        domain = request.form.get("domain")
        parent = get_parent_domain(domain)
        allow_list = get_allow_list()
        # Only add if not already present
        if parent and parent not in allow_list:
            with open(ALLOWED_PAW_ACL, "a") as f:
                f.write(parent + "\n")
        # Try to restart squid and show error if it fails
        try:
            subprocess.run(["sudo", "systemctl", "restart", "squid"], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            flash(f"Error restarting squid: {e.stderr.decode()}", "danger")
        return redirect(url_for("index"))

    blocked_domains = get_blocked_domains()
    allow_list = get_allow_list()
    show_only_blocked = request.args.get("blockedonly", "0") == "1"

    display_domains = []
    for domain in blocked_domains:
        parent = get_parent_domain(domain)
        allowed = parent in allow_list
        # If show_only_blocked, skip already allowed ones
        if show_only_blocked and allowed:
            continue
        display_domains.append({
            "domain": domain,
            "parent": parent,
            "allowed": allowed
        })
    return render_template("index.html", domains=display_domains, show_only_blocked=show_only_blocked)

@app.route("/refresh")
def refresh():
    # Just redirects to homepage with blockedonly=1 for convenience
    return redirect(url_for("index", blockedonly=1))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
