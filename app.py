from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import os
import zipfile
import uuid

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# Simulated database
users = {
    "Genetic": {"password": "obuegenesis", "role": "admin", "uses_left": float("inf")},
    "DomGen": {"password": "Admin domgen", "role": "admin", "uses_left": float("inf")},
}
codes = {}  # code -> {"slots": x, "remaining": x, "used_by": []}

# Default free slots for new users
DEFAULT_USES = 5

# Ensure site storage exists
os.makedirs("sites", exist_ok=True)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/create_account", methods=["POST"])
def create_account():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    if username in users:
        return jsonify({"status": "error", "message": "Username already exists"}), 400
    users[username] = {"password": password, "role": "user", "uses_left": DEFAULT_USES}
    return jsonify({"status": "ok", "message": "Account created successfully"})

@app.route("/login_user", methods=["POST"])
def login_user():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    user = users.get(username)
    if not user or user["password"] != password:
        return jsonify({"status": "error", "message": "Invalid credentials"}), 401
    return jsonify({
        "status": "ok",
        "role": user["role"],
        "uses_left": user["uses_left"]
    })

@app.route("/upload", methods=["POST"])
def upload():
    username = request.form.get("username")
    if username not in users:
        return jsonify({"status": "error", "message": "Invalid user"}), 401

    user = users[username]
    if user["role"] != "admin" and user["uses_left"] <= 0:
        return jsonify({
            "status": "error",
            "message": "❌ No hosting uses left. Contact admin for redeem code.",
            "contact": "https://chat.whatsapp.com/KA28UYJhcCiHneYVHxcCdk"
        }), 403

    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400

    site_name = request.form.get("site_name")
    file = request.files["file"]
    site_path = os.path.join("sites", username, site_name)
    os.makedirs(site_path, exist_ok=True)

    zip_path = os.path.join(site_path, "site.zip")
    file.save(zip_path)

    # Extract site
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(site_path)
    os.remove(zip_path)

    if user["role"] != "admin":
        user["uses_left"] -= 1

    return jsonify({
        "status": "ok",
        "message": f"✅ Site {site_name} hosted successfully!",
        "uses_left": user["uses_left"],
        "url": f"/sites/{username}/{site_name}/index.html"
    })

@app.route("/redeem", methods=["POST"])
def redeem():
    data = request.json
    username = data.get("username")
    code = data.get("code")

    if code not in codes:
        return jsonify({"status": "error", "message": "Invalid code"}), 400
    if codes[code]["remaining"] <= 0:
        return jsonify({"status": "error", "message": "Code already used"}), 400

    users[username]["uses_left"] += codes[code]["slots"]
    codes[code]["remaining"] -= 1
    codes[code]["used_by"].append(username)

    return jsonify({
        "status": "ok",
        "message": f"✅ Redeem successful. Added {codes[code]['slots']} uses.",
        "uses_left": users[username]["uses_left"]
    })

@app.route("/generate_code", methods=["POST"])
def generate_code():
    data = request.json
    slots = int(data.get("slots", 5))
    uses = int(data.get("uses", 1))
    code = str(uuid.uuid4())[:8]
    codes[code] = {"slots": slots, "remaining": uses, "used_by": []}
    return jsonify({"status": "ok", "code": code, "slots": slots, "uses": uses})

@app.route("/list_codes", methods=["GET"])
def list_codes():
    return jsonify(codes)

@app.route("/list_users", methods=["GET"])
def list_users():
    return jsonify({u: {"uses_left": d["uses_left"], "role": d["role"]} for u, d in users.items()})

@app.route("/sites/<username>/<sitename>/<path:filename>")
def serve_site(username, sitename, filename):
    return send_from_directory(os.path.join("sites", username, sitename), filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
