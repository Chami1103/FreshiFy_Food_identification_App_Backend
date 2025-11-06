"""
Notify Service - FreshiFy
-------------------------
Handles notifications, calendar, blogs, and calculations.
Port: 5002
"""

import os
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from DB_FreshiFy import FreshiFyDB, FreshifyConfig

load_dotenv()
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

cfg = FreshifyConfig()
db = FreshiFyDB(cfg)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notify_service")

@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "db_connected": db.db is not None,
        "service": "notify_service",
    }), 200

@app.route("/notify", methods=["POST"])
def notify():
    data = request.get_json(silent=True) or {}
    msg = data.get("message")
    if not msg:
        return jsonify({"error": "message required"}), 400
    db.insert_notification(msg)
    logger.info(f"Notification added: {msg}")
    return jsonify({"ok": True}), 201

@app.route("/notifications", methods=["GET"])
def notifications():
    docs = db.notifications.find({"user": cfg.current_user}) if db.notifications else []
    results = [{"id": str(d.get("_id")), "message": d.get("message")} for d in docs]
    return jsonify(results), 200

if __name__ == "__main__":
    port = int(os.getenv("NOTIFY_PORT", "5002"))
    host = os.getenv("NOTIFY_HOST", "0.0.0.0")
    print(f"[Notify] running at http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
