from __future__ import annotations
import os
import time
import logging
from dotenv import load_dotenv
load_dotenv()

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.errors import CollectionInvalid, ServerSelectionTimeoutError
from bson import ObjectId

# -------------------- Logging --------------------
LOG_DIR = os.path.join(os.getcwd(), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "db.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# also log to console for developer convenience
_console = logging.StreamHandler()
_console.setLevel(logging.INFO)
_console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logging.getLogger().addHandler(_console)


@dataclass(frozen=True)
class FreshifyConfig:
    mongo_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name: str = os.getenv("DB_NAME", "DB_FreshiFy")
    ttl_seconds: int = int(os.getenv("TTL_SECONDS", str(8 * 24 * 60 * 60)))  # default 8 days
    current_user: str = os.getenv("CURRENT_USER", "chamika")
    ts_time_field: str = "createdAt"
    ts_meta_field: str = "user"
    ts_granularity: str = "seconds"


def _oid(s: str) -> Optional[ObjectId]:
    try:
        return ObjectId(s)
    except Exception:
        return None


class FreshiFyDB:
    """
    MongoDB wrapper used by the FreshiFy backend services.
    Provides collections and convenient helper methods used by the Flask endpoints.
    """

    def __init__(self, cfg: Optional[FreshifyConfig] = None):
        self.cfg = cfg or FreshifyConfig()

        # these will be set after connection
        self.client: Optional[MongoClient] = None
        self.db = None

        # collection handles
        self.sensors: Optional[Collection] = None
        self.images: Optional[Collection] = None
        self.notifications: Optional[Collection] = None
        self.calendar_events: Optional[Collection] = None
        self.blogs: Optional[Collection] = None
        self.calc_records: Optional[Collection] = None
        self.thoughts: Optional[Collection] = None  # NEW: thoughts collection

        # connect on init
        self._connect_with_retry(max_retries=5, wait_seconds=3)

        # if connected, ensure collections & indexes and cache handles
        if self.db is not None:
            try:
                self._ensure_collections_and_indexes()
                self._cache_collections()
                logging.info(f"[DB] Connected to {self.cfg.mongo_uri}, DB={self.cfg.db_name}")
            except Exception as e:
                logging.error("[DB] Error during collection/index setup: %s", e)

    # ---------------- connection ----------------
    def _connect_with_retry(self, max_retries: int = 5, wait_seconds: int = 3) -> None:
        """
        Create a MongoClient and set self.db. Retries a few times on failure.
        """
        for attempt in range(1, max_retries + 1):
            try:
                self.client = MongoClient(
                    self.cfg.mongo_uri,
                    tz_aware=True,
                    serverSelectionTimeoutMS=8000,
                )
                # quick ping to validate connection
                self.client.admin.command("ping")
                self.db = self.client[self.cfg.db_name]
                logging.info(f"[DB] Connected on attempt {attempt}")
                return
            except ServerSelectionTimeoutError as se:
                logging.warning(f"[DB] Retry {attempt}/{max_retries}: MongoDB unreachable ({se})")
                time.sleep(wait_seconds)
            except Exception as e:
                logging.warning(f"[DB] Retry {attempt}/{max_retries}: unexpected error ({e})")
                time.sleep(wait_seconds)

        # if we reach here, connection failed
        logging.error("[DB] Connection failed after retries.")
        # keep client/db as None to allow graceful degradation in the rest of the code
        self.client = None
        self.db = None

    def _cache_collections(self) -> None:
        if self.db is None:
            return
        self.sensors = self.db["sensors_data"]
        self.images = self.db["images_data"]
        self.notifications = self.db["notifications"]
        self.calendar_events = self.db["calendar_events"]
        self.blogs = self.db["blogs"]
        self.calc_records = self.db["calc_records"]
        self.thoughts = self.db["thoughts"]  # NEW

    # ---------------- setup ----------------
    def _ensure_collections_and_indexes(self) -> None:
        if self.db is None:
            logging.warning("[DB] _ensure_collections_and_indexes called but no database connection.")
            return

        names = set(self.db.list_collection_names())

        def ensure(col: str) -> None:
            nonlocal names
            if col not in names:
                try:
                    self.db.create_collection(col)
                    logging.info(f"[DB] Created collection: {col}")
                except CollectionInvalid:
                    logging.debug(f"[DB] Collection {col} already exists (race).")
                names.add(col)

        # create collections if missing (added 'thoughts')
        for col in [
            "sensors_data",
            "images_data",
            "notifications",
            "calendar_events",
            "blogs",
            "calc_records",
            "thoughts",  # NEW
        ]:
            ensure(col)

        # common useful indexes
        try:
            self.db["sensors_data"].create_index([("user", ASCENDING), ("createdAt", DESCENDING)])
            self.db["images_data"].create_index([("user", ASCENDING), ("createdAt", DESCENDING)])
            self.db["notifications"].create_index([("user", ASCENDING), ("createdAt", DESCENDING)])
            self.db["calendar_events"].create_index([("user", ASCENDING), ("start", DESCENDING)])
            self.db["blogs"].create_index([("user", ASCENDING), ("createdAt", DESCENDING)])
            # calculator indexes
            self.db["calc_records"].create_index([("user", ASCENDING), ("date", DESCENDING)])
            self.db["calc_records"].create_index([("kind", ASCENDING)])
            # thoughts index (new)
            self.db["thoughts"].create_index([("user", ASCENDING), ("createdAt", DESCENDING)])
        except Exception as e:
            logging.warning("[DB] Warning while creating basic indexes: %s", e)

        # telemetry-specific TTL (only for telemetry collections)
        try:
            self.db["sensors_data"].create_index(
                [("createdAt", ASCENDING)],
                expireAfterSeconds=self.cfg.ttl_seconds,
                name="ttl_createdAt_sensors",
            )
            self.db["images_data"].create_index(
                [("createdAt", ASCENDING)],
                expireAfterSeconds=self.cfg.ttl_seconds,
                name="ttl_createdAt_images",
            )
        except Exception as e:
            logging.warning("[DB] TTL index creation warning: %s", e)

        # extra helpful indexes
        try:
            self.db["sensors_data"].create_index([("status", ASCENDING)])
            self.db["images_data"].create_index([("status", ASCENDING)])
            self.db["blogs"].create_index([("title", ASCENDING)])
            self.db["blogs"].create_index([("category", ASCENDING)])
            self.db["blogs"].create_index([("tags", ASCENDING)])
            # optional: text index on thoughts text for later search (safe - wrapped)
            try:
                # create a simple text index on 'text' field to allow text searches in the future
                self.db["thoughts"].create_index([("text", "text")], name="text_idx_thoughts")
            except Exception:
                # ignore text index errors (older mongo or perms)
                logging.debug("[DB] text index for thoughts could not be created or already exists.")
        except Exception as e:
            logging.debug("[DB] Extra index creation issue: %s", e)

    # ---------------- inserts ----------------
    def insert_sensor_result(
        self,
        *,
        user: Optional[str],
        nh3: float,
        rgb: Tuple[int, int, int],
        c: int = 0,
        food: Optional[str] = None,
        status: Optional[str] = None,
        source: str = "live",
        device_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> Optional[str]:
        if self.sensors is None:
            logging.warning("[DB] insert_sensor_result: sensors collection missing.")
            return None
        doc = {
            "user": user or self.cfg.current_user,
            "deviceId": device_id,
            "nh3": float(nh3),
            "rgb": [int(x) for x in rgb],
            "c": int(c),
            "food": food,
            "status": status,
            "source": source,
            "createdAt": created_at or datetime.now(timezone.utc),
        }
        try:
            res = self.sensors.insert_one(doc)
            return str(res.inserted_id)
        except Exception as e:
            logging.error("[DB] insert_sensor_result failed: %s", e)
            return None

    def insert_image_result(
        self,
        *,
        user: Optional[str],
        food: str,
        status: str,
        file_name: str,
        source: str,
        created_at: Optional[datetime] = None,
    ) -> Optional[str]:
        if self.images is None:
            logging.warning("[DB] insert_image_result: images collection missing.")
            return None
        doc = {
            "user": user or self.cfg.current_user,
            "food": food,
            "status": status,
            "file": file_name,
            "source": source,
            "createdAt": created_at or datetime.now(timezone.utc),
        }
        try:
            res = self.images.insert_one(doc)
            return str(res.inserted_id)
        except Exception as e:
            logging.error("[DB] insert_image_result failed: %s", e)
            return None

    def insert_notification(self, message: str) -> Optional[str]:
        if self.notifications is None:
            logging.warning("[DB] insert_notification: notifications collection missing.")
            return None
        doc = {
            "user": self.cfg.current_user,
            "message": message,
            "createdAt": datetime.now(timezone.utc),
        }
        try:
            res = self.notifications.insert_one(doc)
            return str(res.inserted_id)
        except Exception as e:
            logging.error("[DB] insert_notification failed: %s", e)
            return None

    # ---------- thoughts (new) ----------
    def add_thought(
        self,
        *,
        text: str,
        user: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> Optional[str]:
        """
        Inserts a short user thought/note.
        """
        if self.thoughts is None:
            logging.warning("[DB] add_thought: thoughts collection missing.")
            return None
        doc = {
            "user": user or self.cfg.current_user,
            "text": text,
            "createdAt": created_at or datetime.now(timezone.utc),
        }
        try:
            res = self.thoughts.insert_one(doc)
            return str(res.inserted_id)
        except Exception as e:
            logging.error("[DB] add_thought failed: %s", e)
            return None

    def list_thoughts(self, user: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Returns recent thoughts for a user ordered by createdAt descending.
        """
        if self.thoughts is None or self.db is None:
            return []
        out: List[Dict[str, Any]] = []
        try:
            q = {"user": user or self.cfg.current_user}
            cur = self.thoughts.find(q).sort("createdAt", DESCENDING).limit(limit)
            for d in cur:
                ca = d.get("createdAt")
                out.append({
                    "id": str(d.get("_id")),
                    "text": d.get("text"),
                    "createdAt": ca.isoformat() if hasattr(ca, "isoformat") else ca,
                })
            return out
        except Exception as e:
            logging.warning("[DB] list_thoughts error: %s", e)
            return []

    # ---------- reads / helpers for front-end ----------
    def get_stats(self, user: str) -> Dict[str, int]:
        if self.db is None:
            return {"totalScans": 0, "freshCount": 0, "spoiledCount": 0}
        try:
            fresh = 0
            spoiled = 0
            if self.db is not None:
                fresh = (
                    self.db["sensors_data"].count_documents({"user": user, "status": "Fresh"})
                    + self.db["images_data"].count_documents({"user": user, "status": "Fresh"})
                )
                spoiled = (
                    self.db["sensors_data"].count_documents({"user": user, "status": "Spoiled"})
                    + self.db["images_data"].count_documents({"user": user, "status": "Spoiled"})
                )
            total = fresh + spoiled
            return {"totalScans": total, "freshCount": fresh, "spoiledCount": spoiled}
        except Exception as e:
            logging.warning("[DB] get_stats error: %s", e)
            return {"totalScans": 0, "freshCount": 0, "spoiledCount": 0}

    def get_last_sensor(self, user: str):
        if self.sensors is None:
            return None
        try:
            return self.sensors.find_one({"user": user}, sort=[("createdAt", DESCENDING)])
        except Exception:
            return None

    def get_last_image(self, user: str):
        if self.images is None:
            return None
        try:
            return self.images.find_one({"user": user}, sort=[("createdAt", DESCENDING)])
        except Exception:
            return None

    def get_live_nh3(self, user: str):
        if self.sensors is None:
            return None
        try:
            return self.sensors.find_one({"user": user}, sort=[("createdAt", DESCENDING)], projection={"nh3": 1, "createdAt": 1})
        except Exception:
            return None

    def get_history(self, user: str, limit: int = 30) -> List[Dict[str, Any]]:
        if self.db is None:
            return []
        items: List[Dict[str, Any]] = []
        try:
            sens = list(self.db["sensors_data"].find({"user": user}).sort("createdAt", DESCENDING).limit(limit))
            imgs = list(self.db["images_data"].find({"user": user}).sort("createdAt", DESCENDING).limit(limit))

            for d in sens:
                ca = d.get("createdAt")
                items.append({
                    "id": str(d.get("_id")),
                    "type": "sensor",
                    "food": d.get("food") or "General_Food",
                    "status": d.get("status") or "-",
                    "nh3": d.get("nh3"),
                    "rgb": d.get("rgb"),
                    "createdAt": ca.isoformat() if hasattr(ca, "isoformat") else ca,
                })
            for d in imgs:
                ca = d.get("createdAt")
                items.append({
                    "id": str(d.get("_id")),
                    "type": "image",
                    "food": d.get("food"),
                    "status": d.get("status"),
                    "createdAt": ca.isoformat() if hasattr(ca, "isoformat") else ca,
                })

            items.sort(key=lambda x: x.get("createdAt") or "", reverse=True)
            return items[:limit]
        except Exception as e:
            logging.warning("[DB] get_history error: %s", e)
            return []

    # ---------- calendar ----------
    def add_calendar_event(
        self,
        *,
        title: str,
        start: str,
        end: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[str]:
        if self.calendar_events is None:
            logging.warning("[DB] add_calendar_event: collection missing.")
            return None
        doc = {
            "user": self.cfg.current_user,
            "title": title,
            "start": start,
            "end": end,
            "notes": notes,
            "createdAt": datetime.now(timezone.utc),
        }
        try:
            res = self.calendar_events.insert_one(doc)
            return str(res.inserted_id)
        except Exception as e:
            logging.error("[DB] add_calendar_event failed: %s", e)
            return None

    def list_calendar_events(
        self,
        *,
        start_from: Optional[str] = None,
        end_to: Optional[str] = None,
        limit: int = 100,
    ):
        if self.calendar_events is None:
            return []
        q: Dict[str, Any] = {"user": self.cfg.current_user}
        if start_from or end_to:
            rng: Dict[str, Any] = {}
            if start_from:
                rng["$gte"] = start_from
            if end_to:
                rng["$lte"] = end_to
            q["start"] = rng
        try:
            cur = self.calendar_events.find(q).sort("start", DESCENDING).limit(limit)
            out: List[Dict[str, Any]] = []
            for d in cur:
                out.append({
                    "id": str(d["_id"]),
                    "title": d.get("title"),
                    "start": d.get("start"),
                    "end": d.get("end"),
                    "notes": d.get("notes"),
                    "createdAt": d.get("createdAt"),
                })
            return out
        except Exception as e:
            logging.warning("[DB] list_calendar_events error: %s", e)
            return []

    def delete_calendar_event(self, event_id: str) -> bool:
        if self.calendar_events is None:
            return False
        oid = _oid(event_id)
        if oid is None:
            return False
        try:
            res = self.calendar_events.delete_one({"_id": oid, "user": self.cfg.current_user})
            return res.deleted_count > 0
        except Exception as e:
            logging.warning("[DB] delete_calendar_event error: %s", e)
            return False

    # ---------- blogs ----------
    def add_blog(
        self,
        *,
        title: str,
        content: str,
        category: Optional[str] = None,
        author: Optional[str] = None,
        readTime: Optional[str] = None,
        tags: Optional[List[str]] = None,
        image: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> Optional[str]:
        if self.blogs is None:
            logging.warning("[DB] add_blog: blogs collection missing.")
            return None
        doc = {
            "user": self.cfg.current_user,
            "title": title,
            "content": content,
            "category": category or "General",
            "author": author or "Unknown",
            "readTime": readTime or "—",
            "tags": tags or [],
            "image": image or "",
            "createdAt": created_at or datetime.now(timezone.utc),
        }
        try:
            res = self.blogs.insert_one(doc)
            return str(res.inserted_id)
        except Exception as e:
            logging.error("[DB] add_blog failed: %s", e)
            return None

    def list_blogs(self, *, limit: int = 50) -> List[Dict[str, Any]]:
        if self.blogs is None:
            return []
        try:
            cur = (
                self.blogs.find({"$or": [{"user": self.cfg.current_user}, {"user": {"$exists": False}}]})
                .sort("createdAt", DESCENDING)
                .limit(limit)
            )
            out: List[Dict[str, Any]] = []
            for d in cur:
                ca = d.get("createdAt")
                out.append({
                    "_id": str(d.get("_id")),
                    "title": d.get("title"),
                    "content": d.get("content"),
                    "category": d.get("category"),
                    "author": d.get("author"),
                    "readTime": d.get("readTime"),
                    "tags": d.get("tags") or [],
                    "image": d.get("image") or "",
                    "createdAt": ca.isoformat() if hasattr(ca, "isoformat") else ca,
                })
            return out
        except Exception as e:
            logging.warning("[DB] list_blogs error: %s", e)
            return []

    def get_blog(self, blog_id: str) -> Optional[Dict[str, Any]]:
        if self.blogs is None:
            return None
        oid = _oid(blog_id)
        if oid is None:
            return None
        try:
            d = self.blogs.find_one({"_id": oid})
            if d is None:
                return None
            ca = d.get("createdAt")
            return {
                "_id": str(d.get("_id")),
                "title": d.get("title"),
                "content": d.get("content"),
                "category": d.get("category"),
                "author": d.get("author"),
                "readTime": d.get("readTime"),
                "tags": d.get("tags") or [],
                "image": d.get("image") or "",
                "createdAt": ca.isoformat() if hasattr(ca, "isoformat") else ca,
            }
        except Exception as e:
            logging.warning("[DB] get_blog error: %s", e)
            return None

    def delete_blog(self, blog_id: str) -> bool:
        if self.blogs is None:
            return False
        oid = _oid(blog_id)
        if oid is None:
            return False
        try:
            res = self.blogs.delete_one({"_id": oid})
            return res.deleted_count > 0
        except Exception as e:
            logging.warning("[DB] delete_blog error: %s", e)
            return False

    # ---------- calculator (records + summary) ----------
    def add_calc_record(
        self,
        *,
        user: str,
        food: str,
        value: float,
        kind: str,  # "entry" | "bonus"
        date_iso: str,
    ) -> Optional[str]:
        if self.calc_records is None:
            logging.warning("[DB] add_calc_record: calc_records missing.")
            return None
        try:
            when = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
        except Exception:
            when = datetime.now(timezone.utc)
        doc = {
            "user": user or self.cfg.current_user,
            "food": food,
            "value": float(value),
            "kind": kind if kind in ("entry", "bonus") else "entry",
            "date": when,
            "createdAt": datetime.now(timezone.utc),
        }
        try:
            res = self.calc_records.insert_one(doc)
            return str(res.inserted_id)
        except Exception as e:
            logging.error("[DB] add_calc_record failed: %s", e)
            return None

    def calc_summary(self, *, user: str) -> Dict[str, Any]:
        """
        Returns a month-to-date summary for the given user.
        """
        if self.calc_records is None:
            return {
                "latestFood": None,
                "currentTotalCost": 0,
                "totalBonus": 0,
                "netAmount": 0,
                "lastUpdatedDate": None,
                "monthStartDate": None,
                "billPrintedDate": None,
                "remainingDays": None,
            }

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # first day of next month
        if month_start.month == 12:
            next_month_start = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month_start = month_start.replace(month=month_start.month + 1)
        # month_end = next_month_start - timedelta(seconds=1)  # not used but kept for clarity

        try:
            cur = self.calc_records.find(
                {"user": user, "date": {"$gte": month_start, "$lt": next_month_start}}
            ).sort("date", DESCENDING)
        except Exception as e:
            logging.warning("[DB] calc_summary find error: %s", e)
            return {
                "latestFood": None,
                "currentTotalCost": 0,
                "totalBonus": 0,
                "netAmount": 0,
                "lastUpdatedDate": None,
                "monthStartDate": month_start.isoformat(),
                "billPrintedDate": None,
                "remainingDays": (next_month_start.date() - now.date()).days,
            }

        entry_total = 0.0
        bonus_total = 0.0
        latest_food = None
        last_updated = None

        for i, d in enumerate(cur):
            v = float(d.get("value", 0) or 0)
            if d.get("kind") == "bonus":
                bonus_total += v
            else:
                entry_total += v
            if i == 0:
                latest_food = d.get("food")
                when = d.get("date") or d.get("createdAt")
                last_updated = when.isoformat() if hasattr(when, "isoformat") else when

        net = entry_total + bonus_total
        remaining_days = (next_month_start.date() - now.date()).days

        return {
            "latestFood": latest_food,
            "currentTotalCost": round(entry_total, 2),
            "totalBonus": round(bonus_total, 2),
            "netAmount": round(net, 2),
            "lastUpdatedDate": last_updated,
            "monthStartDate": month_start.isoformat(),
            "billPrintedDate": None,
            "remainingDays": remaining_days,
        }
