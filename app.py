import os
import subprocess
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from publicsuffix2 import get_sld
from functools import wraps
from datetime import datetime
import mysql.connector
import pyotp

from db_config import DB_CONFIG

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'supersecretkey')

SQUID_LOG_FILE = "/var/log/squid/access.log"
ALLOW_LIST_FILE = "/etc/squid/allowed_paw.acl"
HIDDEN_LIST_FILE = "/etc/squid/hidden_domains.txt"

# --- MySQL helpers for user/MFA management ---

def get_mysql_conn():
    return mysql.connector.connect(**DB_CONFIG)

def get_user(username):
    with get_mysql_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        return cursor.fetchone()

def get_user_by_id(user_id):
    with get_mysql_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
        return cursor.fetchone()

def get_all_users():
    with get_mysql_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users")
        return cursor.fetchall()

def add_user(username, email, password, admin_level=0):
    with get_mysql_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, email, password, admin_level, mfa_enabled) VALUES (%s, %s, %s, %s, 0)",
            (username, email, password, admin_level)
        )
        conn.commit()

def delete_user(user_id):
    with get_mysql_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()

def set_user_password(user_id, password):
    with get_mysql_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password=%s WHERE id=%s", (password, user_id))
        conn.commit()

def set_user_admin_level(user_id, admin_level):
    with get_mysql_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET admin_level=%s WHERE id=%s", (admin_level, user_id))
        conn.commit()

def reset_user_mfa(user_id):
    with get_mysql_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET mfa_secret=NULL, mfa_enabled=0 WHERE id=%s", (user_id,))
        conn.commit()

def set_user_mfa(username, secret):
    with get_mysql_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET mfa_secret=%s, mfa_enabled=1 WHERE username=%s", (secret, username))
        conn.commit()

def get_user_mfa(username):
    with get_mysql_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT mfa_secret, mfa_enabled FROM users WHERE username=%s", (username,))
        row = cursor.fetchone()
        return row if row else (None, 0)

def check_user_exists(username):
    with get_mysql_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE username=%s", (username,))
        return cursor.fetchone() is not None

# --- Authentication helpers ---

def is_logged_in():
    return session.get('logged_in', False)

def is_admin():
    return session.get('admin_level', 0) > 0

def is_god():
    return session.get('admin_level', 0) == 99

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_logged_in():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Enforce initial setup if no users exist ---
@app.before_request
def enforce_first_user_setup():
    if request.endpoint in ['static', 'setup', 'setup_mfa']:
        return
    with get_mysql_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        (user_count,) = cursor.fetchone()
        if user_count == 0:
            if request.endpoint != 'setup' and not request.path.startswith('/setup'):
                return redirect(url_for('setup'))

# --- Allow static files without login ---
@app.before_request
def allow_static_files():
    if request.endpoint and request.endpoint.startswith('static'):
        return

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

# --- Initial Setup Wizard ---

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    with get_mysql_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        (user_count,) = cursor.fetchone()
        if user_count > 0:
            return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        password2 = request.form['password2']
        email = request.form['email'].strip()
        if not username or not password or not password2 or not email:
            flash('All fields are required.', 'danger')
            return render_template('setup.html')
        if password != password2:
            flash('Passwords do not match.', 'danger')
            return render_template('setup.html')
        if check_user_exists(username):
            flash('Username already exists.', 'danger')
            return render_template('setup.html')
        add_user(username, email, password, admin_level=99)
        session['pending_user'] = username
        session['pending_admin_level'] = 99
        return redirect(url_for('setup_mfa'))

    return render_template('setup.html')

@app.route('/setup_mfa', methods=['GET', 'POST'])
def setup_mfa():
    username = session.get('pending_user')
    if not username:
        return redirect(url_for('login'))
    secret = session.get('mfa_secret')
    if not secret:
        secret = pyotp.random_base32()
        session['mfa_secret'] = secret
    qr_uri = pyotp.totp.TOTP(secret).provisioning_uri(username, issuer_name="PAW Proxy Pilot")
    if request.method == 'POST':
        code = request.form['code'].replace(" ", "")
        if not code.isdigit() or len(code) != 6 or not pyotp.TOTP(secret).verify(code):
            flash('Invalid MFA code. Try again.', 'danger')
            return render_template('mfa_setup.html', secret=secret, qr_uri=qr_uri)
        set_user_mfa(username, secret)
        user = get_user(username)
        session.clear()
        session['logged_in'] = True
        session['username'] = username
        session['admin_level'] = user.get('admin_level', 0)
        flash('Setup complete! You are now logged in.', 'success')
        return redirect(url_for('index'))
    return render_template('mfa_setup.html', secret=secret, qr_uri=qr_uri)

