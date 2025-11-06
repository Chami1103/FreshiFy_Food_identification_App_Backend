"""
Sensor Service - FreshiFy
-------------------------
Provides NH3 + RGB based food spoilage detection.
Port: 5000
"""

import os
import joblib
import warnings
from datetime import datetime
from typing import Any, Dict
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import numpy as np

# Local DB modules
from DB_FreshiFy import FreshiFyDB, FreshifyConfig

# --------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------
load_dotenv()
app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})

cfg = FreshifyConfig()
db = FreshiFyDB(cfg)

# Model paths
MODEL_PATH = os.getenv("SENSOR_MODEL_PATH", "models/logistic_regression_model.pkl")
SCALER_PATH = os.getenv("SENSOR_SCALER_PATH", "models/scaler.joblib")
ENCODER_PATH = os.getenv("SENSOR_LABEL_ENCODER_PATH", "models/label_encoder.joblib")

sensor_model, scaler, label_encoder = None, None, None

try:
    sensor_model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    label_encoder = joblib.load(ENCODER_PATH)
    app.logger.info("Sensor model, scaler, and encoder loaded successfully.")
except Exception as e:
    warnings.warn(f"Model load failed: {e}")
    app.logger.warning(f"Model load failed: {e}")

def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _predict_sensor_logic(payload: Dict[str, Any]) -> Dict[str, Any]:
    nh3 = float(payload.get("nh3", 0))
    r = float(payload.get("r", 0))
    g = float(payload.get("g", 0))
    b = float(payload.get("b", 0))
    mode = payload.get("mode", "check")

    if not sensor_model or not scaler or not label_encoder:
        status = "Spoiled" if nh3 > 50 else "Fresh"
        return {
            "Food": "General_Food",
            "Status": status,
            "Gas": "NH3",
            "NH3": nh3,
            "RGB": [r, g, b],
            "DateTime": _now_str(),
            "mode": mode,
            "prediction": f"General_Food — {status}",
        }

    try:
        arr = np.array([[nh3, r, g, b]])
        scaled = scaler.transform(arr)
        pred_class = sensor_model.predict(scaled)[0]
        label = label_encoder.inverse_transform([pred_class])[0]
        status = "Fresh" if "fresh" in label.lower() else "Spoiled"
        food = label.split("_")[0].capitalize() if "_" in label else "Food"
        return {
            "Food": food,
            "Status": status,
            "Gas": "NH3",
            "NH3": nh3,
            "RGB": [r, g, b],
            "DateTime": _now_str(),
            "mode": mode,
            "prediction": f"{food} — {status}",
        }
    except Exception as e:
        app.logger.warning(f"Prediction error: {e}")
        status = "Spoiled" if nh3 > 50 else "Fresh"
        return {
            "Food": "General_Food",
            "Status": status,
            "Gas": "NH3",
            "NH3": nh3,
            "RGB": [r, g, b],
            "DateTime": _now_str(),
            "mode": mode,
            "prediction": f"General_Food — {status}",
        }

@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "model_loaded": sensor_model is not None,
        "db_connected": db.db is not None,
        "user": cfg.current_user,
    }), 200

@app.route("/predict-sensor", methods=["POST"])
def predict_sensor():
    data = request.get_json(force=True, silent=True) or {}
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400
    pred = _predict_sensor_logic(data)
    return jsonify(pred), 200

if __name__ == "__main__":
    port = int(os.getenv("SENSOR_PORT", "5000"))
    host = os.getenv("SENSOR_HOST", "0.0.0.0")
    print(f"[Sensor] running at http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
