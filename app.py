from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import os
import uuid

app = Flask(__name__, template_folder="templates", static_folder="sites")
CORS(app)

# In-memory "database"
users = {
    "admin": {"password": "admin123", "remaining_uses": 999999, "hosted_sites": [], "is_admin": True}
}
codes = {}  # { code: {"uses_left": int, "redeemed_by": []} }

# Ensure sites folder exists
if not os.path.exists("sites"):
    os.makedirs("sites")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/register_user", methods=["POST"])
def register_user():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    if username in users:
        return jsonify({"success": False, "message": "User already exists"})
    users[username] = {"password": password, "remaining_uses": 5, "hosted_sites": [], "is_admin": False}
    return jsonify({"success": True, "message": "User registered successfully"})

@app.route("/login_user", methods=["POST"])
def login_user():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    user = users.get(username)
    if user and user["password"] == password:
        return jsonify({"success": True, "is_admin": user.get("is_admin", False)})
    return jsonify({"success": False, "message": "Invalid username or password"})

@app.route("/host_site", methods=["POST"])
def host_site():
    data = request.json
    username = data.get("username")
    site_name = data.get("site_name")
    content = data.get("content")

    user = users.get(username)
    if not user:
        return jsonify({"success": False, "message": "User not found"})

    if user["remaining_uses"] <= 0:
        return jsonify({"success": False, "message": "No hosting uses left. Contact admin."})

    user_dir = os.path.join("sites", username)
    os.makedirs(user_dir, exist_ok=True)

    site_path = os.path.join(user_dir, f"{site_name}.html")
    with open(site_path, "w", encoding="utf-8") as f:
        f.write(content)

    if site_name not in user["hosted_sites"]:
        user["hosted_sites"].append(f"{site_name}.html")

    user["remaining_uses"] -= 1
    return jsonify({"success": True, "message": f"Site hosted successfully: /sites/{username}/{site_name}.html"})

@app.route("/sites/<username>/<path:filename>")
def serve_site(username, filename):
    return send_from_directory(os.path.join("sites", username), filename)

@app.route("/redeem_code", methods=["POST"])
def redeem_code():
    data = request.json
    username = data.get("username")
    code = data.get("code")

    if code not in codes or codes[code]["uses_left"] <= 0:
        return jsonify({"success": False, "message": "Invalid or expired code"})

    users[username]["remaining_uses"] +=  codes[code]["uses_left"]
    codes[code]["redeemed_by"].append(username)
    codes[code]["uses_left"] = 0  # One-time code
    return jsonify({"success": True, "message": "Code redeemed successfully"})

@app.route("/generate_code", methods=["POST"])
def generate_code():
    data = request.json
    uses = int(data.get("uses", 0))
    code = str(uuid.uuid4())[:8]
    codes[code] = {"uses_left": uses, "redeemed_by": []}
    return jsonify({"success": True, "code": code})

@app.route("/get_user/<username>")
def get_user(username):
    user = users.get(username)
    if not user:
        return jsonify({"success": False, "message": "User not found"})
    return jsonify({
        "success": True,
        "remaining_uses": user["remaining_uses"],
        "hosted_sites": user["hosted_sites"]
    })

@app.route("/admin_data")
def admin_data():
    user_list = []
    for uname, info in users.items():
        if not info.get("is_admin", False):
            user_list.append({
                "username": uname,
                "remaining_uses": info["remaining_uses"],
                "hosted_sites": info["hosted_sites"]
            })

    code_list = []
    for code, info in codes.items():
        code_list.append({
            "code": code,
            "uses_left": info["uses_left"],
            "redeemed_by": info["redeemed_by"]
        })

    return jsonify({"users": user_list, "codes": code_list})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
