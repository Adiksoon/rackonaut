"""Deduplicate quality captures and store them alongside their inventory IDs."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import cv2
import numpy as np

from .quality import QualityVerdict


class QualityEvidence:
    def __init__(self, directory, inspection_id, per_observation=False):
        self.directory = Path(directory).expanduser() / inspection_id
        self.frames = {}
        self.saved = set()
        self.last_frame = None
        self.retry_at = 0.
        self.per_observation = per_observation

    def ready(self, verdicts, findings, inventory, now):
        if self.last_frame is not None and now - self.last_frame > .6:
            self.frames.clear()
        self.last_frame = now
        frames, ready = {}, []
        for reading in findings:
            slot, classification = reading.slot.name, reading.classification
            if classification.occupancy != "occupied":
                continue
            verdict = verdicts[slot]
            key = (slot, classification.pallet_id, verdict.status)
            frames[key] = self.frames.get(key, 0) + 1
            observation = inventory.get(slot)
            capture_key = (*key, observation["observation_id"]) if self.per_observation and observation else key
            # Keep uncertain views in the preview. A capture represents a
            # stable verdict backed by a matching local inventory observation.
            if (verdict.status != "UNCERTAIN" and frames[key] >= 7 and capture_key not in self.saved
                    and now >= self.retry_at and observation and observation["occupancy"] == "occupied"
                    and observation["pallet_id"] == classification.pallet_id):
                ready.append((capture_key, verdict, observation))
        self.frames = frames
        return ready

    def damage_count(self, ready=()):
        keys = self.saved | {key for key, _, _ in ready}
        return len({key[:2] for key in keys if key[2] == "DAMAGED"})

    def save_observation(self, observation, image, annotated, captured, header):
        key = (observation["slot_id"], observation["pallet_id"], "CAPTURED", observation["observation_id"])
        verdict = QualityVerdict("CAPTURED", "Camera frame used for the inventory observation.")
        return self.save((key, verdict, observation), image, annotated, captured, header)

    def save(self, item, image, annotated, captured, header):
        key, verdict, observation = item
        quality_id = f"Q-{uuid4().hex.upper()}"
        report = {
            "quality_schema_version": "0.1",
            "quality_id": quality_id,
            "inspection_id": observation["inspection_id"],
            "observation_id": observation["observation_id"],
            "observation_timestamp": observation["timestamp"],
            "slot_id": key[0],
            "pallet_id": key[1],
            "status": verdict.status,
            "reason": verdict.reason,
            "timestamp": captured.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "camera": {
                "frame_id": header.frame_id,
                "stamp": {"sec": header.stamp.sec, "nanosec": header.stamp.nanosec},
                "width": image.shape[1],
                "height": image.shape[0],
            },
            "defect_polygon_px": np.rint(verdict.defect).astype(int).tolist() if verdict.defect is not None else None,
            "images": {"original": "camera.png", "annotated": "annotated.png"},
        }
        if verdict.status == "CAPTURED":
            report["occupancy"] = observation["occupancy"]
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / quality_id
        with TemporaryDirectory(dir=self.directory, prefix=".capture-") as temporary:
            output = Path(temporary)
            if not cv2.imwrite(str(output / "camera.png"), image):
                raise OSError("Could not write native camera PNG")
            if not cv2.imwrite(str(output / "annotated.png"), annotated):
                raise OSError("Could not write annotated PNG")
            (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            output.rename(destination)
        self.saved.add(key)
        return destination