# --- MFA routes (for regular users) ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_user(username)
        if not user:
            flash('User not found in database', 'danger')
            return render_template('login.html')
        with get_mysql_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users WHERE username=%s AND password=%s", (username, password))
            authed = cursor.fetchone() is not None
        if not authed:
            flash('Invalid username or password', 'danger')
            return render_template('login.html')
        secret, enabled = get_user_mfa(username)
        session['pending_user'] = username
        session['pending_admin_level'] = user.get('admin_level', 0)
        if not secret or not enabled:
            return redirect(url_for('mfa_setup_route'))
        else:
            return redirect(url_for('mfa_verify'))
    return render_template('login.html')

@app.route('/mfa_setup', methods=['GET', 'POST'])
def mfa_setup_route():
    username = session.get('pending_user')
    if not username:
        return redirect(url_for('login'))

    if request.method == 'POST':
        secret = session.get('mfa_secret')
        if not secret:
            flash('Session expired. Please try again.', 'danger')
            return redirect(url_for('login'))
        code = request.form['code'].replace(" ", "")
        if not code.isdigit() or len(code) != 6:
            flash('Invalid code format. Enter a 6-digit code from your authenticator app, without spaces.', 'danger')
            qr_uri = pyotp.totp.TOTP(secret).provisioning_uri(username, issuer_name="PAW Proxy Pilot")
            return render_template('mfa_setup.html', secret=secret, qr_uri=qr_uri)
        if pyotp.TOTP(secret).verify(code):
            set_user_mfa(username, secret)
            session['logged_in'] = True
            session['username'] = username
            session['admin_level'] = session.pop('pending_admin_level', 0)
            session.pop('pending_user', None)
            session.pop('mfa_secret', None)
            return redirect(url_for('index'))
        else:
            flash('Invalid MFA code, try again.', 'danger')
            qr_uri = pyotp.totp.TOTP(secret).provisioning_uri(username, issuer_name="PAW Proxy Pilot")
            return render_template('mfa_setup.html', secret=secret, qr_uri=qr_uri)
    else:
        secret = pyotp.random_base32()
        session['mfa_secret'] = secret
        qr_uri = pyotp.totp.TOTP(secret).provisioning_uri(username, issuer_name="PAW Proxy Pilot")
        return render_template('mfa_setup.html', secret=secret, qr_uri=qr_uri)

@app.route('/mfa_verify', methods=['GET', 'POST'])
def mfa_verify():
    username = session.get('pending_user')
    if not username:
        return redirect(url_for('login'))
    secret, enabled = get_user_mfa(username)
    if not secret or not enabled:
        return redirect(url_for('mfa_setup_route'))
    if request.method == 'POST':
        code = request.form['code'].replace(" ", "")
        if not code.isdigit() or len(code) != 6:
            flash('Invalid code format. Enter a 6-digit code from your authenticator app, without spaces.', 'danger')
            return render_template('mfa_verify.html')
        if pyotp.TOTP(secret).verify(code):
            session['logged_in'] = True
            session['username'] = username
            session['admin_level'] = session.pop('pending_admin_level', 0)
            session.pop('pending_user', None)
            return redirect(url_for('index'))
        else:
            flash('Invalid MFA code, try again.', 'danger')
    return render_template('mfa_verify.html')

@app.route('/logout', methods=['POST', 'GET'])
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- Overview (dashboard) ---

