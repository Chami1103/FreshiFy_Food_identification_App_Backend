"""
Notify_Alerts.py — Notification / Calendar / Blog / Calculator Backend (configurable port)
Uses FreshiFyDB for persistence and prefers waitress if installed.
"""
#E:\FreshiFy_Mobile_App_Backend\app\Notify_Alerts.py
import os
import signal
import logging
import threading
from contextlib import suppress
from typing import Any, Dict, List, Optional
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from DB_FreshiFy import FreshiFyDB, FreshifyConfig

try:
    from waitress import serve as waitress_serve
except Exception:
    waitress_serve = None

# ------------------------------------------------------------
# Setup Environment & Logging
# ------------------------------------------------------------
load_dotenv()

LOG_DIR = os.path.join(os.getcwd(), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

logging.basicConfig(
    filename=os.path.join(LOG_DIR, "notify.log"),
    level=os.getenv("LOG_LEVEL", "INFO"),
    format=LOG_FORMAT
)
_console = logging.StreamHandler()
_console.setLevel(logging.getLogger().level)
_console.setFormatter(logging.Formatter(LOG_FORMAT))
logging.getLogger().addHandler(_console)
logger = logging.getLogger("notify_alerts")

# ------------------------------------------------------------
# Flask App Setup
# ------------------------------------------------------------
app = Flask(__name__, static_folder=None)
origins_env = (os.getenv("CORS_ORIGINS") or "").strip()
origins = [o.strip() for o in origins_env.split(",") if o.strip()] or ["*"]
CORS(
    app,
    resources={r"/*": {"origins": origins}},
    supports_credentials=True,
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    methods=["GET", "POST", "DELETE", "OPTIONS"]
)

# ------------------------------------------------------------
# DB Setup
# ------------------------------------------------------------
cfg = FreshifyConfig()
db = FreshiFyDB(cfg)
logger.info("DB wrapper initialized (connected=%s)", db.db is not None)


# ------------------------------------------------------------
# Helper Functions & Error Classes
# ------------------------------------------------------------
def _json_req(required: Optional[List[str]] = None) -> Dict[str, Any]:
    body = request.get_json(silent=True) or {}
    if required:
        missing = [k for k in required if (body.get(k) is None or (isinstance(body.get(k), str) and not body.get(k).strip()))]
        if missing:
            raise BadRequestError(f"Missing required fields: {', '.join(missing)}")
    return body


class BadRequestError(Exception):
    pass


class NotFoundError(Exception):
    pass


@app.errorhandler(BadRequestError)
def handle_bad_request(e):
    logger.warning("BadRequest: %s %s", e, request.path)
    return jsonify({"ok": False, "error": str(e)}), 400


@app.errorhandler(NotFoundError)
def handle_not_found(e):
    logger.warning("NotFound: %s %s", e, request.path)
    return jsonify({"ok": False, "error": str(e)}), 404


@app.errorhandler(Exception)
def handle_exception(e):
    logger.exception("Unhandled exception while processing %s %s: %s", request.method, request.path, e)
    return jsonify({"ok": False, "error": "internal_server_error"}), 500


# ------------------------------------------------------------
# Health Endpoint
# ------------------------------------------------------------
@app.get("/health")
def health():
    db_ok = bool(db.db)
    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "service": "notify_calendar_blog",
        "version": "v1.1",
        "db_connected": db_ok,
    }), 200


# ------------------------------------------------------------
# Notifications
# ------------------------------------------------------------
@app.get("/notifications")
def list_notifications():
    limit = min(int(request.args.get("limit", 50)), 500)
    out = []
    try:
        if db.notifications is None:
            logger.warning("[NOTIFY] Notifications collection is None")
            return jsonify([]), 200

        cur = db.notifications.find({"user": cfg.current_user}).sort("createdAt", -1).limit(limit)
        for d in cur:
            ca = d.get("createdAt")
            out.append({
                "id": str(d.get("_id")),
                "message": d.get("message"),
                "createdAt": ca.isoformat() if hasattr(ca, "isoformat") else ca
            })
    except Exception as e:
        logger.warning("[NOTIFY] Error listing notifications: %s", e)
        raise
    return jsonify(out), 200


@app.post("/notify")
def add_notification():
    body = _json_req(required=["message"])
    msg = (body.get("message") or "").strip()
    if not msg:
        raise BadRequestError("message is required")
    try:
        nid = db.insert_notification(msg)
        logger.info("[NOTIFY] Added notification id=%s message=%s", nid, msg[:80])
        return jsonify({"ok": True, "id": nid}), 201
    except Exception:
        logger.exception("[NOTIFY] Insert error")
        raise


