# E:\Freshify\FreshiFy_Mobile_App_Backend\main_App.py
"""
FreshiFy Backend Launcher (Improved)
------------------------------------
Launches 3 backend microservices with auto-recovery, path validation, and live log streaming.

Services:
1️⃣ Sensor Service        → http://0.0.0.0:5000
2️⃣ Image Service         → http://0.0.0.0:5001
3️⃣ Notification Service  → http://0.0.0.0:5002
"""

import os
import sys
import time
import subprocess
import threading
import logging
from pathlib import Path
from dotenv import load_dotenv

# --------------------------------------------------------------------
# Environment & Base Setup
# --------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
os.environ["PYTHONPATH"] = str(BASE_DIR)
load_dotenv(BASE_DIR / ".env")

# Log directory
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "main.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("FreshiFyMain")

logger.info("[INFO] BASE: %s", BASE_DIR)

# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
def ensure_file(path: Path, name: str) -> Path:
    """Ensure a microservice file exists or attempt auto-detect."""
    if not path.exists():
        alt = list(path.parent.glob(f"{path.stem}*.py"))
        if alt:
            detected = alt[0]
            logger.warning("[WARN] %s path not found; auto-detected: %s", name, detected)
            return detected
        logger.error("[ERROR] %s not found at %s", name, path)
        return None
    return path


def stream_output(prefix: str, proc: subprocess.Popen):
    """Continuously stream subprocess stdout to console."""
    try:
        for line in iter(proc.stdout.readline, ""):
            if line:
                sys.stdout.write(f"[{prefix}] {line}")
                sys.stdout.flush()
    except Exception as e:
        logger.error("[%s] stream error: %s", prefix, e)


def start_service(name: str, path: Path) -> subprocess.Popen | None:
    """Launch a subprocess and stream its logs."""
    if not path or not path.exists():
        logger.error("[ERROR] %s file missing, skipping launch.", name)
        return None

    logger.info("[START] Launching %s", path.name)
    proc = subprocess.Popen(
        [sys.executable, str(path)],
        cwd=str(path.parent),
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # line-buffered
    )
    thread = threading.Thread(target=stream_output, args=(name.upper(), proc), daemon=True)
    thread.start()
    return proc


# --------------------------------------------------------------------
# Microservice Paths
# --------------------------------------------------------------------
SENSOR_SERVICE = ensure_file(BASE_DIR / "Sensor_module" / "Gas_Sensor" / "Sensor_Flask_API_Endpoints.py", "Sensor")
IMAGE_SERVICE = ensure_file(BASE_DIR / "Image_Processing" / "Image_Flask_API_Endpoints.py", "Image")
NOTIFY_SERVICE = ensure_file(BASE_DIR / "Notify_Alerts.py", "Notify")

# --------------------------------------------------------------------
# Start All Services
# --------------------------------------------------------------------
services = {
    "Sensor": start_service("Sensor", SENSOR_SERVICE),
    "Image": start_service("Image", IMAGE_SERVICE),
    "Notifications": start_service("Notify", NOTIFY_SERVICE),
}

logger.info("[READY] All services started (Sensor:5000 Image:5001 Notify:5002)\n")

# --------------------------------------------------------------------
# Auto-Restart Monitor
# --------------------------------------------------------------------
try:
    while True:
        for name, proc in list(services.items()):
            if proc and proc.poll() is not None:
                logger.warning("[%s] ❌ crashed — restarting...", name)
                time.sleep(2)
                path = (
                    SENSOR_SERVICE if name == "Sensor"
                    else IMAGE_SERVICE if name == "Image"
                    else NOTIFY_SERVICE
                )
                services[name] = start_service(name, path)
        time.sleep(3)

except KeyboardInterrupt:
    logger.warning("[STOP] Keyboard interrupt received. Shutting down...")
    for name, proc in services.items():
        if proc:
            logger.info("[%s] Terminating...", name)
            proc.terminate()
    logger.info("[DONE] All services stopped cleanly.")
