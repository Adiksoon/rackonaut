"""Consecutive-frame gate and the v1 observation transport."""

import json
from datetime import datetime, timezone
from http.client import HTTPException
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


class StableReadings:
    def __init__(self, stable_frames=4, uncertain_frames=8):
        self.stable_frames = stable_frames
        self.uncertain_frames = uncertain_frames
        self.tracks = {}
        self.recorded = {}
        self.last_frame = None

    def update(self, readings, now):
        if self.last_frame is not None and now - self.last_frame > .6:
            self.tracks.clear()
        self.last_frame = now
        tracks = {}
        ready = []
        for reading in readings:
            slot, classification = reading.slot.name, reading.classification
            uncertain = classification.occupancy == "uncertain"
            if uncertain and reading.reason not in (
                "Shelf edge unclear", "Shelf partly obscured", "Pallet association ambiguous"
            ):
                continue
            if uncertain and slot in self.recorded:
                continue
            previous, count = self.tracks.get(slot, (None, 0))
            count = count + 1 if previous == classification else 1
            tracks[slot] = (classification, count)
            minimum = self.uncertain_frames if uncertain else self.stable_frames
            if count >= minimum and self.recorded.get(slot) != classification:
                ready.append(reading)
        self.tracks = tracks
        return ready

    def record(self, reading):
        self.recorded[reading.slot.name] = reading.classification

    def rearm(self):
        self.tracks.clear()
        self.recorded.clear()


def observation(inspection_id, reading, timestamp):
    classification = reading.classification
    return {
        "schema_version": "1.0",
        "inspection_id": inspection_id,
        "observation_id": f"OBS-{uuid4().hex.upper()}",
        "slot_id": reading.slot.name,
        "pallet_id": classification.pallet_id,
        "occupancy": classification.occupancy,
        "label_status": classification.label_status,
        "timestamp": timestamp.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    }


def post_observation(backend_url, event, timeout=1.0):
    request = Request(
        f"{backend_url.rstrip('/')}/api/observations",
        data=json.dumps(event, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    for delay in (0, .25, .65):
        if delay:
            sleep(delay)
        try:
            with urlopen(request, timeout=timeout) as result:
                if result.status in (200, 201):
                    return True, f"HTTP {result.status}"
                return False, f"Unexpected HTTP {result.status}"
        except HTTPError as error:
            status = error.code
            error.close()
            if status < 500 and status not in (408, 429):
                return False, f"HTTP {status}"
            reason = f"HTTP {status}"
        except (URLError, OSError, HTTPException):
            reason = "Backend unavailable"
    return False, reason
