"""Stream measured flight poses to a bounded, append-only calibration journal."""

import json
import os
from datetime import datetime, timezone
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import monotonic

from rackonaut_localization.warehouse_config import trajectory_file
from .teaching import FRAME, SECOND, session_path


FORMAT = 1
INTERVAL_NS = SECOND // 5
MAX_SAMPLES = 12000


class RouteRecorder:
    def __init__(self, root, session, run, energy_model, takeoff_dock, number=None):
        self.identity = session
        self.run = run
        self.number = number
        self.header = {"kind": "header", "schema_version": FORMAT, "mapping_id": session,
                       "inspection_id": run, "frame": FRAME, "source": "slam",
                       "sample_interval_ns": INTERVAL_NS, "sample_limit": MAX_SAMPLES,
                       "energy_model": dict(energy_model), "takeoff_dock": dict(takeoff_dock)}
        if number is not None:
            self.header["sortie"] = number
        self.queue = Queue(maxsize=512)
        self.done = Event()
        self.ending = None
        self.error = None
        self.last_stamp = None
        self.count = 0
        self.dropped = 0
        self.worker = Thread(target=self.write, args=(root,), daemon=True, name="calibration-trajectory")
        self.worker.start()

    def add(self, pose, sample, force=False):
        if self.ending is not None or self.done.is_set():
            return
        if self.last_stamp is not None:
            delta = pose.stamp - self.last_stamp
            if delta <= 0 or delta < INTERVAL_NS and not force:
                return
        if self.count >= MAX_SAMPLES:
            self.dropped += 1
            return
        sec, nanos = divmod(pose.stamp, SECOND)
        row = {**sample, "kind": "pose", "schema_version": FORMAT, "mapping_id": self.identity,
               "frame": FRAME, "index": self.count, "stamp": {"sec": sec, "nanosec": nanos},
               "position_m": pose.xyz, "orientation_xyzw": pose.quaternion,
               "speed_mps": pose.linear, "angular_speed_radps": pose.angular,
               "position_sigma_m": pose.sigma}
        try:
            self.queue.put_nowait(row)
        except Full:
            self.dropped += 1
            return
        self.count += 1
        self.last_stamp = pose.stamp

    def finish(self, stage, contact, energy):
        if self.ending is None:
            self.ending = {"kind": "end", "schema_version": FORMAT, "mapping_id": self.identity,
                           "frame": FRAME, "stage": stage,
                           "physical_dock": bool(contact), "complete": stage == "COMPLETE" and bool(contact) and not self.dropped,
                           "sample_count": self.count, "dropped_samples": self.dropped,
                           "energy": energy, "written_at_utc": datetime.now(timezone.utc).isoformat()}

    def write(self, root):
        try:
            path = session_path(root, self.identity, trajectory_file(self.number))
            with path.open("x", encoding="utf-8") as out:
                def append(row):
                    out.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")

                append(self.header)
                next_flush = monotonic()
                while True:
                    try:
                        append(self.queue.get(timeout=.15))
                    except Empty:
                        if self.ending is not None and self.queue.empty():
                            append(self.ending)
                            out.flush()
                            os.fsync(out.fileno())
                            return
                    if monotonic() >= next_flush:
                        out.flush()
                        next_flush = monotonic() + .8
        except (OSError, ValueError) as error:
            self.error = str(error)
        finally:
            self.done.set()
