# File: Image_Processing/Image_Flask_API_Endpoints.py
"""
Image FreshiFy Backend (configurable port)
Endpoints:
- GET  /health
- POST /predict-image      (multipart/form-data; accepts 'images' list OR single 'file')
- GET  /dashboard/last-image
- GET  /history
"""
from __future__ import annotations
import os
import sys
import pathlib
import uuid
import warnings
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# ensure backend root is on path
BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from DB_FreshiFy import FreshiFyDB, FreshifyConfig

load_dotenv()
app = Flask(__name__)

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

UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.getcwd(), "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".bmp"}

MODEL_PATH = os.getenv("MODEL_PATH", os.path.join(os.getcwd(), "models", "Fruit_Classifier.h5"))

image_model = None
_tf_loaded = False

# Label mapping — ensure this matches the model's output indexing
label_mapping = {
    0: "apple_fresh",
    1: "apple_spoiled",
    2: "banana_fresh",
    3: "banana_spoiled",
    4: "bellpepper_fresh",
    5: "bellpepper_spoiled",
    6: "bittergourd_fresh",
    7: "bittergourd_spoiled",
    8: "carrot_fresh",
    9: "carrot_spoiled",
    10: "tomato_fresh",
    11: "tomato_spoiled",
}

# Try TensorFlow import and model load
try:
    import tensorflow as tf
    from tensorflow.keras.utils import load_img, img_to_array

    if os.path.exists(MODEL_PATH):
        image_model = tf.keras.models.load_model(MODEL_PATH)
        _tf_loaded = True
        app.logger.info("[MODEL] Loaded TensorFlow model from %s", MODEL_PATH)
    else:
        warnings.warn(f"[MODEL] Fruit_Classifier not found at {MODEL_PATH}")
        app.logger.warning("[MODEL] Model file not found at %s", MODEL_PATH)
except Exception as e:
    warnings.warn(f"[MODEL] TensorFlow load failed: {e}")
    app.logger.warning("[MODEL] TensorFlow not available: %s", e)
    image_model = None
    _tf_loaded = False


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _predict_fallback(filename: str) -> Dict[str, Any]:
    # lightweight fallback if TF not available
    lower = filename.lower()
    if "apple" in lower:
        return {"food": "Apple", "status": "Fresh", "confidence": 0.75}
    if "spoiled" in lower or "mold" in lower:
        return {"food": "Unknown", "status": "Spoiled", "confidence": 0.8}
    if "tomato" in lower:
        return {"food": "Tomato", "status": "Fresh", "confidence": 0.7}
    return {"food": "General_Food", "status": "Fresh", "confidence": 0.6}


def _predict_with_model(path: str) -> Dict[str, Any]:
    if not _tf_loaded or image_model is None:
        return _predict_fallback(path)
    try:
        import numpy as np
        img = load_img(path, target_size=(224, 224))
        arr = img_to_array(img)
        arr = tf.keras.applications.mobilenet_v2.preprocess_input(arr)
        arr = np.expand_dims(arr, 0)
        preds = image_model.predict(arr, verbose=0)
        idx = int(np.argmax(preds, axis=-1)[0])
        label = label_mapping.get(idx, "unknown_fresh")
        parts = label.split("_")
        food = parts[0].capitalize()
        status = parts[1].capitalize() if len(parts) > 1 else "Unknown"
        confidence = float(np.max(preds[0])) if hasattr(preds, "shape") else 0.0
        return {"food": food, "status": status, "confidence": round(confidence, 3)}
    except Exception as e:
        app.logger.warning("[MODEL] Prediction error: %s", e)
        return _predict_fallback(path)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "model_loaded": _tf_loaded,
        "db_connected": db.db is not None,
        "uploads": os.path.isdir(UPLOAD_DIR),
    }), 200


@app.route("/predict-image", methods=["POST"])
def predict_image():
    """
    Accepts:
    - multipart form with field 'images' (list) OR
    - multipart form with single file field 'file'
    Returns:
    - For single file: {"prediction": "<Food> — <Status>", "result": {...}}
    - For multi file: {"count": n, "results": [...], "predictions": ["X — Y", ...]}
    """
    # Accept both single-file name `file` (used by app) and `images` (legacy)
    files = []
    if "images" in request.files:
        files = request.files.getlist("images")
    elif "file" in request.files:
        files = [request.files.get("file")]
    else:
        return jsonify({"error": "No image file found (expected 'file' or 'images')"}), 400

    if not files:
        return jsonify({"error": "No images uploaded"}), 400
    if len(files) > 8:
        return jsonify({"error": "Maximum 8 images allowed"}), 400

    results: List[Dict[str, Any]] = []
    predictions: List[str] = []
    for f in files:
        orig_name = f.filename or f"img_{uuid.uuid4().hex}.jpg"
        ext = pathlib.Path(orig_name).suffix.lower()
        if ext not in ALLOWED_EXT:
            ext = ".jpg"
        fname = secure_filename(f"{uuid.uuid4().hex}{ext}")
        path = os.path.join(UPLOAD_DIR, fname)
        try:
            f.save(path)
        except Exception as e:
            app.logger.warning("[UPLOAD] Save failed for %s: %s", orig_name, e)
            continue

        pred = _predict_with_model(path)
        # Normalized prediction string to match frontend expectation
        pred_str = f"{pred.get('food', 'Unknown')} — {pred.get('status', 'Unknown')}"
        predictions.append(pred_str)

        try:
            # Insert with UTC created_at
            db.insert_image_result(
                user=cfg.current_user,
                food=pred["food"],
                status=pred["status"],
                file_name=fname,
                source="upload",
                created_at=datetime.now(timezone.utc),
            )
        except Exception as e:
            app.logger.warning("[DB] insert_image_result failed: %s", e)

        results.append({
            "file": fname,
            "food": pred["food"],
            "status": pred["status"],
            "confidence": pred.get("confidence", 0.0),
            "DateTime": _now_str(),
        })

    # Response formatting:
    if len(results) == 1:
        return jsonify({
            "prediction": predictions[0],
            "result": results[0],
        }), 200
    else:
        return jsonify({
            "count": len(results),
            "results": results,
            "predictions": predictions,
        }), 200


@app.route("/dashboard/last-image", methods=["GET"])
def last_image():
    doc = db.get_last_image(cfg.current_user)
    if not doc:
        return jsonify(None), 200
    ca = doc.get("createdAt")
    return jsonify({
        "food": doc.get("food"),
        "status": doc.get("status"),
        "file": doc.get("file"),
        "createdAt": ca.isoformat() if hasattr(ca, "isoformat") else ca,
    }), 200


@app.route("/history", methods=["GET"])
def history():
    try:
        limit = int(request.args.get("limit", 30))
    except ValueError:
        limit = 30
    items = db.get_history(user=cfg.current_user, limit=limit)
    images_only = [i for i in items if i.get("type") == "image"]
    return jsonify(images_only), 200


if __name__ == "__main__":
    port = int(os.getenv("IMAGE_PORT", "5001"))
    host = os.getenv("IMAGE_HOST", "0.0.0.0")
    app.logger.info("[IMAGE] starting on %s:%s tf_loaded=%s db_connected=%s",
                    host, port, _tf_loaded, db.db is not None)
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
