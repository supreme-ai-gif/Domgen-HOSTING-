import os
import uuid
import shutil
import zipfile
from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# === In-memory database (replace with Firestore if needed) ===
users = {}  # {username: {"password": str, "uses": int, "sites": []}}
redeem_codes = {}  # {code: {"slots": int, "uses_left": int, "used_by": []}}

# Admin accounts
admins = {
    "Genetic": "obuegenesis",
    "DomGen": "Admin domgen"
}

SITES_DIR = "sites"
os.makedirs(SITES_DIR, exist_ok=True)

# ========================= ROUTES ========================= #

@app.route("/")
def index():
    return render_template("index.html")

# -------- User Auth -------- #
@app.route("/create_account", methods=["POST"])
def create_account():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    if username in users or username in admins:
        return jsonify({"success": False, "message": "Username already exists"})
    users[username] = {"password": password, "uses": 5, "sites": []}
    return jsonify({"success": True, "message": "Account created successfully"})

@app.route("/login_user", methods=["POST"])
def login_user():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    if username in admins and admins[username] == password:
        return jsonify({"success": True, "role": "admin"})
    if username in users and users[username]["password"] == password:
        return jsonify({"success": True, "role": "user", "uses": users[username]["uses"]})
    return jsonify({"success": False, "message": "Invalid credentials"})

# -------- Hosting -------- #
@app.route("/upload_site", methods=["POST"])
def upload_site():
    username = request.form.get("username")
    if username not in users and username not in admins:
        return jsonify({"success": False, "message": "Unauthorized"})

    # Admins can host infinitely
    if username not in admins:
        if users[username]["uses"] <= 0:
            return jsonify({"success": False, "message": "No uses left. Contact admin."})
        users[username]["uses"] -= 1

    site_name = request.form.get("siteName")
    file = request.files.get("siteFile")

    if not site_name or not file:
        return jsonify({"success": False, "message": "Missing site name or file"})

    user_dir = os.path.join(SITES_DIR, username, site_name)
    os.makedirs(user_dir, exist_ok=True)

    zip_path = os.path.join(user_dir, "site.zip")
    file.save(zip_path)

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(user_dir)
        os.remove(zip_path)
    except Exception as e:
        return jsonify({"success": False, "message": f"Extraction failed: {str(e)}"})

    if username not in admins:
        users[username]["sites"].append(site_name)

    return jsonify({"success": True, "message": f"Site {site_name} hosted!", "uses": users.get(username, {}).get("uses", "∞")})

@app.route("/sites/<username>/<site>/<path:filename>")
def serve_site(username, site, filename):
    site_dir = os.path.join(SITES_DIR, username, site)
    return send_from_directory(site_dir, filename)

# -------- Redeem -------- #
@app.route("/redeem", methods=["POST"])
def redeem():
    data = request.json
    username = data.get("username")
    code = data.get("code")

    if username not in users:
        return jsonify({"success": False, "message": "User not found"})

    if code not in redeem_codes:
        return jsonify({"success": False, "message": "Invalid code"})

    if redeem_codes[code]["uses_left"] <= 0:
        return jsonify({"success": False, "message": "Code expired"})

    slots = redeem_codes[code]["slots"]
    users[username]["uses"] += slots
    redeem_codes[code]["uses_left"] -= 1
    redeem_codes[code]["used_by"].append(username)

    return jsonify({"success": True, "message": f"Redeemed {slots} uses!", "uses": users[username]["uses"]})

# -------- Admin -------- #
@app.route("/generate_code", methods=["POST"])
def generate_code():
    data = request.json
    slots = int(data.get("slots", 5))
    uses = int(data.get("uses", 1))
    code = uuid.uuid4().hex[:8].upper()
    redeem_codes[code] = {"slots": slots, "uses_left": uses, "used_by": []}
    return jsonify({"success": True, "code": code})

@app.route("/list_codes", methods=["GET"])
def list_codes():
    return jsonify(redeem_codes)

@app.route("/list_users", methods=["GET"])
def list_users():
    return jsonify(users)

# ========================= MAIN ========================= #
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