@app.route("/")
@login_required
def index():
    allow_list = get_allow_list()
    hidden_list = get_hidden_list()
    blocked_domains = get_blocked_domains()
    allow_set = set(allow_list)
    hidden_set = set(hidden_list)
    unconfirmed = [d for d in blocked_domains
                   if get_parent_domain(d) not in allow_set and get_parent_domain(d) not in hidden_set]
    clients = {}
    if os.path.exists(SQUID_LOG_FILE):
        with open(SQUID_LOG_FILE, "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) > 2:
                    ip = parts[2]
                    try:
                        timestamp = float(parts[0])
                        last_connected = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        last_connected = "Unknown"
                    if ip not in clients or last_connected > clients[ip]:
                        clients[ip] = last_connected

    return render_template(
        "index.html",
        allowed_count=len(allow_list),
        blocked_count=len(hidden_list),
        unconfirmed_count=len(unconfirmed),
        clients=clients,
        page='overview',
        changes_pending=session.get("changes_pending", False)
    )

# --- Manage Users (God Admin and User Admins, with permissions) ---

@app.route('/admin/users')
@login_required
def admin_users():
    current_level = session.get('admin_level', 0)
    with get_mysql_conn() as conn:
        cursor = conn.cursor(dictionary=True)
        if current_level == 99:
            cursor.execute("SELECT * FROM users")
        else:
            cursor.execute("SELECT * FROM users WHERE admin_level < %s", (99,))
        users = cursor.fetchall()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
def admin_users_add():
    current_level = session.get('admin_level', 0)
    if current_level < 1:
        flash("Insufficient permission", "danger")
        return redirect(url_for('admin_users'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        admin_level = int(request.form.get('admin_level', 0))
        if admin_level >= current_level and current_level != 99:
            flash("Cannot assign a higher or equal admin level", "danger")
            return redirect(url_for('admin_users_add'))
        if not username or not email or not password:
            flash('All fields required', 'danger')
            return redirect(url_for('admin_users_add'))
        if check_user_exists(username):
            flash('Username exists', 'danger')
            return redirect(url_for('admin_users_add'))
        add_user(username, email, password, admin_level)
        flash('User added', 'success')
        return redirect(url_for('admin_users'))
    return render_template('admin_users_add.html')

@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_users_edit(user_id):
    current_level = session.get('admin_level', 0)
    user = get_user_by_id(user_id)
    if not user or (current_level < 99 and user['admin_level'] >= 99):
        flash('Insufficient permission', 'danger')
        return redirect(url_for('admin_users'))
    if request.method == 'POST':
        email = request.form['email']
        admin_level = int(request.form.get('admin_level', 0))
        if admin_level >= current_level and current_level != 99:
            flash("Cannot assign a higher or equal admin level", "danger")
            return redirect(url_for('admin_users_edit', user_id=user_id))
        with get_mysql_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET email=%s, admin_level=%s WHERE id=%s", (email, admin_level, user_id))
            conn.commit()
        flash('User updated', 'success')
        return redirect(url_for('admin_users'))
    return render_template('admin_users_edit.html', user=user)

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_users_delete(user_id):
    current_level = session.get('admin_level', 0)
    user = get_user_by_id(user_id)
    if not user or (current_level < 99 and user['admin_level'] >= 99):
        flash("Insufficient permission", "danger")
        return redirect(url_for('admin_users'))
    if session.get("username") == user.get('username'):
        flash("Cannot delete yourself", "danger")
        return redirect(url_for('admin_users'))
    delete_user(user_id)
    flash("User deleted", "success")
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/reset_password', methods=['GET', 'POST'])
@login_required
def admin_users_reset_password(user_id):
    current_level = session.get('admin_level', 0)
    user = get_user_by_id(user_id)
    if not user or (current_level < 99 and user['admin_level'] >= 99):
        flash('Insufficient permission', 'danger')
        return redirect(url_for('admin_users'))
    if request.method == 'POST':
        password = request.form['password']
        if not password:
            flash('Password required', 'danger')
            return redirect(url_for('admin_users_reset_password', user_id=user_id))
        set_user_password(user_id, password)
        flash('Password reset', 'success')
        return redirect(url_for('admin_users'))
    return render_template('admin_users_reset_password.html', user=user)

@app.route('/admin/users/<int:user_id>/reset_mfa', methods=['GET', 'POST'])
@login_required
def admin_users_reset_mfa(user_id):
    # Only God admins can reset MFA, and not for other gods
    current_level = session.get('admin_level', 0)
    user = get_user_by_id(user_id)
    if not user or current_level != 99 or user['admin_level'] == 99:
        flash('Insufficient permission', 'danger')
        return redirect(url_for('admin_users'))
    if request.method == 'POST':
        reset_user_mfa(user_id)
        flash('User MFA reset', 'success')
        return redirect(url_for('admin_users'))
    return render_template('admin_users_reset_mfa.html', user=user)

@app.route('/admin/change_password', methods=['GET', 'POST'])
@login_required
def admin_change_password():
    user = get_user(session.get('username'))
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        if new_password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('admin_change_password.html')
        if user['password'] != current_password:
            flash('Current password incorrect', 'danger')
            return render_template('admin_change_password.html')
        set_user_password(user['id'], new_password)
        flash('Password changed successfully', 'success')
        return redirect(url_for('admin'))
    return render_template('admin_change_password.html')

@app.route('/admin/login_audit')
@login_required
def admin_login_audit():
    if session.get('admin_level', 0) != 99:
        flash('Insufficient permission', 'danger')
        return redirect(url_for('admin_users'))
    # Dummy audit log; replace with your actual audit log retrieval
    audit = [
        {"username": "alice", "time": "2025-09-15 09:00:00", "ip": "1.2.3.4", "status": "Success"},
        {"username": "bob", "time": "2025-09-15 09:10:00", "ip": "5.6.7.8", "status": "Failure"},
    ]
    return render_template('admin_login_audit.html', audit=audit)

# --- Placeholder admin settings routes ---

@app.route('/admin/email_settings')
@login_required
def admin_email_settings():
    # Only admins (1+) and god (99) can see
    if session.get('admin_level', 0) < 1:
        flash("Insufficient permission", "danger")
        return redirect(url_for('admin'))
    return render_template('admin_email_settings.html')

@app.route('/admin/security_settings')
@login_required
def admin_security_settings():
    # Only god admin
    if session.get('admin_level', 0) != 99:
        flash("Insufficient permission", "danger")
        return redirect(url_for('admin'))
    return render_template('admin_security_settings.html')

@app.route("/admin")
@login_required
def admin():
    return render_template("admin.html")

# --- (Domain and Squid management routes unchanged) ---

# ... (Put your existing routes for manage_allowed, manage_blocked, etc. here)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
