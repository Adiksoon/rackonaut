"""Local service authentication and the warehouse calibration draft."""

import json
import os
from collections import deque
from datetime import datetime, timezone
from hashlib import sha256
from hmac import compare_digest
from secrets import token_urlsafe
from threading import Lock
from time import monotonic
from uuid import uuid4


COOKIE = "rackonaut_service"
PRODUCTION = "PRODUCTION"
REQUESTED = "CALIBRATION_REQUESTED"
BLOCKED = "CALIBRATION_BLOCKED"
RECOVERY = "RECOVERY_REQUIRED"
READY = "CALIBRATION_READY"
MAPPING = "MAPPING_ACTIVE"
MAPPED = "MAPPING_COMPLETE"
CHARGING = "CALIBRATION_CHARGING"
FINALIZING = "CALIBRATION_FINALIZING"
TRANSITIONING = {REQUESTED, "STOPPING_INSPECTION", "RETURNING_TO_DOCK", "WAITING_FOR_DOCK",
                 "PREPARING_CALIBRATION"}


class ServiceAccess:
    def __init__(self):
        code = os.environ.get("RACKONAUT_SERVICE_CODE")
        self.code_digest = sha256(code.encode()).digest() if code else None
        try:
            self.ttl = min(3600, max(1, int(os.environ.get("RACKONAUT_SERVICE_SESSION_SECONDS", "900"))))
        except ValueError:
            self.ttl = 900
        self.sessions = {}
        self.failures = deque()
        self.lock = Lock()

    def unlock(self, code):
        if self.code_digest is None:
            return 503, None, "The server has no service access code configured."
        with self.lock:
            now = monotonic()
            while self.failures and now - self.failures[0] >= 60:
                self.failures.popleft()
            if len(self.failures) >= 5:
                return 429, None, "Too many attempts. Try again in a minute."
            if not isinstance(code, str) or not compare_digest(sha256(code.encode()).digest(), self.code_digest):
                self.failures.append(now)
                return 401, None, "Incorrect service code."
            self.sessions = {token: expiry for token, expiry in self.sessions.items() if expiry > now}
            if len(self.sessions) >= 32:
                self.sessions.pop(next(iter(self.sessions)))
            token = token_urlsafe(32)
            self.sessions[token] = now + self.ttl
            return 200, token, None

    def authorized(self, token):
        with self.lock:
            return self.sessions.get(token, 0.) > monotonic()

    def revoke(self, token):
        with self.lock:
            self.sessions.pop(token, None)


class Calibration:
    """Called with the Control dispatch lock held. Startup never queues a return."""

    def __init__(self, path):
        self.path = path
        self.draft = None
        self.reason = ""
        self.cancel_pending = False
        self.owner = None
        self.mapping_run = None
        self.started = 0.
        self.dock_since = None
        self.state = PRODUCTION
        if self.path.exists():
            try:
                self.draft = json.loads(self.path.read_text(encoding="utf-8"))
                self.set_state(BLOCKED, "Control Center restarted. Verify the physical dock before cancelling this draft.")
            except (OSError, ValueError, TypeError, KeyError):
                self.draft = None
                self.state = BLOCKED
                self.reason = "The calibration draft could not be read. Verify the physical dock before clearing it."

    def store(self, draft):
        pending = self.path.with_suffix(".tmp")
        pending.write_text(json.dumps(draft, indent=2) + "\n", encoding="utf-8")
        pending.replace(self.path)

    def start(self, warehouse, owner, now, initialize_locations=None, multi_sortie=False):
        draft = {"calibration_id": f"CAL-{uuid4().hex.upper()}",
                 "started_at": datetime.now(timezone.utc).isoformat(), "status": REQUESTED,
                 "warehouse_name": warehouse, "map_source": "ONBOARD_LIDAR_IMU",
                 "locations": [], "waypoints": [], "map_reference": None}
        if multi_sortie:
            draft.update(multi_sortie=True, sorties=[])
        if initialize_locations:
            identity = draft["calibration_id"]
            initialize_locations(identity)
            draft["locations_reference"] = f"/api/service/mapping/{identity}/locations.json"
        self.store(draft)
        self.draft = draft
        self.state = REQUESTED
        self.reason = "Calibration requested. New inspections are locked."
        self.owner = owner
        self.mapping_run = None
        self.started = now
        self.dock_since = None

    def set_state(self, state, reason):
        self.state, self.reason = state, reason
        if self.draft and self.draft["status"] != state:
            draft = {**self.draft, "status": state}
            try:
                self.store(draft)
            except OSError as error:
                # Keep supervising any flight already in progress even if storage is unavailable.
                self.reason = f"{reason} Draft storage is unavailable: {error.strerror}."
            self.draft = draft

    def clear(self):
        self.path.unlink(missing_ok=True)
        self.draft = self.owner = self.dock_since = None
        self.mapping_run = None
        self.cancel_pending = False
        self.set_state(PRODUCTION, "Returned to production. Start a new inspection when ready.")

    def snapshot(self):
        return {"mode": self.state, "detail": self.reason, "cancel_pending": self.cancel_pending,
                "draft": self.draft}
