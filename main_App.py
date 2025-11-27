# E:\FreshiFy_Mobile_App_Backend\main_App.py (MOVE TO ROOT)
"""
FreshiFy Backend Launcher (Fixed Paths)
------------------------------------
Launches 4 backend microservices with auto-recovery, path validation, and live log streaming.

Services:
1️⃣ Sensor Service        → http://0.0.0.0:5000
2️⃣ Image Service         → http://0.0.0.0:5001
3️⃣ Notification Service  → http://0.0.0.0:5002
4️⃣ Auth Service          → http://0.0.0.0:5003
"""
import os
import sys
import time
import subprocess
import threading
import logging
from pathlib import Path
from dotenv import load_dotenv

# ============================================================================
# Environment & Base Setup
# ============================================================================
BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"
os.chdir(BASE_DIR)
os.environ["PYTHONPATH"] = str(BASE_DIR)
load_dotenv(BASE_DIR / ".env")

# Log directory
LOG_DIR = APP_DIR / "logs"
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

# ============================================================================
# Banner
# ============================================================================
print("=" * 70)
print(" ███████╗██████╗ ███████╗███████╗██╗  ██╗██╗███████╗██╗   ██╗")
print(" ██╔════╝██╔══██╗██╔════╝██╔════╝██║  ██║██║██╔════╝╚██╗ ██╔╝")
print(" █████╗  ██████╔╝█████╗  ███████╗███████║██║█████╗   ╚████╔╝ ")
print(" ██╔══╝  ██╔══██╗██╔══╝  ╚════██║██╔══██║██║██╔══╝    ╚██╔╝  ")
print(" ██║     ██║  ██║███████╗███████║██║  ██║██║██║        ██║   ")
print(" ╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝╚═╝        ╚═╝   ")
print("=" * 70)
print(f"📁 BASE DIRECTORY: {BASE_DIR}")
print(f"📁 APP DIRECTORY: {APP_DIR}")
print(f"🗂️  LOG DIRECTORY: {LOG_DIR}")
print("=" * 70)

logger.info("[INFO] FreshiFy Backend Services Starting...")

# ============================================================================
# Helper Functions
# ============================================================================
def ensure_file(path: Path, name: str) -> Path:
    """Ensure a microservice file exists or attempt auto-detect."""
    if not path.exists():
        logger.warning(f"[WARN] {name} path not found: {path}")
        # Try to auto-detect
        alt = list(path.parent.glob(f"*{path.stem}*.py")) if path.parent.exists() else []
        if alt:
            detected = alt[0]
            logger.warning(f"[WARN] Auto-detected alternative: {detected}")
            return detected
        logger.error(f"[ERROR] {name} service file not found at {path}")
        return None
    logger.info(f"[✓] {name} service file found: {path.name}")
    return path


def stream_output(prefix: str, proc: subprocess.Popen):
    """Continuously stream subprocess stdout to console."""
    try:
        for line in iter(proc.stdout.readline, ""):
            if line:
                sys.stdout.write(f"[{prefix}] {line}")
                sys.stdout.flush()
    except Exception as e:
        logger.error(f"[{prefix}] Stream error: {e}")


def start_service(name: str, path: Path) -> subprocess.Popen | None:
    """Launch a subprocess and stream its logs."""
    if not path or not path.exists():
        logger.error(f"[ERROR] {name} file missing, skipping launch.")
        return None

    logger.info(f"[START] Launching {name} service: {path.name}")
    try:
        proc = subprocess.Popen(
            [sys.executable, str(path)],
            cwd=str(APP_DIR),  # Changed: Run from APP_DIR
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        
        # Start log streaming thread
        thread = threading.Thread(
            target=stream_output, 
            args=(name.upper(), proc), 
            daemon=True
        )
        thread.start()
        
        logger.info(f"[✓] {name} service started (PID: {proc.pid})")
        return proc
        
    except Exception as e:
        logger.error(f"[ERROR] Failed to start {name}: {e}")
        return None


# ============================================================================
# Microservice Paths (FIXED)
# ============================================================================
print("\n🔍 Locating Service Files...")
print("-" * 70)

# Look for services in the app directory
SENSOR_SERVICE = ensure_file(
    APP_DIR / "Sensor_Flask_API_Endpoints.py",
    "Sensor"
)
IMAGE_SERVICE = ensure_file(
    APP_DIR / "Image_Flask_API_Endpoints.py",
    "Image"
)
NOTIFY_SERVICE = ensure_file(
    APP_DIR / "Notify_Alerts.py",
    "Notification"
)
AUTH_SERVICE = ensure_file(
    APP_DIR / "Auth_Service.py",
    "Authentication"
)

print("-" * 70)

# ============================================================================
# Start All Services
# ============================================================================
print("\n🚀 Starting Services...")
print("-" * 70)

services = {
    "Sensor": start_service("Sensor", SENSOR_SERVICE),
    "Image": start_service("Image", IMAGE_SERVICE),
    "Notifications": start_service("Notify", NOTIFY_SERVICE),
    "Auth": start_service("Auth", AUTH_SERVICE),
}

# Wait for services to initialize
time.sleep(2)

print("-" * 70)
print("\n✅ All Services Started Successfully!")
print("=" * 70)
print("📡 Service Endpoints:")
print("-" * 70)
print("  🔬 Sensor Service:        http://0.0.0.0:5000")
print("  🖼️  Image Service:         http://0.0.0.0:5001")
print("  🔔 Notification Service:  http://0.0.0.0:5002")
print("  🔐 Auth Service:          http://0.0.0.0:5003")
print("=" * 70)
print("\n⚡ Monitoring services for crashes... (Press Ctrl+C to stop)")
print("-" * 70)

# ============================================================================
# Auto-Restart Monitor
# ============================================================================
restart_count = {name: 0 for name in services.keys()}
MAX_RESTARTS = 5
RESTART_WINDOW = 60

try:
    while True:
        for name, proc in list(services.items()):
            if proc and proc.poll() is not None:
                exit_code = proc.returncode
                restart_count[name] += 1
                
                logger.warning(f"[{name}] ❌ Service crashed (Exit code: {exit_code})")
                
                if restart_count[name] > MAX_RESTARTS:
                    logger.error(
                        f"[{name}] ⚠️  Service crashed {MAX_RESTARTS}+ times. "
                        "Manual intervention required."
                    )
                    services[name] = None
                    continue
                
                logger.info(f"[{name}] 🔄 Restarting... (Attempt {restart_count[name]})")
                time.sleep(2)
                
                # Determine path
                path = (
                    SENSOR_SERVICE if name == "Sensor"
                    else IMAGE_SERVICE if name == "Image"
                    else NOTIFY_SERVICE if name == "Notifications"
                    else AUTH_SERVICE
                )
                
                services[name] = start_service(name, path)
        
        time.sleep(3)

except KeyboardInterrupt:
    print("\n" + "=" * 70)
    logger.warning("[STOP] ⚠️  Keyboard interrupt received. Shutting down...")
    print("-" * 70)
    
    for name, proc in services.items():
        if proc:
            logger.info(f"[{name}] 🛑 Terminating...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
                logger.info(f"[{name}] ✓ Stopped cleanly")
            except subprocess.TimeoutExpired:
                logger.warning(f"[{name}] ⚠️  Force killing...")
                proc.kill()
    
    print("-" * 70)
    logger.info("[DONE] ✅ All services stopped cleanly.")
    print("=" * 70)
    print("👋 Goodbye!")