from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import os
import sqlite3
import uuid

app = Flask(__name__, static_folder="sites", template_folder="templates")
CORS(app)

# === DATABASE SETUP ===
DB_NAME = "hosting.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Users
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT,
                    is_admin INTEGER DEFAULT 0,
                    uses_left INTEGER DEFAULT 5
                )''')

    # Redeem codes
    c.execute('''CREATE TABLE IF NOT EXISTS codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE,
                    max_uses INTEGER,
                    uses_left INTEGER,
                    created_by TEXT
                )''')

    # Who redeemed what
    c.execute('''CREATE TABLE IF NOT EXISTS redemptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    code TEXT
                )''')

    conn.commit()
    conn.close()

init_db()

# === AUTH ===
@app.route("/register", methods=["POST"])
def register():
    data = request.json
    username, password = data["username"], data["password"]

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, uses_left) VALUES (?, ?, ?)", 
                  (username, password, 5))
        conn.commit()
        return jsonify({"success": True, "message": "Account created! You have 5 free uses."})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Username already exists"})
    finally:
        conn.close()

@app.route("/login_user", methods=["POST"])
def login_user():
    data = request.json
    username, password = data["username"], data["password"]

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    user = c.fetchone()
    conn.close()

    if user:
        return jsonify({
            "success": True,
            "username": user[1],
            "is_admin": bool(user[3]),
            "uses_left": user[4]
        })
    return jsonify({"success": False, "message": "Invalid credentials"})

# === HOSTING ===
@app.route("/host_file", methods=["POST"])
def host_file():
    username = request.form.get("username")
    file = request.files["file"]

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT uses_left FROM users WHERE username=?", (username,))
    result = c.fetchone()
    if not result:
        conn.close()
        return jsonify({"success": False, "message": "User not found"})

    uses_left = result[0]
    if uses_left <= 0:
        conn.close()
        return jsonify({"success": False, "message": "No uses left. Contact admin."})

    # Save file
    site_id = str(uuid.uuid4())
    user_folder = os.path.join("sites", username)
    os.makedirs(user_folder, exist_ok=True)
    save_path = os.path.join(user_folder, f"{site_id}.html")
    file.save(save_path)

    # Reduce use
    c.execute("UPDATE users SET uses_left=uses_left-1 WHERE username=?", (username,))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Site hosted!", "link": f"/sites/{username}/{site_id}.html"})

@app.route("/host_html", methods=["POST"])
def host_html():
    data = request.json
    username = data["username"]
    html_content = data["html"]

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT uses_left FROM users WHERE username=?", (username,))
    result = c.fetchone()
    if not result:
        conn.close()
        return jsonify({"success": False, "message": "User not found"})

    uses_left = result[0]
    if uses_left <= 0:
        conn.close()
        return jsonify({"success": False, "message": "No uses left. Contact admin."})

    # Save HTML
    site_id = str(uuid.uuid4())
    user_folder = os.path.join("sites", username)
    os.makedirs(user_folder, exist_ok=True)
    save_path = os.path.join(user_folder, f"{site_id}.html")
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Reduce use
    c.execute("UPDATE users SET uses_left=uses_left-1 WHERE username=?", (username,))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Site hosted!", "link": f"/sites/{username}/{site_id}.html"})

@app.route("/sites/<username>/<filename>")
def serve_site(username, filename):
    return send_from_directory(os.path.join("sites", username), filename)

# === REDEEM CODE ===
@app.route("/redeem", methods=["POST"])
def redeem():
    data = request.json
    username, code = data["username"], data["code"]

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT uses_left FROM users WHERE username=?", (username,))
    user = c.fetchone()
    if not user:
        conn.close()
        return jsonify({"success": False, "message": "User not found"})

    c.execute("SELECT * FROM codes WHERE code=?", (code,))
    code_entry = c.fetchone()
    if not code_entry or code_entry[3] <= 0:
        conn.close()
        return jsonify({"success": False, "message": "Invalid or expired code"})

    # Redeem
    c.execute("UPDATE users SET uses_left=uses_left+? WHERE username=?", (code_entry[2], username))
    c.execute("UPDATE codes SET uses_left=uses_left-1 WHERE code=?", (code,))
    c.execute("INSERT INTO redemptions (username, code) VALUES (?, ?)", (username, code))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": f"Code redeemed! +{code_entry[2]} uses added."})

# === ADMIN ===
@app.route("/create_code", methods=["POST"])
def create_code():
    data = request.json
    username, max_uses = data["username"], data["max_uses"]

    # Check admin
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT is_admin FROM users WHERE username=?", (username,))
    admin = c.fetchone()
    if not admin or not admin[0]:
        conn.close()
        return jsonify({"success": False, "message": "Unauthorized"})

    code = str(uuid.uuid4())[:8].upper()
    c.execute("INSERT INTO codes (code, max_uses, uses_left, created_by) VALUES (?, ?, ?, ?)", 
              (code, max_uses, 1, username))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "code": code})

@app.route("/admin_dashboard", methods=["GET"])
def admin_dashboard():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT username, uses_left, is_admin FROM users")
    users = [{"username": u[0], "uses_left": u[1], "is_admin": bool(u[2])} for u in c.fetchall()]

    c.execute("SELECT code, max_uses, uses_left, created_by FROM codes")
    codes = [{"code": cd[0], "max_uses": cd[1], "uses_left": cd[2], "created_by": cd[3]} for cd in c.fetchall()]

    c.execute("SELECT username, code FROM redemptions")
    redemptions = [{"username": r[0], "code": r[1]} for r in c.fetchall()]

    conn.close()
    return jsonify({"users": users, "codes": codes, "redemptions": redemptions})

if __name__ == "__main__":
    os.makedirs("sites", exist_ok=True)
    app.run(host="0.0.0.0", port=5000)
