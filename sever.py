# app.py
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os
import zipfile
import shutil
import json
import secrets
import string

# --- Config ---
DB_FILE = "domgen.db"
SITES_DIR = "sites"
WHATSAPP_LINK = "https://chat.whatsapp.com/KA28UYJhcCiHneYVHxcCdk"  # provided

os.makedirs(SITES_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- DB helpers ---
def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # users: username unique, password, role, remaining_uses (-1 = infinite/admin)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            remaining_uses INTEGER,
            redeemed_codes TEXT DEFAULT '[]'
        )
    ''')

    # codes: code unique, slots (how many uploads granted each redeem), max_uses total allowed, remaining_uses, used_by (json list)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS redeem_codes (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE,
            slots INTEGER,
            max_uses INTEGER,
            remaining_uses INTEGER,
            used_by TEXT DEFAULT '[]'
        )
    ''')

    conn.commit()

    # Insert admin accounts if not exist
    for admin_name, admin_pass in [("Genetic", "obuegenesis"), ("DomGen", "Admin domgen")]:
        cur.execute("SELECT id FROM users WHERE username = ?", (admin_name,))
        if not cur.fetchone():
            cur.execute("INSERT INTO users (username,password,role,remaining_uses) VALUES (?,?,?,?)",
                        (admin_name, admin_pass, "admin", -1))
    conn.commit()
    conn.close()

init_db()

# --- Utilities ---
def flatten_extracted(folder):
    items = os.listdir(folder)
    if len(items) == 1 and os.path.isdir(os.path.join(folder, items[0])):
        inner = os.path.join(folder, items[0])
        for name in os.listdir(inner):
            shutil.move(os.path.join(inner, name), os.path.join(folder, name))
        shutil.rmtree(inner)

def make_code(length=8):
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# --- Routes ---

# Create account
@app.route("/create_account", methods=["POST"])
def create_account():
    data = request.get_json() or {}
    username = data.get("username") or data.get("name")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error":"username & password required"}), 400

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cur.fetchone():
        conn.close()
        return jsonify({"error":"Username already exists"}), 400

    # new normal user: role=user, remaining_uses=5
    cur.execute("INSERT INTO users (username,password,role,remaining_uses) VALUES (?,?,?,?)",
                (username, password, "user", 5))
    conn.commit()
    conn.close()
    return jsonify({"message":"Account created", "uploads_left": 5})

# Login
@app.route("/login_user", methods=["POST"])
def login_user():
    data = request.get_json() or {}
    username = data.get("username") or data.get("name")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error":"username & password required"}), 400

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT username,role,remaining_uses FROM users WHERE username = ? AND password = ?", (username, password))
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"error":"Invalid username or password"}), 400

    uploads_left = row["remaining_uses"]
    role = row["role"]
    return jsonify({"username": username, "role": role, "uploads_left": uploads_left})

# Upload site (multipart/form-data) - field name: file
@app.route("/upload/<username>/<site_name>", methods=["POST"])
def upload_site(username, site_name):
    # check user exists and limit
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT role,remaining_uses FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({"error":"Unknown user"}), 400

    role = row["role"]
    remaining = row["remaining_uses"]

    if role != "admin" and (remaining is None or int(remaining) <= 0):
        conn.close()
        return jsonify({"error":"Your free uses have finished. Contact admin to get redeem code.","contact": WHATSAPP_LINK}), 403

    if "file" not in request.files:
        conn.close()
        return jsonify({"error":"No file uploaded (field name must be 'file')"}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".zip"):
        conn.close()
        return jsonify({"error":"Only .zip files allowed"}), 400

    # save zip into sites/<username>/<site_name> and extract
    user_site_dir = os.path.join(SITES_DIR, username, site_name)
    if os.path.exists(user_site_dir):
        shutil.rmtree(user_site_dir)
    os.makedirs(user_site_dir, exist_ok=True)

    zip_path = os.path.join(user_site_dir, "site.zip")
    file.save(zip_path)

    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(user_site_dir)
        flatten_extracted(user_site_dir)
        os.remove(zip_path)
    except Exception as e:
        # cleanup
        shutil.rmtree(user_site_dir, ignore_errors=True)
        conn.close()
        return jsonify({"error":f"Extraction failed: {e}"}), 500

    # decrease user remaining_uses if not admin
    if role != "admin":
        new_remaining = int(remaining) - 1
        cur.execute("UPDATE users SET remaining_uses = ? WHERE username = ?", (new_remaining, username))
        conn.commit()
    else:
        new_remaining = -1

    conn.close()
    # return hosted index link if exists, else list files
    index_url = f"/site/{username}/{site_name}/index.html"
    files = [f for f in os.listdir(user_site_dir) if os.path.isfile(os.path.join(user_site_dir, f))]
    return jsonify({"message":"Upload successful", "files": files, "index": index_url, "uploads_left": new_remaining})

# List sites for a user
@app.route("/sites/<username>", methods=["GET"])
def sites_list(username):
    user_dir = os.path.join(SITES_DIR, username)
    if not os.path.exists(user_dir):
        return jsonify([])
    result = []
    for site in os.listdir(user_dir):
        site_dir = os.path.join(user_dir, site)
        if os.path.isdir(site_dir):
            files = [f for f in os.listdir(site_dir) if os.path.isfile(os.path.join(site_dir, f))]
            result.append({"siteName": site, "files": files})
    return jsonify(result)
