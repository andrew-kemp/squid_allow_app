import os
import subprocess
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from publicsuffix2 import get_sld
import pam
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'supersecretkey')

SQUID_LOG_FILE = "/var/log/squid/access.log"
ALLOW_LIST_FILE = "/etc/squid/allowed_paw.acl"
HIDDEN_LIST_FILE = "/etc/squid/hidden_domains.txt"

# --- Authentication helpers ---

def is_logged_in():
    return session.get('logged_in', False)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Domain helpers ---

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
    return sorted(clean_domains, key=lambda d: d.lower())

def get_parent_domain(domain):
    parent = get_sld(domain)
    return f".{parent}" if parent and parent != domain else f".{domain}"

def get_allow_list():
    if not os.path.exists(ALLOW_LIST_FILE):
        return []
    with open(ALLOW_LIST_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]

def get_hidden_list():
    if not os.path.exists(HIDDEN_LIST_FILE):
        return []
    with open(HIDDEN_LIST_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]

def add_to_allow_list(domain):
    entry = get_parent_domain(domain)
    current = set(get_allow_list())
    if entry not in current:
        with open(ALLOW_LIST_FILE, "a") as f:
            f.write(entry + "\n")
    # Also remove from hidden if present
    remove_from_hidden_list(domain)

def remove_from_allow_list(entry):
    current = set(get_allow_list())
    if entry in current:
        current.remove(entry)
        with open(ALLOW_LIST_FILE, "w") as f:
            for item in sorted(current, key=lambda d: d.lstrip('.').lower()):
                f.write(item + "\n")

def add_to_hidden_list(domain):
    entry = get_parent_domain(domain)
    current = set(get_hidden_list())
    if entry not in current:
        with open(HIDDEN_LIST_FILE, "a") as f:
            f.write(entry + "\n")

def remove_from_hidden_list(domain_or_entry):
    entry = get_parent_domain(domain_or_entry) if not domain_or_entry.startswith('.') else domain_or_entry
    current = set(get_hidden_list())
    if entry in current:
        current.remove(entry)
        with open(HIDDEN_LIST_FILE, "w") as f:
            for item in sorted(current, key=lambda d: d.lstrip('.').lower()):
                f.write(item + "\n")

def mark_changes_pending():
    session["changes_pending"] = True

def clear_changes_pending():
    session.pop("changes_pending", None)

