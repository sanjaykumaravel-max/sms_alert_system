from flask import Flask, request, jsonify
import os
from pathlib import Path
import threading
import json

try:
    from .app_paths import data_path
except Exception:
    from app_paths import data_path

try:
    from sms_service import default_sms_service
except Exception:
    default_sms_service = None

app = Flask(__name__)

# Simple file-backed storage
_data_lock = threading.Lock()
_data_dir = data_path()
_data_dir.mkdir(parents=True, exist_ok=True)
_hour_file = _data_dir / "hour_entries.json"
_plant_file = _data_dir / "plant_components.json"

@app.route("/health", methods=["GET"]) 
def health():
    return jsonify({"status": "ok"})


def _read_json_file(path: Path, default):
    try:
        if not path.exists():
            return default
        with path.open('r', encoding='utf-8') as f:
            return json.load(f) or default
    except Exception:
        return default


def _write_json_file(path: Path, data) -> bool:
    try:
        with _data_lock:
            with path.open('w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


@app.route('/api/hour_entries', methods=['GET', 'POST'])
def api_hour_entries():
    # Optional auth
    server_key = os.environ.get('SERVER_API_KEY')
    if server_key:
        provided = request.headers.get('X-API-KEY') or request.args.get('api_key')
        if provided != server_key:
            return jsonify({'success': False, 'error': 'unauthorized'}), 401

    if request.method == 'GET':
        data = _read_json_file(_hour_file, [])
        return jsonify(data)

    # POST: append an entry
    try:
        entry = request.get_json(force=True)
    except Exception:
        return jsonify({'success': False, 'error': 'invalid json'}), 400
    if not isinstance(entry, dict):
        return jsonify({'success': False, 'error': 'entry must be an object'}), 400
    data = _read_json_file(_hour_file, [])
    data.append(entry)
    ok = _write_json_file(_hour_file, data)
    if not ok:
        return jsonify({'success': False, 'error': 'failed to persist'}), 500
    return jsonify({'success': True, 'entry': entry}), 201


@app.route('/api/plant_components', methods=['GET', 'PUT'])
def api_plant_components():
    server_key = os.environ.get('SERVER_API_KEY')
    if server_key:
        provided = request.headers.get('X-API-KEY') or request.args.get('api_key')
        if provided != server_key:
            return jsonify({'success': False, 'error': 'unauthorized'}), 401

    if request.method == 'GET':
        data = _read_json_file(_plant_file, {})
        return jsonify(data)

    # PUT: replace mapping
    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({'success': False, 'error': 'invalid json'}), 400
    if not isinstance(payload, dict):
        return jsonify({'success': False, 'error': 'payload must be an object'}), 400
    ok = _write_json_file(_plant_file, payload)
    if not ok:
        return jsonify({'success': False, 'error': 'failed to persist'}), 500
    return jsonify({'success': True})

@app.route("/send", methods=["POST"])
def send_sms():
    if not default_sms_service:
        return jsonify({"success": False, "error": "SMS service unavailable"}), 500

    data = request.get_json(force=True)
    to = data.get("to")
    message = data.get("message")
    if not to or not message:
        return jsonify({"success": False, "error": "missing 'to' or 'message'"}), 400

    # Optional simple auth: header X-API-KEY or env SERVER_API_KEY
    server_key = os.environ.get("SERVER_API_KEY")
    if server_key:
        provided = request.headers.get("X-API-KEY") or request.args.get("api_key")
        if provided != server_key:
            return jsonify({"success": False, "error": "unauthorized"}), 401

    try:
        res = default_sms_service.send(to, message)
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
