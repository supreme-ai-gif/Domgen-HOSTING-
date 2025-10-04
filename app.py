import os
import sqlite3
import secrets
from flask import Flask, request, jsonify, session, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app, supports_credentials=True)

# === CONFIG ===
app.secret_key = "super-secret-key"  # change in production
UPLOAD_FOLDER = "sites"
DB_FILE = "database.db"
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# === DATABASE ===
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        # Users
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            uses_left INTEGER
        )
        """)
        # Redeem Codes
        c.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            code TEXT PRIMARY KEY,
            slots INTEGER,
            remaining INTEGER
        )
        """)
        # Code usage
        c.execute("""
        CREATE TABLE IF NOT EXISTS code_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            code TEXT
        )
        """)
        # Sites
        c.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            name TEXT,
            filename TEXT
        )
        """)
        conn.commit()

init_db()

# === HELPERS ===
def get_user(username):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT username, password, uses_left FROM users WHERE username=?", (username,))
        return c.fetchone()

def update_uses(username, uses):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET uses_left=? WHERE username=?", (uses, username))
        conn.commit()

# === ROUTES ===
@app.route("/")
def home():
    return render_template("index.html")

# Create account
@app.route("/create_account", methods=["POST"])
def create_account():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    if get_user(username):
        return jsonify({"success": False, "message": "User already exists"})
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO users (username, password, uses_left) VALUES (?,?,?)",
                  (username, password, 5))
        conn.commit()
    return jsonify({"success": True, "message": "Account created! You have 5 free uses."})

# Login
@app.route("/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    user = get_user(username)
    if user and user[1] == password:
        session["user"] = username
        if username == ADMIN_USER:
            return jsonify({"success": True, "admin": True})
        return jsonify({"success": True, "uses_left": user[2]})
    return jsonify({"success": False, "message": "Invalid credentials"})

@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    return jsonify({"success": True})

# Upload site
@app.route("/upload", methods=["POST"])
def upload():
    if "user" not in session:
        return jsonify({"success": False, "message": "Not logged in"})
    username = session["user"]
    if username != ADMIN_USER:
        user = get_user(username)
        if not user or user[2] <= 0:
            return jsonify({"success": False, "message": "No uses left. Contact admin for redeem code."})
        update_uses(username, user[2] - 1)
    if "file" not in request.files:
        return jsonify({"success": False, "message": "No file uploaded"})
    file = request.files["file"]
    sitename = request.form.get("sitename", "mysite")
    filename = secure_filename(file.filename)
    user_folder = os.path.join(UPLOAD_FOLDER, username, sitename)
    os.makedirs(user_folder, exist_ok=True)
    file.save(os.path.join(user_folder, filename))
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO sites (username, name, filename) VALUES (?,?,?)",
                  (username, sitename, filename))
        conn.commit()
    return jsonify({"success": True, "message": "Site uploaded!", 
                    "link": f"/sites/{username}/{sitename}/{filename}"})

# List sites
@app.route("/list_sites", methods=["GET"])
def list_sites():
    if "user" not in session:
        return jsonify([])
    username = session["user"]
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT name, filename FROM sites WHERE username=?", (username,))
        sites = [{"name": n, "filename": f, "link": f"/sites/{username}/{n}/{f}"} for n, f in c.fetchall()]
    return jsonify(sites)

# Serve sites
@app.route("/sites/<username>/<sitename>/<filename>")
def serve_site(username, sitename, filename):
    return send_from_directory(os.path.join(UPLOAD_FOLDER, username, sitename), filename)

# Redeem codes
@app.route("/redeem", methods=["POST"])
def redeem():
    if "user" not in session:
        return jsonify({"success": False, "message": "Not logged in"})
    data = request.json
    code = data.get("code")
    username = session["user"]
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT code, slots, remaining FROM codes WHERE code=?", (code,))
        row = c.fetchone()
        if not row or row[2] <= 0:
            return jsonify({"success": False, "message": "Invalid or expired code"})
        c.execute("SELECT * FROM code_usage WHERE username=? AND code=?", (username, code))
        if c.fetchone():
            return jsonify({"success": False, "message": "You already used this code"})
        c.execute("UPDATE codes SET remaining=remaining-1 WHERE code=?", (code,))
        c.execute("INSERT INTO code_usage (username, code) VALUES (?,?)", (username, code))
        c.execute("UPDATE users SET uses_left=uses_left+? WHERE username=?", (row[1], username))
        conn.commit()
    return jsonify({"success": True, "message": f"Code redeemed! +{row[1]} uses added."})

# Admin: generate code
@app.route("/generate_code", methods=["POST"])
def generate_code():
    if "user" not in session or session["user"] != ADMIN_USER:
        return jsonify({"success": False, "message": "Admin only"})
    data = request.json
    slots = int(data.get("slots", 5))
    uses = int(data.get("uses", 1))
    code = secrets.token_hex(4).upper()
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO codes (code, slots, remaining) VALUES (?,?,?)", (code, slots, uses))
        conn.commit()
    return jsonify({"success": True, "code": code, "slots": slots, "uses": uses})

# Admin: list codes
@app.route("/list_codes")
def list_codes():
    if "user" not in session or session["user"] != ADMIN_USER:
        return jsonify([])
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT code, slots, remaining FROM codes")
        codes = []
        for code, slots, remaining in c.fetchall():
            c.execute("SELECT username FROM code_usage WHERE code=?", (code,))
            used_by = [u[0] for u in c.fetchall()]
            codes.append({"code": code, "slots": slots, "remaining": remaining, "used_by": used_by})
    return jsonify(codes)

# Admin: list users
@app.route("/list_users")
def list_users():
    if "user" not in session or session["user"] != ADMIN_USER:
        return jsonify([])
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT username, uses_left FROM users")
        users = [{"username": u, "uses_left": l} for u, l in c.fetchall()]
    return jsonify(users)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
