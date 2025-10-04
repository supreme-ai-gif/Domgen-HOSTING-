import os, json, uuid, zipfile
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# --- Files & Directories ---
DATA_FILE = "data.json"
SITES_DIR = "sites"
os.makedirs(SITES_DIR, exist_ok=True)

# --- Load & Save Data ---
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump({"users": {}, "codes": {}}, f)

def load_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# --- Create Account ---
@app.route("/api/create", methods=["POST"])
def create():
    data = load_data()
    body = request.get_json()
    username, password = body.get("username"), body.get("password")
    if username in data["users"]:
        return jsonify({"message": "User already exists"}), 400
    data["users"][username] = {"password": password, "uses_left": 5, "sites": []}
    save_data(data)
    return jsonify({"message": "Account created. 5 free uses granted."})

# --- Login ---
@app.route("/api/login", methods=["POST"])
def login():
    data = load_data()
    body = request.get_json()
    username, password = body.get("username"), body.get("password")
    if username not in data["users"] or data["users"][username]["password"] != password:
        return jsonify({"message": "Invalid credentials"}), 400
    user = data["users"][username]
    return jsonify({
        "message": "Login successful",
        "username": username,
        "uses_left": user["uses_left"],
        "role": "admin" if username == "admin" else "user"
    })

# --- Upload Site ---
@app.route("/api/upload", methods=["POST"])
def upload():
    data = load_data()
    username = request.form.get("username")
    site_name = request.form.get("site_name")
    file = request.files.get("file")

    if not username or not site_name or not file:
        return jsonify({"message": "Missing data"}), 400
    if username not in data["users"]:
        return jsonify({"message": "User not found"}), 404

    user = data["users"][username]
    if username != "admin" and user["uses_left"] <= 0:
        return jsonify({"message": "No uses left. Redeem a code."}), 403

    site_path = os.path.join(SITES_DIR, site_name)
    os.makedirs(site_path, exist_ok=True)

    # Extract ZIP into folder
    zip_path = os.path.join(site_path, "site.zip")
    file.save(zip_path)
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(site_path)
    os.remove(zip_path)

    # Deduct use
    if username != "admin":
        user["uses_left"] -= 1
    if site_name not in user["sites"]:
        user["sites"].append(site_name)

    save_data(data)
    return jsonify({"message": f"Site '{site_name}' hosted successfully", "link": f"/sites/{site_name}/"})

# --- List Sites for a User ---
@app.route("/api/sites", methods=["GET"])
def list_sites():
    data = load_data()
    username = request.args.get("username")
    if username not in data["users"]:
        return jsonify([])

    user = data["users"][username]
    sites_info = []
    for s in user["sites"]:
        path = os.path.join(SITES_DIR, s)
        if os.path.exists(path):
            files = len(os.listdir(path))
            sites_info.append({
                "name": s,
                "files": files,
                "link": f"/sites/{s}/"
            })
    return jsonify(sites_info)

# --- Redeem Code ---
@app.route("/api/redeem", methods=["POST"])
def redeem():
    data = load_data()
    body = request.get_json()
    username, code = body.get("username"), body.get("code")

    if username not in data["users"]:
        return jsonify({"message": "User not found"}), 404
    if code not in data["codes"]:
        return jsonify({"message": "Invalid code"}), 400

    c = data["codes"][code]
    if c["uses"] <= 0:
        return jsonify({"message": "Code already fully used"}), 400

    # Add slots
    data["users"][username]["uses_left"] += c["slots"]
    c["uses"] -= 1
    c.setdefault("redeemed_by", []).append(username)
    save_data(data)
    return jsonify({"message": f"Code redeemed. {c['slots']} slots added."})

# --- Admin: Generate Redeem Code ---
@app.route("/api/admin/generate", methods=["POST"])
def admin_generate():
    body = request.get_json()
    slots, uses = int(body.get("slots", 5)), int(body.get("uses", 1))

    data = load_data()
    code = str(uuid.uuid4())[:8]
    data["codes"][code] = {"slots": slots, "uses": uses, "redeemed_by": []}
    save_data(data)
    return jsonify({"code": code, "slots": slots, "uses": uses})

# --- Admin: List Codes ---
@app.route("/api/admin/codes", methods=["GET"])
def admin_codes():
    data = load_data()
    return jsonify(data["codes"])

# --- Admin: List Users ---
@app.route("/api/admin/users", methods=["GET"])
def admin_users():
    data = load_data()
    return jsonify({u: {"uses_left": v["uses_left"]} for u, v in data["users"].items()})

# --- Serve Static Files ---
@app.route("/sites/<site>/<path:filename>")
def serve_site(site, filename):
    return send_from_directory(os.path.join(SITES_DIR, site), filename)

@app.route("/sites/<site>/")
def serve_index(site):
    return send_from_directory(os.path.join(SITES_DIR, site), "index.html")

# --- Main ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
