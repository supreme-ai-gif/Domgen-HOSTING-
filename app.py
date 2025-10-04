from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import zipfile
import shutil
import uuid

app = Flask(__name__)

# Ensure 'sites' folder exists
if not os.path.exists("sites"):
    os.makedirs("sites")

# ==== FRONTEND ROUTE ====
@app.route("/")
def home():
    return render_template("index.html")

# ==== AUTH / USERS SIMULATION ====
users = {"admin": {"password": "admin123", "uses_left": float("inf"), "is_admin": True}}
redeem_codes = {}

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    if username in users:
        return jsonify({"error": "User already exists"}), 400

    users[username] = {"password": password, "uses_left": 5, "is_admin": False}
    return jsonify({"message": "Account created successfully"})

@app.route("/login_user", methods=["POST"])
def login_user():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    user = users.get(username)
    if not user or user["password"] != password:
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "message": "Login successful",
        "username": username,
        "uses_left": user["uses_left"],
        "is_admin": user["is_admin"]
    })

# ==== HOSTING ====
@app.route("/host_file", methods=["POST"])
def host_file():
    username = request.form.get("username")
    site_name = request.form.get("site_name")
    file = request.files["file"]

    user = users.get(username)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if not user["is_admin"] and user["uses_left"] <= 0:
        return jsonify({"error": "No uses left. Please redeem a code"}), 403

    site_folder = os.path.join("sites", username, site_name)
    if os.path.exists(site_folder):
        shutil.rmtree(site_folder)
    os.makedirs(site_folder)

    zip_path = os.path.join(site_folder, "site.zip")
    file.save(zip_path)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(site_folder)

    os.remove(zip_path)

    if not user["is_admin"]:
        user["uses_left"] -= 1

    site_url = f"/sites/{username}/{site_name}/index.html"
    return jsonify({"message": "Site hosted successfully", "url": site_url, "uses_left": user["uses_left"]})

@app.route("/sites/<username>/<site_name>/<path:filename>")
def serve_site(username, site_name, filename):
    return send_from_directory(os.path.join("sites", username, site_name), filename)

# ==== REDEEM CODE ====
@app.route("/generate_code", methods=["POST"])
def generate_code():
    data = request.json
    slots = data.get("slots", 5)
    code = str(uuid.uuid4())[:8]
    redeem_codes[code] = {"slots": slots, "used_by": []}
    return jsonify({"code": code, "slots": slots})

@app.route("/redeem", methods=["POST"])
def redeem():
    data = request.json
    username = data.get("username")
    code = data.get("code")

    user = users.get(username)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if code not in redeem_codes:
        return jsonify({"error": "Invalid code"}), 400

    if username in redeem_codes[code]["used_by"]:
        return jsonify({"error": "You already used this code"}), 400

    user["uses_left"] += redeem_codes[code]["slots"]
    redeem_codes[code]["used_by"].append(username)

    return jsonify({"message": "Code redeemed successfully", "uses_left": user["uses_left"]})

# ==== ADMIN DASHBOARD DATA ====
@app.route("/list_codes", methods=["GET"])
def list_codes():
    return jsonify(redeem_codes)

@app.route("/list_users", methods=["GET"])
def list_users():
    return jsonify(users)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
