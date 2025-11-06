"""
app/__init__.py
--------------------------------------------------------
FreshiFy Backend Package Initializer
- Loads environment variables (.env)
- Sets up shared logging
- Establishes MongoDB connection (FreshiFyDB)
--------------------------------------------------------
"""

import os
import logging
from dotenv import load_dotenv

# ----------------------------------------------------
# 1️⃣ Load Environment Variables
# ----------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, os.pardir))
ENV_PATH = os.path.join(ROOT_DIR, ".env")

if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)
else:
    print(f"[WARN] .env not found at {ENV_PATH}")

# ----------------------------------------------------
# 2️⃣ Logging Setup (Unified across all modules)
# ----------------------------------------------------
LOG_DIR = os.path.join(ROOT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "app_init.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.getLogger().addHandler(console)

logger = logging.getLogger("FreshiFyInit")
logger.info("🚀 FreshiFy App Initialized — environment loaded from .env")

# ----------------------------------------------------
# 3️⃣ Shared MongoDB Connection
# ----------------------------------------------------
try:
    from app.DB_FreshiFy import FreshiFyDB, FreshifyConfig

    cfg = FreshifyConfig()
    db = FreshiFyDB(cfg)

    if db.db is not None:
        logger.info(f"✅ MongoDB connected → {cfg.mongo_uri} / {cfg.db_name}")
    else:
        logger.warning("⚠️ MongoDB not connected (continuing in offline mode).")

except Exception as e:
    logger.error(f"❌ Failed to initialize MongoDB connection: {e}")
    db = None
    cfg = None

# ----------------------------------------------------
# 4️⃣ Expose shared objects
# ----------------------------------------------------
__all__ = ["logger", "db", "cfg", "FreshiFyDB", "FreshifyConfig"]