# ------------------------------------------------------------
# Thoughts (Floating notes from the mobile client)
# ------------------------------------------------------------
@app.post("/thoughts/add")
def thoughts_add():
    """
    Accepts JSON: { "text": "Tomorrow eat fried rice" }
    Stores the note in the 'thoughts' collection.
    """
    body = _json_req(required=["text"])
    text = (body.get("text") or "").strip()
    if not text:
        raise BadRequestError("text is required")
    # optional length/word guard server-side (app also enforces)
    words = len(text.split())
    if words > 60:
        # allow more on server but warn client ideally; here we cap and store first 60 words
        text = " ".join(text.split()[:60])
    try:
        tid = db.add_thought(text=text, user=cfg.current_user)
        logger.info("[THOUGHT] Added thought id=%s user=%s len=%d", tid, cfg.current_user, len(text))
        return jsonify({"ok": True, "id": tid}), 201
    except Exception:
        logger.exception("[THOUGHT] Insert error")
        raise


@app.get("/thoughts/list")
def thoughts_list():
    """
    Query params:
      - limit (optional)
    Returns: latest thoughts for current user.
    """
    limit = min(int(request.args.get("limit", 50)), 500)
    try:
        items = db.list_thoughts(user=cfg.current_user, limit=limit)
        return jsonify(items), 200
    except Exception:
        logger.exception("[THOUGHT] List error")
        raise


# ------------------------------------------------------------
# Calendar
# ------------------------------------------------------------
@app.post("/calendar/add")
def calendar_add():
    body = _json_req(required=["title", "start"])
    title = (body.get("title") or "").strip()
    start = (body.get("start") or "").strip()
    end = (body.get("end") or "").strip() or None
    notes = (body.get("notes") or "").strip() or None
    try:
        eid = db.add_calendar_event(title=title, start=start, end=end, notes=notes)
        logger.info("[CALENDAR] Added event id=%s title=%s", eid, title)
        return jsonify({"ok": True, "id": eid}), 201
    except Exception:
        logger.exception("[CALENDAR] Add error")
        raise


@app.get("/calendar/events")
def calendar_events():
    start_from = request.args.get("from") or None
    end_to = request.args.get("to") or None
    limit = min(int(request.args.get("limit", 100)), 1000)
    try:
        items = db.list_calendar_events(start_from=start_from, end_to=end_to, limit=limit)
        return jsonify(items), 200
    except Exception:
        logger.warning("[CALENDAR] List error")
        raise


@app.delete("/calendar/delete/<event_id>")
def calendar_delete(event_id: str):
    try:
        ok = db.delete_calendar_event(event_id)
        logger.info("[CALENDAR] Deleted event id=%s ok=%s", event_id, ok)
        return jsonify({"ok": ok}), 200
    except Exception:
        logger.exception("[CALENDAR] Delete error")
        raise


# ------------------------------------------------------------
# Blogs
# ------------------------------------------------------------
@app.post("/blogs/add")
def blogs_add():
    body = _json_req(required=["title", "content"])
    title = (body.get("title") or "").strip()
    content = (body.get("content") or "").strip()
    category = (body.get("category") or "").strip() or None
    author = (body.get("author") or "").strip() or None
    readTime = (body.get("readTime") or "").strip() or None
    tags = body.get("tags") or []
    image = (body.get("image") or "").strip() or None

    try:
        bid = db.add_blog(
            title=title,
            content=content,
            category=category,
            author=author,
            readTime=readTime,
            tags=tags,
            image=image
        )
        logger.info("[BLOGS] Added blog id=%s title=%s", bid, title)
        return jsonify({"ok": True, "id": bid}), 201
    except Exception:
        logger.exception("[BLOGS] Add error")
        raise


@app.get("/blogs/list")
def blogs_list():
    limit = min(int(request.args.get("limit", 50)), 500)
    try:
        items = db.list_blogs(limit=limit)
        return jsonify(items), 200
    except Exception:
        logger.warning("[BLOGS] List error")
        raise


@app.get("/blogs/<blog_id>")
def blogs_get(blog_id: str):
    try:
        blog = db.get_blog(blog_id)
        if not blog:
            raise NotFoundError(f"Blog {blog_id} not found")
        return jsonify(blog), 200
    except NotFoundError:
        raise
    except Exception:
        logger.exception("[BLOGS] Get error")
        raise