# List all users (for admin dashboard)
@app.route("/list_users", methods=["GET"])
def list_users():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT username, remaining_uses FROM users")
    users = [{"username": r["username"], "uploads_left": r["remaining_uses"]} for r in cur.fetchall()]
    conn.close()
    return jsonify(users)

# Serve file
@app.route("/site/<username>/<site_name>/<path:filename>")
def serve_file(username, site_name, filename):
    directory = os.path.join(SITES_DIR, username, site_name)
    return send_from_directory(directory, filename)

# Delete site
@app.route("/delete/<username>/<site_name>", methods=["DELETE"])
def delete_site(username, site_name):
    dirpath = os.path.join(SITES_DIR, username, site_name)
    if os.path.exists(dirpath):
        shutil.rmtree(dirpath)
        return jsonify({"message":"Site deleted"})
    return jsonify({"error":"Site not found"}), 404

# Generate code (admin)
@app.route("/generate_code", methods=["POST"])
def generate_code():
    data = request.get_json() or {}
    admin = data.get("admin") or data.get("account_name")
    # verify admin
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE username = ?", (admin,))
    row = cur.fetchone()
    if not row or row["role"] != "admin":
        conn.close()
        return jsonify({"error":"Unauthorized (admin only)"}), 403

    slots = int(data.get("slots", 5))
    max_uses = int(data.get("max_uses", 1))
    code = data.get("code") or make_code(8)

    cur.execute("INSERT INTO redeem_codes (code, slots, max_uses, remaining_uses, used_by) VALUES (?,?,?,?,?)",
                (code, slots, max_uses, max_uses, json.dumps([])))
    conn.commit()
    conn.close()
    return jsonify({"message":"Code created", "code": code, "slots": slots, "max_uses": max_uses})

# List active codes (admin)
@app.route("/active_codes", methods=["POST"])
def active_codes():
    data = request.get_json() or {}
    admin = data.get("admin") or data.get("account_name")
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE username = ?", (admin,))
    row = cur.fetchone()
    if not row or row["role"] != "admin":
        conn.close()
        return jsonify({"error":"Unauthorized (admin only)"}), 403

    cur.execute("SELECT code, slots, max_uses, remaining_uses, used_by FROM redeem_codes")
    codes = []
    for r in cur.fetchall():
        codes.append({
            "code": r["code"],
            "slots": r["slots"],
            "max_uses": r["max_uses"],
            "remaining_uses": r["remaining_uses"],
            "used_by": json.loads(r["used_by"] or "[]")
        })
    conn.close()
    return jsonify({"codes": codes})

# Delete code (admin)
@app.route("/delete_code", methods=["POST"])
def delete_code():
    data = request.get_json() or {}
    admin = data.get("admin")
    code = data.get("code")
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE username = ?", (admin,))
    row = cur.fetchone()
    if not row or row["role"] != "admin":
        conn.close()
        return jsonify({"error":"Unauthorized"}), 403
    cur.execute("DELETE FROM redeem_codes WHERE code = ?", (code,))
    conn.commit()
    conn.close()
    return jsonify({"message":"Code deleted"})

# Redeem code
@app.route("/redeem_code", methods=["POST"])
def redeem_code():
    data = request.get_json() or {}
    username = data.get("username") or data.get("account_name")
    code = data.get("code")
    if not username or not code:
        return jsonify({"error":"username and code required"}), 400

    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT id, remaining_uses, slots, used_by FROM redeem_codes WHERE code = ?", (code,))
    code_row = cur.fetchone()
    if not code_row:
        conn.close()
        return jsonify({"error":"Invalid code"}), 400
    if code_row["remaining_uses"] <= 0:
        conn.close()
        return jsonify({"error":"Code expired"}), 400

    # update user
    cur.execute("SELECT remaining_uses, redeemed_codes FROM users WHERE username = ?", (username,))
    user_row = cur.fetchone()
    if not user_row:
        conn.close()
        return jsonify({"error":"Unknown user"}), 400

    # If user had infinite (admin) allow but no need: we'll still add slots
    current_uses = user_row["remaining_uses"]
    new_uses = (0 if current_uses in (None,) else int(current_uses)) + int(code_row["slots"])
    cur.execute("UPDATE users SET remaining_uses = ?, redeemed_codes = ? WHERE username = ?",
                (new_uses, json.dumps(json.loads(user_row["redeemed_codes"] or "[]") + [code]), username))

    # update code: decrement remaining_uses and append used_by
    used_by = json.loads(code_row["used_by"] or "[]")
    used_by.append(username)
    cur.execute("UPDATE redeem_codes SET remaining_uses = ?, used_by = ? WHERE code = ?",
                (code_row["remaining_uses"] - 1, json.dumps(used_by), code))
    conn.commit()

    # return updated user uses
    cur.execute("SELECT remaining_uses FROM users WHERE username = ?", (username,))
    updated = cur.fetchone()["remaining_uses"]
    conn.close()
    return jsonify({"message": f"Redeemed +{code_row['slots']} uploads", "uploads_left": updated})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
