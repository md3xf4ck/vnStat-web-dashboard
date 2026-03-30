import copy
import json
import threading
import time
from datetime import datetime, date
from functools import wraps
from typing import Optional

import paramiko
from flask import Flask, jsonify, render_template, request, session, redirect, url_for

from config import CONFIG

app = Flask(__name__)
app.secret_key = CONFIG["secret_key"]

# In-memory cache: { server_name: { "data": {...}, "updated_at": datetime, "error": str|None } }
cache = {}
cache_lock = threading.Lock()


# ──────────────────────────────────────────────
# SSH helpers
# ──────────────────────────────────────────────

def fetch_vnstat(server: dict) -> dict:
    """SSH into a server and return parsed vnstat --json output."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        connect_kwargs = {
            "hostname": server["host"],
            "port": server.get("port", 22),
            "username": server["user"],
            "timeout": 10,
        }
        if "key_path" in server:
            connect_kwargs["key_filename"] = server["key_path"]
        elif "password" in server:
            connect_kwargs["password"] = server["password"]

        client.connect(**connect_kwargs)
        iface = server.get("interface", "")
        cmd = f"vnstat --json" + (f" -i {iface}" if iface else "")
        _, stdout, stderr = client.exec_command(cmd)
        raw = stdout.read().decode()
        err = stderr.read().decode()
        if not raw.strip():
            raise RuntimeError(f"vnstat returned nothing. stderr: {err}")
        return json.loads(raw)
    finally:
        client.close()


def refresh_server(name: str, server: dict):
    try:
        data = fetch_vnstat(server)
        with cache_lock:
            cache[name] = {"data": data, "updated_at": datetime.now(), "error": None}
    except Exception as e:
        with cache_lock:
            prev = cache.get(name, {})
            cache[name] = {
                "data": prev.get("data"),
                "updated_at": datetime.now(),
                "error": str(e),
            }


def background_refresh():
    while True:
        for name, server in CONFIG["servers"].items():
            threading.Thread(target=refresh_server, args=(name, server), daemon=True).start()
        time.sleep(CONFIG.get("refresh_interval", 60))


# ──────────────────────────────────────────────
# Auth helpers
# ──────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ──────────────────────────────────────────────
# vnstat data processing
# ──────────────────────────────────────────────

def process_day_data(vnstat_json: dict, day_str: Optional[str], interface: Optional[str]):
    """
    Extract hourly traffic + speed for a given day (YYYY-MM-DD).
    Returns dict with upload/download arrays per hour (0-23).
    """
    interfaces = vnstat_json.get("interfaces", [])
    if not interfaces:
        return None

    # pick interface
    if interface:
        iface_data = next((i for i in interfaces if i["name"] == interface), interfaces[0])
    else:
        iface_data = interfaces[0]

    hours_raw = iface_data.get("traffic", {}).get("hour", [])

    # parse target date
    if day_str:
        try:
            target = datetime.strptime(day_str, "%Y-%m-%d").date()
        except ValueError:
            target = date.today()
    else:
        target = date.today()

    # filter hours for that day
    day_hours = [
        h for h in hours_raw
        if h.get("date", {}).get("year") == target.year
        and h.get("date", {}).get("month") == target.month
        and h.get("date", {}).get("day") == target.day
    ]

    upload_bytes = [0] * 24
    download_bytes = [0] * 24
    upload_speed = [0] * 24
    download_speed = [0] * 24

    for h in day_hours:
        hour = h.get("time", {}).get("hour", 0)
        if 0 <= hour <= 23:
            tx = h.get("tx", 0)
            rx = h.get("rx", 0)
            upload_bytes[hour] = tx
            download_bytes[hour] = rx
            # speed: bytes / 3600 → bytes/s
            upload_speed[hour] = round(tx / 3600) if tx else 0
            download_speed[hour] = round(rx / 3600) if rx else 0

    # available days list (for date picker)
    available_days = sorted({
        f"{h['date']['year']}-{h['date']['month']:02d}-{h['date']['day']:02d}"
        for h in hours_raw
        if "date" in h
    }, reverse=True)

    return {
        "interface": iface_data["name"],
        "date": str(target),
        "upload_bytes": upload_bytes,
        "download_bytes": download_bytes,
        "upload_speed": upload_speed,
        "download_speed": download_speed,
        "peak_upload_bytes": max(upload_bytes),
        "peak_download_bytes": max(download_bytes),
        "peak_upload_speed": max(upload_speed),
        "peak_download_speed": max(download_speed),
        "total_upload": sum(upload_bytes),
        "total_download": sum(download_bytes),
        "available_days": available_days[:90],
        "interfaces": [i["name"] for i in interfaces],
    }


def process_minute_data(vnstat_json: dict, hour: int, interface: Optional[str], day_str: Optional[str]):
    """Extract per-minute data for a specific hour."""
    interfaces = vnstat_json.get("interfaces", [])
    if not interfaces:
        return None

    if interface:
        iface_data = next((i for i in interfaces if i["name"] == interface), interfaces[0])
    else:
        iface_data = interfaces[0]

    if day_str:
        try:
            target = datetime.strptime(day_str, "%Y-%m-%d").date()
        except ValueError:
            target = date.today()
    else:
        target = date.today()

    minutes_raw = iface_data.get("traffic", {}).get("fiveminute", [])

    # filter to our hour
    minutes_in_hour = [
        m for m in minutes_raw
        if m.get("date", {}).get("year") == target.year
        and m.get("date", {}).get("month") == target.month
        and m.get("date", {}).get("day") == target.day
        and m.get("time", {}).get("hour") == hour
    ]

    # vnstat stores 5-minute buckets; expand to per-minute indices 0-59
    upload_bytes = [0] * 60
    download_bytes = [0] * 60
    upload_speed = [0] * 60
    download_speed = [0] * 60

    for m in minutes_in_hour:
        minute = m.get("time", {}).get("minute", 0)
        tx = m.get("tx", 0)
        rx = m.get("rx", 0)
        # fill 5-minute bucket
        for i in range(5):
            idx = minute + i
            if idx < 60:
                upload_bytes[idx] = round(tx / 5)
                download_bytes[idx] = round(rx / 5)
                upload_speed[idx] = round(tx / 5 / 300) if tx else 0
                download_speed[idx] = round(rx / 5 / 300) if rx else 0

    return {
        "hour": hour,
        "upload_bytes": upload_bytes,
        "download_bytes": download_bytes,
        "upload_speed": upload_speed,
        "download_speed": download_speed,
        "peak_upload_bytes": max(upload_bytes),
        "peak_download_bytes": max(download_bytes),
        "peak_upload_speed": max(upload_speed),
        "peak_download_speed": max(download_speed),
    }


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == CONFIG["auth"]["username"] and password == CONFIG["auth"]["password"]:
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("index"))
        error = "Неверный логин или пароль"
    return render_template("index.html", page="login", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    servers = list(CONFIG["servers"].keys())
    return render_template("index.html", page="dashboard", servers=servers)


@app.route("/api/servers")
@login_required
def api_servers():
    result = {}
    with cache_lock:
        for name in CONFIG["servers"]:
            entry = cache.get(name, {})
            result[name] = {
                "updated_at": entry.get("updated_at", datetime.now()).strftime("%H:%M:%S") if entry.get("updated_at") else None,
                "error": entry.get("error"),
                "has_data": entry.get("data") is not None,
            }
    return jsonify(result)


@app.route("/api/data/<server_name>")
@login_required
def api_data(server_name):
    if server_name not in CONFIG["servers"]:
        return jsonify({"error": "Server not found"}), 404

    with cache_lock:
        entry = cache.get(server_name, {})
        entry = copy.deepcopy(entry)  # prevent mutating shared cache

    if not entry.get("data"):
        return jsonify({"error": entry.get("error") or "No data yet, please wait..."}), 503

    day_str = request.args.get("day")
    interface = request.args.get("interface") or CONFIG["servers"][server_name].get("interface")

    result = process_day_data(entry["data"], day_str, interface)
    if not result:
        return jsonify({"error": "Could not process vnstat data"}), 500

    result["server"] = server_name
    result["updated_at"] = entry["updated_at"].strftime("%H:%M:%S") if entry.get("updated_at") else None
    return jsonify(result)


@app.route("/api/minutes/<server_name>")
@login_required
def api_minutes(server_name):
    if server_name not in CONFIG["servers"]:
        return jsonify({"error": "Server not found"}), 404

    with cache_lock:
        entry = cache.get(server_name, {})

    if not entry.get("data"):
        return jsonify({"error": "No data"}), 503

    try:
        hour = int(request.args.get("hour", 0))
    except ValueError:
        hour = 0

    day_str = request.args.get("day")
    interface = request.args.get("interface") or CONFIG["servers"][server_name].get("interface")

    result = process_minute_data(entry["data"], hour, interface, day_str)
    if not result:
        return jsonify({"error": "Could not process minute data"}), 500
    return jsonify(result)


@app.route("/api/refresh/<server_name>", methods=["POST"])
@login_required
def api_refresh(server_name):
    if server_name not in CONFIG["servers"]:
        return jsonify({"error": "Server not found"}), 404
    server = CONFIG["servers"][server_name]
    threading.Thread(target=refresh_server, args=(server_name, server), daemon=True).start()
    return jsonify({"status": "refreshing"})


# ──────────────────────────────────────────────
# Start background thread (always, not just __main__)
# ──────────────────────────────────────────────

_bg_thread = threading.Thread(target=background_refresh, daemon=True)
_bg_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3232, debug=False)
