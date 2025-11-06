"""
Image Detection Service - FreshiFy
----------------------------------
Classifies food freshness from images using MobileNetV2.
Port: 5001
"""

import os
import uuid
import pathlib
import warnings
from datetime import datetime, timezone
from typing import Dict, List
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import numpy as np

from DB_FreshiFy import FreshiFyDB, FreshifyConfig

# Setup
load_dotenv()
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

cfg = FreshifyConfig()
db = FreshiFyDB(cfg)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_EXT = {".jpg", ".jpeg", ".png"}

MODEL_PATH = os.getenv("MODEL_PATH", "models/Fruit_Classifier.h5")

_tf_loaded = False
image_model = None
label_mapping = {
    0: "apple_fresh",
    1: "apple_spoiled",
    2: "banana_fresh",
    3: "banana_spoiled",
    4: "carrot_fresh",
    5: "carrot_spoiled",
}

try:
    import tensorflow as tf
    from tensorflow.keras.utils import load_img, img_to_array
    if os.path.exists(MODEL_PATH):
        image_model = tf.keras.models.load_model(MODEL_PATH)
        _tf_loaded = True
except Exception as e:
    warnings.warn(f"TensorFlow not available: {e}")

def _predict_with_model(path: str) -> Dict[str, str]:
    if not _tf_loaded or image_model is None:
        return {"food": "Unknown", "status": "Fresh", "confidence": 0.5}
    img = load_img(path, target_size=(224, 224))
    arr = img_to_array(img)
    arr = tf.keras.applications.mobilenet_v2.preprocess_input(arr)
    arr = np.expand_dims(arr, 0)
    preds = image_model.predict(arr, verbose=0)
    idx = int(np.argmax(preds, axis=-1)[0])
    label = label_mapping.get(idx, "unknown_fresh")
    parts = label.split("_")
    return {
        "food": parts[0].capitalize(),
        "status": parts[1].capitalize(),
        "confidence": round(float(np.max(preds[0])), 3),
    }

@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "model_loaded": _tf_loaded,
        "uploads": os.path.isdir(UPLOAD_DIR),
    }), 200

@app.route("/predict-image", methods=["POST"])
def predict_image():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No image provided"}), 400
    ext = pathlib.Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        ext = ".jpg"
    fname = secure_filename(f"{uuid.uuid4().hex}{ext}")
    path = os.path.join(UPLOAD_DIR, fname)
    file.save(path)

    pred = _predict_with_model(path)
    db.insert_image_result(
        user=cfg.current_user,
        food=pred["food"],
        status=pred["status"],
        file_name=fname,
        source="upload",
        created_at=datetime.now(timezone.utc),
    )

    return jsonify({
        "prediction": f"{pred['food']} — {pred['status']}",
        "confidence": pred["confidence"],
    }), 200

if __name__ == "__main__":
    port = int(os.getenv("IMAGE_PORT", "5001"))
    host = os.getenv("IMAGE_HOST", "0.0.0.0")
    print(f"[Image] running at http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
