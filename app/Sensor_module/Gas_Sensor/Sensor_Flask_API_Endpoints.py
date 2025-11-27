# File: app/Sensor_module/Gas_Sensor/Sensor_Flask_API_Endpoints.py
"""
FreshiFy Sensor Backend (port 5000)
-----------------------------------
Endpoints:
- GET  /health
- POST /calibrate              (NEW: Receives ESP32 calibration data)
- GET  /live-nh3
- POST /predict-sensor        (JSON body: {nh3, r, g, b, c, mode, deviceId})
- GET  /dashboard/stats
- GET  /dashboard/last-sensor
- GET  /history
"""
import os
import sys
import uuid
import joblib
import warnings
import pathlib
import numpy as np
from datetime import datetime, timezone
from typing import Any, Dict
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# --------------------------------------------------------------------
# Setup - fixed path (backend root)
# --------------------------------------------------------------------
BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[3]  # Go up 3 levels to reach backend root
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Import from app package
from app.DB_FreshiFy import FreshiFyDB, FreshifyConfig

load_dotenv()
app = Flask(__name__)

# Enable CORS
origins_str = os.getenv("CORS_ORIGINS", "")
origins = [o.strip() for o in origins_str.split(",") if o.strip()] or ["*"]
CORS(
    app,
    resources={r"/*": {"origins": origins}},
    supports_credentials=True,
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    methods=["GET", "POST", "OPTIONS"],
)

cfg = FreshifyConfig()
db = FreshiFyDB(cfg)

# --------------------------------------------------------------------
# Model Paths (ENV VARS expected)
# --------------------------------------------------------------------
MODELS_DIR = os.path.join(BACKEND_ROOT, "models")
MODEL_PATH = os.getenv("SENSOR_MODEL_PATH", os.path.join(MODELS_DIR, "logistic_regression_model.pkl"))
SCALER_PATH = os.getenv("SENSOR_SCALER_PATH", os.path.join(MODELS_DIR, "scaler.joblib"))
ENCODER_PATH = os.getenv("SENSOR_LABEL_ENCODER_PATH", os.path.join(MODELS_DIR, "label_encoder.joblib"))

sensor_model = None
scaler = None
label_encoder = None

# --------------------------------------------------------------------
# Load model artifacts
# --------------------------------------------------------------------
try:
    if os.path.exists(MODEL_PATH):
        sensor_model = joblib.load(MODEL_PATH)
        app.logger.info(f"[MODEL] Loaded sensor model from {MODEL_PATH}")
    else:
        raise FileNotFoundError(f"Model not found: {MODEL_PATH}")

    if os.path.exists(SCALER_PATH):
        scaler = joblib.load(SCALER_PATH)
        app.logger.info(f"[MODEL] Loaded scaler from {SCALER_PATH}")
    else:
        raise FileNotFoundError(f"Scaler not found: {SCALER_PATH}")

    if os.path.exists(ENCODER_PATH):
        label_encoder = joblib.load(ENCODER_PATH)
        app.logger.info(f"[MODEL] Loaded label encoder from {ENCODER_PATH}")
    else:
        raise FileNotFoundError(f"Encoder not found: {ENCODER_PATH}")

    app.logger.info("[MODEL] ✅ Sensor model + scaler + encoder loaded successfully.")
except Exception as e:
    warnings.warn(f"[MODEL] Sensor model load failed: {e}")
    app.logger.warning(f"[MODEL] ⚠️ Sensor model load failed: {e}")
    sensor_model, scaler, label_encoder = None, None, None

# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _predict_sensor_logic(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Predict spoilage from NH3 + RGB using ML model.
    Falls back to rule-based prediction if model unavailable.
    Returns structured object and normalized 'prediction' string.
    """
    nh3 = float(payload.get("nh3", 0) or 0)
    r = float(payload.get("r", 0) or 0)
    g = float(payload.get("g", 0) or 0)
    b = float(payload.get("b", 0) or 0)
    mode = payload.get("mode", "check")

    # Simple rule-of-thumb fallback
    if not sensor_model or not scaler or not label_encoder:
        status = "Spoiled" if nh3 > 50 else "Fresh" if nh3 <= 50 else "Unknown"
        pred = {
            "Food": "General_Food",
            "Status": status,
            "Gas": "NH3",
            "NH3": nh3,
            "RGB": [int(r), int(g), int(b)],
            "DateTime": _now_str(),
            "mode": mode,
            "prediction": f"General_Food — {status}",
        }
        return pred

    try:
        arr = np.array([[nh3, r, g, b]])
        scaled = scaler.transform(arr)
        pred_class = sensor_model.predict(scaled)[0]
        # label_encoder may have been trained to map classes to string labels
        label = label_encoder.inverse_transform([pred_class])[0] if label_encoder is not None else str(pred_class)
        status = "Fresh" if "fresh" in label.lower() else "Spoiled"
        food = label.split("_")[0].capitalize() if "_" in label else "Food"
        return {
            "Food": food,
            "Status": status,
            "Gas": "NH3",
            "NH3": nh3,
            "RGB": [int(r), int(g), int(b)],
            "DateTime": _now_str(),
            "mode": mode,
            "prediction": f"{food} — {status}",
        }
    except Exception as e:
        app.logger.warning(f"[MODEL] Prediction error: {e}")
        status = "Spoiled" if nh3 > 50 else "Fresh"
        return {
            "Food": "General_Food",
            "Status": status,
            "Gas": "NH3",
            "NH3": nh3,
            "RGB": [int(r), int(g), int(b)],
            "DateTime": _now_str(),
            "mode": mode,
            "prediction": f"General_Food — {status}",
        }

# --------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "service": "Sensor Service",
        "version": "1.0.0",
        "model_loaded": sensor_model is not None,
        "db_connected": db.db is not None,
        "user": cfg.current_user,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200


@app.route("/calibrate", methods=["POST"])
def calibrate():
    """
    NEW ENDPOINT: Receives calibration data from ESP32
    Expected JSON: {deviceId, status, R0?, reason?}
    """
    data = request.get_json(force=True, silent=True) or {}
    
    device_id = data.get("deviceId", "unknown")
    cal_status = data.get("status", "unknown")
    r0_value = data.get("R0")
    reason = data.get("reason", "")
    
    app.logger.info(f"[CALIBRATE] Device '{device_id}': status={cal_status}, R0={r0_value}, reason={reason}")
    
    # Store calibration record in database
    try:
        calibration_doc = {
            "deviceId": device_id,
            "status": cal_status,
            "R0": r0_value,
            "reason": reason,
            "user": cfg.current_user,
            "timestamp": datetime.now(timezone.utc)
        }
        
        # Insert into calibrations collection
        db.db.calibrations.insert_one(calibration_doc)
        app.logger.info(f"[CALIBRATE] ✅ Stored calibration for device '{device_id}'")
        
    except Exception as e:
        app.logger.warning(f"[CALIBRATE] ⚠️ Database insert failed: {e}")
    
    # Return success response
    response = {
        "ok": True,
        "message": "Calibration data received successfully",
        "deviceId": device_id,
        "status": cal_status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    if cal_status == "ok":
        response["R0"] = r0_value
        app.logger.info(f"[CALIBRATE] ✅ Device '{device_id}' calibrated successfully with R0={r0_value}")
    else:
        response["reason"] = reason
        app.logger.warning(f"[CALIBRATE] ⚠️ Device '{device_id}' calibration failed: {reason}")
    
    return jsonify(response), 200


@app.route("/live-nh3", methods=["GET"])
def live_nh3():
    doc = db.get_live_nh3(cfg.current_user)
    if not doc:
        return jsonify({"nh3": None, "createdAt": None}), 200
    ca = doc.get("createdAt")
    return jsonify({
        "nh3": doc.get("nh3"),
        "createdAt": ca.isoformat() if hasattr(ca, "isoformat") else ca,
    }), 200


@app.route("/predict-sensor", methods=["POST"])
def predict_sensor():
    """
    Receives sensor data from ESP32 and returns prediction
    Expected JSON: {deviceId, nh3, r, g, b, mode?, sensorStatus?}
    """
    data = request.get_json(force=True, silent=True) or {}
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    device_id = data.get("deviceId", "unknown")
    sensor_status = data.get("sensorStatus") or data.get("status")  # Support both field names
    
    app.logger.info(f"[PREDICT] Received data from device '{device_id}': NH3={data.get('nh3')}, RGB=({data.get('r')},{data.get('g')},{data.get('b')})")

    pred = _predict_sensor_logic(data)
    
    # Add device ID to prediction result
    pred["deviceId"] = device_id
    if sensor_status:
        pred["sensorStatus"] = sensor_status

    # Insert result into MongoDB (best-effort; continue even if db fails)
    try:
        db.insert_sensor_result(
            user=cfg.current_user,
            nh3=float(pred.get("NH3", 0)),
            rgb=tuple(pred.get("RGB", (0, 0, 0))),
            c=int(data.get("c", 0) or 0),
            food=pred.get("Food"),
            status=pred.get("Status"),
            source=pred.get("mode", "check"),
            created_at=datetime.now(timezone.utc),
        )
        app.logger.info(f"[PREDICT] ✅ Stored prediction: {pred.get('prediction')}")
    except Exception as e:
        app.logger.warning(f"[PREDICT] ⚠️ Failed to insert sensor result: {e}")

    # Return both structured result and a normalized 'prediction' string
    return jsonify(pred), 200


@app.route("/dashboard/stats", methods=["GET"])
def dashboard_stats():
    stats = db.get_stats(user=cfg.current_user)
    return jsonify(stats), 200


@app.route("/dashboard/last-sensor", methods=["GET"])
def last_sensor():
    doc = db.get_last_sensor(cfg.current_user)
    if not doc:
        return jsonify(None), 200
    ca = doc.get("createdAt")
    return jsonify({
        "food": doc.get("food"),
        "status": doc.get("status"),
        "nh3": doc.get("nh3"),
        "createdAt": ca.isoformat() if hasattr(ca, "isoformat") else ca,
    }), 200


@app.route("/history", methods=["GET"])
def history():
    try:
        limit = int(request.args.get("limit", 30))
    except ValueError:
        limit = 30
    items = db.get_history(user=cfg.current_user, limit=limit)
    sensors_only = [i for i in items if i.get("type") == "sensor"]
    return jsonify(sensors_only), 200


@app.route("/calibrations", methods=["GET"])
def get_calibrations():
    """
    NEW ENDPOINT: Retrieve calibration history
    Query params: device_id (optional), limit (default 10)
    """
    try:
        device_id = request.args.get("device_id")
        limit = int(request.args.get("limit", 10))
        
        query = {"user": cfg.current_user}
        if device_id:
            query["deviceId"] = device_id
        
        calibrations = list(
            db.db.calibrations
            .find(query)
            .sort("timestamp", -1)
            .limit(limit)
        )
        
        # Convert ObjectId to string for JSON serialization
        for cal in calibrations:
            cal["_id"] = str(cal["_id"])
            if "timestamp" in cal and hasattr(cal["timestamp"], "isoformat"):
                cal["timestamp"] = cal["timestamp"].isoformat()
        
        return jsonify(calibrations), 200
        
    except Exception as e:
        app.logger.error(f"[CALIBRATIONS] Error fetching calibrations: {e}")
        return jsonify({"error": "Failed to fetch calibrations"}), 500


# --------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("SENSOR_PORT", "5000"))
    host = os.getenv("SENSOR_HOST", "0.0.0.0")
    debug = os.getenv("DEBUG", "False").lower() == "true"
    
    print("=" * 70)
    print("🔬 FreshiFy Sensor Service")
    print("=" * 70)
    print(f"📍 Starting on: http://{host}:{port}")
    print(f"🔧 Debug mode: {debug}")
    print(f"🤖 Model loaded: {sensor_model is not None}")
    print(f"🗄️  Database: {cfg.db_name}")
    print(f"👤 User: {cfg.current_user}")
    print("=" * 70)
    print("📡 Available Endpoints:")
    print("   GET  /health")
    print("   POST /calibrate          (NEW - ESP32 calibration)")
    print("   GET  /live-nh3")
    print("   POST /predict-sensor")
    print("   GET  /dashboard/stats")
    print("   GET  /dashboard/last-sensor")
    print("   GET  /history")
    print("   GET  /calibrations       (NEW - calibration history)")
    print("=" * 70)
    
    app.logger.info("[SENSOR] Starting on %s:%s model_loaded=%s db_connected=%s",
                    host, port, sensor_model is not None, db.db is not None)
    app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)