# --- Login routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        p = pam.pam()
        if p.authenticate(username, password):
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('overview'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- Main routes ---

@app.route('/')
@login_required
def overview():
    allow_list = get_allow_list()
    hidden_list = get_hidden_list()
    blocked_domains = get_blocked_domains()
    allow_set = set(allow_list)
    hidden_set = set(hidden_list)
    # Unconfirmed = domains seen in log, not in allow_list or hidden_list
    unconfirmed = [d for d in blocked_domains 
                   if get_parent_domain(d) not in allow_set and get_parent_domain(d) not in hidden_set]
    return render_template(
        "overview.html",
        allowed_count=len(allow_list),
        blocked_count=len(hidden_list),
        unconfirmed_count=len(unconfirmed),
        changes_pending=session.get("changes_pending", False),
        page='overview'
    )

@app.route("/index", methods=["GET"])
@login_required
def index():
    blocked_domains = get_blocked_domains()
    allow_list = set(get_allow_list())
    hidden_list = set(get_hidden_list())

    display_domains = []
    for domain in blocked_domains:
        parent = get_parent_domain(domain)
        allowed = parent in allow_list
        hidden = parent in hidden_list
        if not allowed and not hidden:
            display_domains.append({
                "domain": domain,
                "parent": parent,
                "allowed": allowed
            })

    display_domains = sorted(display_domains, key=lambda d: d["domain"].lower())
    return render_template(
        "index.html",
        domains=display_domains,
        changes_pending=session.get("changes_pending", False),
        page='blocked'
    )

@app.route("/add_allow", methods=["POST"])
@login_required
def add_allow():
    domain = request.form.get("domain")
    if domain:
        add_to_allow_list(domain)
        mark_changes_pending()
    return redirect(url_for("index"))

@app.route("/remove_blocked", methods=["POST"])
@login_required
def remove_blocked():
    domain = request.form.get("domain")
    if domain:
        add_to_hidden_list(domain)
        mark_changes_pending()
    return redirect(url_for("index"))

@app.route("/bulk_action", methods=["POST"])
@login_required
def bulk_action():
    action = request.form.get('action')
    selected = request.form.getlist('selected_domains')
    referrer = request.referrer or url_for('index')
    if 'allowed' in referrer:
        current_page = 'allowed'
    elif 'removed' in referrer:
        current_page = 'removed'
    else:
        current_page = 'blocked'
    if not selected:
        return redirect(referrer)

    if action == 'allow':
        for domain in selected:
            add_to_allow_list(domain)
        mark_changes_pending()
        return redirect(url_for("allowed"))
    elif action == 'remove':
        if current_page == 'allowed':
            for entry in selected:
                remove_from_allow_list(entry)
            mark_changes_pending()
            return redirect(url_for("allowed"))
        elif current_page == 'removed':
            for entry in selected:
                remove_from_hidden_list(entry)
            return redirect(url_for("view_removed"))
        else:  # blocked
            for domain in selected:
                add_to_hidden_list(domain)
            mark_changes_pending()
            return redirect(url_for("index"))

    return redirect(referrer)

@app.route("/allowed", methods=["GET"])
@login_required
def allowed():
    allow_list = get_allow_list()
    domains = [{"domain": d} for d in sorted(allow_list, key=lambda d: d.lstrip('.').lower())]
    return render_template(
        "allowed.html",
        domains=domains,
        changes_pending=session.get("changes_pending", False),
        page='allowed'
    )

@app.route("/remove_allow", methods=["POST"])
@login_required
def remove_allow():
    entry = request.form.get("domain") or request.form.get("entry")
    if entry:
        remove_from_allow_list(entry)
        mark_changes_pending()
    return redirect(url_for("allowed"))

@app.route("/view_removed", methods=["GET"])
@login_required
def view_removed():
    hidden_domains = sorted(get_hidden_list(), key=lambda d: d.lstrip('.').lower())
    domains = [{"domain": d} for d in hidden_domains]
    return render_template(
        "removed.html",
        domains=domains,
        changes_pending=session.get("changes_pending", False),
        page='removed'
    )

@app.route("/restore_domains", methods=["POST"])
@login_required
def restore_domains():
    selected = request.form.getlist('selected_domains')
    if not selected:
        return redirect(url_for('view_removed'))
    for entry in selected:
        remove_from_hidden_list(entry)
    return redirect(url_for('view_removed'))

@app.route("/restore_domain", methods=["POST"])
@login_required
def restore_domain():
    domain = request.form.get("domain")
    if domain:
        remove_from_hidden_list(domain)
    return redirect(url_for('view_removed'))

@app.route("/restart_squid", methods=["POST"])
@login_required
def restart_squid():
    try:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            result = subprocess.run(
                ["/usr/bin/systemctl", "restart", "squid"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                return jsonify({"status": "error", "message": result.stderr}), 500
            status = subprocess.run(
                ["/usr/bin/systemctl", "is-active", "squid"],
                capture_output=True, text=True
            )
            if status.stdout.strip() != "active":
                return jsonify({"status": "error", "message": status.stdout + status.stderr}), 500
            clear_changes_pending()
            return jsonify({"status": "ok"})
        result = subprocess.run(
            ["/usr/bin/systemctl", "restart", "squid"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return f"Error restarting squid:<br><pre>{result.stderr}</pre>", 500
        status = subprocess.run(
            ["/usr/bin/systemctl", "is-active", "squid"],
            capture_output=True, text=True
        )
        if status.stdout.strip() != "active":
            return f"Squid did not start successfully.<br><pre>{status.stdout} {status.stderr}</pre>", 500
        clear_changes_pending()
        return redirect(request.referrer or url_for("overview"))
    except Exception as e:
        return f"Exception: {e}", 500

@app.route("/clear_changes", methods=["POST"])
@login_required
def clear_changes():
    clear_changes_pending()
    return redirect(request.referrer or url_for("overview"))

@app.route('/clients')
@login_required
def clients():
    clients = {}
    if os.path.exists(SQUID_LOG_FILE):
        with open(SQUID_LOG_FILE, "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) > 2:
                    ip = parts[2]
                    domain = parts[6] if len(parts) > 6 else ""
                    clients.setdefault(ip, []).append(domain)
    return render_template("clients.html", clients=clients, changes_pending=session.get("changes_pending", False))

# Allow static files without login
@app.before_request
def exclude_static():
    if request.endpoint and request.endpoint.startswith('static'):
        return

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
