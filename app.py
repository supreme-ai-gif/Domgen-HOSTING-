import os, json, secrets, zipfile, shutil
from flask import Flask, request, jsonify, render_template, send_from_directory

app = Flask(__name__)

# ---------------- CONFIG ----------------
DATA_FILE = "data.json"
UPLOAD_DIR = "hosted_sites"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------- DATA ----------------
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"users": {}, "codes": {}}, f)

def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ---------------- ROUTES ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["POST"])
def register():
    data = load_data()
    info = request.get_json()
    username, password = info["username"], info["password"]
    if username in data["users"]:
        return jsonify({"error": "Username already exists"}), 400
    data["users"][username] = {"password": password, "uses_left": 5, "is_admin": False}
    save_data(data)
    return jsonify({"message": f"User {username} created"})

@app.route("/login_user", methods=["POST"])
def login_user():
    data = load_data()
    info = request.get_json()
    username, password = info["username"], info["password"]
    if username not in data["users"] or data["users"][username]["password"] != password:
        return jsonify({"error": "Invalid username or password"}), 401
    return jsonify({
        "username": username,
        "uses_left": data["users"][username]["uses_left"],
        "is_admin": data["users"][username]["is_admin"]
    })

@app.route("/host_file", methods=["POST"])
def host_file():
    data = load_data()
    username = request.form.get("username")
    site_name = request.form.get("site_name")
    if username not in data["users"]:
        return jsonify({"error": "User not found"}), 404
    user = data["users"][username]

    if not user["is_admin"] and user["uses_left"] <= 0:
        return jsonify({"error": "No uses left. Please redeem a code."}), 403

    file = request.files["file"]
    site_path = os.path.join(UPLOAD_DIR, site_name)
    if os.path.exists(site_path):
        shutil.rmtree(site_path)
    os.makedirs(site_path, exist_ok=True)

    zip_path = os.path.join(site_path, "site.zip")
    file.save(zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(site_path)
    os.remove(zip_path)

    if not user["is_admin"]:
        user["uses_left"] -= 1
    save_data(data)

    return jsonify({
        "message": "Site hosted successfully",
        "url": f"/sites/{site_name}/index.html",
        "uses_left": user["uses_left"]
    })

@app.route("/sites/<site>/<path:filename>")
def serve_site(site, filename):
    return send_from_directory(os.path.join(UPLOAD_DIR, site), filename)

@app.route("/redeem", methods=["POST"])
def redeem():
    data = load_data()
    info = request.get_json()
    username, code = info["username"], info["code"]
    if code not in data["codes"]:
        return jsonify({"error": "Invalid code"}), 400
    if data["codes"][code]["slots"] <= 0:
        return jsonify({"error": "Code already used"}), 400
    data["users"][username]["uses_left"] += data["codes"][code]["slots"]
    data["codes"][code]["used_by"].append(username)
    data["codes"][code]["slots"] = 0
    save_data(data)
    return jsonify({"message": "Code redeemed successfully", "uses_left": data["users"][username]["uses_left"]})

@app.route("/generate_code", methods=["POST"])
def generate_code():
    data = load_data()
    info = request.get_json()
    slots = int(info["slots"])
    code = secrets.token_hex(4).upper()
    data["codes"][code] = {"slots": slots, "used_by": []}
    save_data(data)
    return jsonify({"code": code, "slots": slots})

@app.route("/list_codes")
def list_codes():
    data = load_data()
    return jsonify(data["codes"])

@app.route("/list_users")
def list_users():
    data = load_data()
    return jsonify(data["users"])

# ---------------- INIT ----------------
def init_admins():
    data = load_data()
    admins = ["Genetic", "DomGen"]
    for adm in admins:
        if adm not in data["users"]:
            data["users"][adm] = {"password": "admin123", "uses_left": float("inf"), "is_admin": True}
    save_data(data)

if __name__ == "__main__":
    init_admins()
    app.run(host="0.0.0.0", port=5000)