@app.delete("/blogs/delete/<blog_id>")
def blogs_delete(blog_id: str):
    try:
        ok = db.delete_blog(blog_id)
        logger.info("[BLOGS] Deleted blog id=%s ok=%s", blog_id, ok)
        return jsonify({"ok": ok}), 200
    except Exception:
        logger.exception("[BLOGS] Delete error")
        raise


# ------------------------------------------------------------
# Calculator
# ------------------------------------------------------------
@app.post("/calculator/add")
def calculator_add():
    body = _json_req(required=["food", "value", "kind", "date"])
    food = (body.get("food") or "").strip()
    value = float(body.get("value", 0))
    kind = (body.get("kind") or "entry").strip()
    date_iso = (body.get("date") or "").strip()

    if kind not in ("entry", "bonus"):
        raise BadRequestError("kind must be 'entry' or 'bonus'")

    try:
        rid = db.add_calc_record(
            user=cfg.current_user,
            food=food,
            value=value,
            kind=kind,
            date_iso=date_iso
        )
        logger.info("[CALC] Added record id=%s food=%s value=%s", rid, food, value)
        return jsonify({"ok": True, "id": rid}), 201
    except Exception:
        logger.exception("[CALC] Add error")
        raise


@app.get("/calculator/summary")
def calculator_summary():
    """
    Basic calculator summary endpoint (backward compatible).
    """
    try:
        summary = db.calc_summary(user=cfg.current_user)
        return jsonify(summary), 200
    except Exception:
        logger.warning("[CALC] Summary error")
        raise


# ------------------------------------------------------------
# NEW: Enhanced Calculator Endpoints
# ------------------------------------------------------------
@app.get("/calculator/summary-enhanced")
def calculator_summary_enhanced():
    """
    Enhanced calculator summary with food details and waste stats.
    
    Returns:
    - Basic monthly summary (cost, bonus, net amount, days remaining)
    - Top 5 most expensive food items
    - Total unique items tracked
    - Waste percentage and stats
    - Food-by-food breakdown (fresh vs spoiled)
    """
    try:
        summary = db.calc_summary_enhanced(user=cfg.current_user)
        logger.info("[CALC] Enhanced summary retrieved for user=%s", cfg.current_user)
        return jsonify(summary), 200
    except Exception:
        logger.exception("[CALC] Enhanced summary error")
        raise


@app.get("/calculator/food-breakdown")
def calculator_food_breakdown():
    """
    Get breakdown of detected foods over the last N days.
    
    Query params:
      - days (optional, default=30, max=365)
    
    Returns:
    - List of food items with fresh/spoiled/total counts
    - Overall totals and statistics
    - Period information
    """
    days = min(int(request.args.get("days", 30)), 365)
    try:
        breakdown = db.get_food_waste_breakdown(user=cfg.current_user, days=days)
        logger.info("[CALC] Food breakdown retrieved for user=%s, days=%d", cfg.current_user, days)
        return jsonify(breakdown), 200
    except Exception:
        logger.exception("[CALC] Food breakdown error")
        raise


# ------------------------------------------------------------
# Graceful Shutdown Handling
# ------------------------------------------------------------
_shutdown_requested = threading.Event()

def _graceful_stop(signum, frame):
    logger.info("Received shutdown signal %s, stopping...", signum)
    _shutdown_requested.set()

signal.signal(signal.SIGINT, _graceful_stop)
with suppress(AttributeError):
    signal.signal(signal.SIGTERM, _graceful_stop)


# ------------------------------------------------------------
# Run Server
# ------------------------------------------------------------
def run_server():
    port = int(os.getenv("NOTIFY_PORT", "5002"))
    host = os.getenv("NOTIFY_HOST", "0.0.0.0")
    logger.info("========== Starting FreshiFy Notify Backend ==========")
    logger.info("Serving on http://%s:%s (CORS origins=%s)", host, port, origins)
    use_waitress = os.getenv("USE_WAITRESS", "true").lower() in ("1", "true", "yes")

    if waitress_serve and use_waitress:
        logger.info("Using waitress WSGI server")
        try:
            waitress_serve(app, host=host, port=port, threads=int(os.getenv("WAITRESS_THREADS", "4")))
        except Exception:
            logger.exception("Waitress serve failed; falling back to Flask dev server")
            app.run(host=host, port=port, debug=False)
    else:
        logger.warning("waitress not used — running Flask dev server (not for production)")
        app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    try:
        run_server()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down...")
    finally:
        logger.info("Shutdown complete.")
