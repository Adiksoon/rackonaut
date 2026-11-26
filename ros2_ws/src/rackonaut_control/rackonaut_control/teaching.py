"""Pair an operator's camera capture with the measured pose and store it in the survey."""

import json
import os
import re
from bisect import bisect_left
from collections import deque
from dataclasses import dataclass
from math import hypot, isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from uuid import uuid4

import cv2
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from rackonaut_perception.vision import Inspector, load_markers


SESSION_ID = r"CAL-[A-F0-9]{32}"
CAPTURE_ID = r"CAP-[A-F0-9]{32}"
FRAME = "rackonaut_odom"
SECOND = 1_000_000_000
CAMERA_AGE = .60
POSE_AGE = .35
HOVER_WINDOW = .38
MAX_POSE_INTERVAL = .12
LINEAR_LIMIT = .065
ANGULAR_LIMIT = .10
HOVER_DISPLACEMENT = .035
HOVER_ROTATION = .075
PREVIEW_SECONDS = 60.


@dataclass(frozen=True)
class Pose:
    stamp: int
    received: float
    xyz: tuple
    quaternion: tuple
    linear: float
    angular: float
    sigma: tuple


@dataclass(frozen=True)
class Camera:
    stamp: int
    received: float
    received_utc: str
    frame: str
    jpeg: bytes


@dataclass(frozen=True)
class Preview:
    identity: str
    session: str
    owner: str
    expires: float
    motion: int
    sample: dict
    jpeg: bytes
    marker: str | None

    def public(self):
        return {**self.sample, "capture_id": self.identity, "calibration_id": self.session,
                "suggested_id": self.marker,
                "photo": f"/api/service/teaching/preview/{self.identity}/reference.jpg"}


def stamp_ns(header):
    return header.stamp.sec * SECOND + header.stamp.nanosec


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, prefix=".pending-", delete=False) as stream:
        pending = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def session_path(root, identity, *parts):
    if not isinstance(identity, str) or not re.fullmatch(SESSION_ID, identity):
        raise ValueError("Invalid mapping session ID.")
    root = root.resolve()
    path = root.joinpath(identity, *parts)
    if path.resolve() != path:
        raise ValueError("Invalid mapping session path.")
    return path


def new_manifest(identity):
    return {"schema_version": 1, "calibration_id": identity, "mapping_id": identity, "frame": FRAME,
            "revision": 0, "trajectory": "result.json", "map": "map.ply", "locations": []}


def location_name(request):
    value = request.get("storage_location_id")
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}", value.strip()):
        raise ValueError("Enter a location ID of up to 64 letters, digits, dots, dashes, underscores or colons.")
    return value.strip()


class Teaching:
    """The Control lock protects input buffers only. HTTP threads own detection and disk writes."""

    def __init__(self, data, marker_map):
        self.root = data / "mapping"
        self.marker_map = marker_map
        self.detector = None
        self.operations = Lock()
        self.writing = False
        self.session = None
        self.motion = 0
        self.poses, self.cameras = deque(maxlen=100), deque(maxlen=12)
        self.previews = {}

    def set_session(self, identity):
        if self.session != identity:
            self.session = identity
            self.poses.clear()
            self.cameras.clear()
            self.motion += 1

    def add_pose(self, message, now):
        if not self.session or message.child_frame_id != "rackonaut_base_link":
            return
        header = stamp_ns(message.header)
        if header <= 0 or self.poses and header <= self.poses[-1].stamp:
            return
        p, q, twist = message.pose.pose.position, message.pose.pose.orientation, message.twist.twist
        xyz, orientation = (p.x, p.y, p.z), (q.x, q.y, q.z, q.w)
        linear = hypot(twist.linear.x, twist.linear.y, twist.linear.z)
        angular = hypot(twist.angular.x, twist.angular.y, twist.angular.z)
        sigma = tuple(max(0., message.pose.covariance[i]) ** .5 for i in (0, 7, 14))
        if not all(isfinite(v) for v in (*xyz, *orientation, linear, angular, *sigma)) or abs(hypot(*orientation)-1) > .10:
            return
        if linear > LINEAR_LIMIT or angular > ANGULAR_LIMIT:
            self.motion += 1
        self.poses.append(Pose(header, now, xyz, orientation, linear, angular, sigma))

    def add_camera(self, message, jpeg, now, received_utc):
        if not self.session or not message.header.frame_id:
            return
        header = stamp_ns(message.header)
        if header <= 0 or self.cameras and header <= self.cameras[-1].stamp:
            return
        self.cameras.append(Camera(header, now, received_utc, message.header.frame_id, jpeg))

    def inputs(self, now):
        if not self.cameras or now-self.cameras[-1].received > CAMERA_AGE:
            raise RuntimeError("Wait for a fresh onboard camera image.")
        if not self.poses or now-self.poses[-1].received > POSE_AGE:
            raise RuntimeError("Wait for a fresh SLAM pose.")
        return tuple(self.poses), tuple(self.cameras)

    @staticmethod
    def pair(poses, cameras, now):
        stamps = [p.stamp for p in poses]
        latest = poses[-1]
        for camera in reversed(cameras):
            if now-camera.received > CAMERA_AGE:
                break
            upper = bisect_left(stamps, camera.stamp)
            if not 0 < upper < len(poses):
                continue
            before, after = poses[upper-1], poses[upper]
            if after.stamp-before.stamp > MAX_POSE_INTERVAL * SECOND:
                continue
            start = bisect_left(stamps, camera.stamp-round(HOVER_WINDOW*SECOND))
            if not start:
                continue
            history = poses[start-1:]
            if any(b.stamp-a.stamp > MAX_POSE_INTERVAL*SECOND for a, b in zip(history, history[1:])):
                continue
            if any(p.linear > LINEAR_LIMIT or p.angular > ANGULAR_LIMIT
                   or np.linalg.norm(np.subtract(p.xyz, latest.xyz)) > HOVER_DISPLACEMENT for p in history):
                continue
            attitudes = Rotation.from_quat([p.quaternion for p in history])
            if ((attitudes[-1].inv()*attitudes).magnitude() > HOVER_ROTATION).any():
                continue
            fraction = (camera.stamp-before.stamp)/(after.stamp-before.stamp)
            position = (1-fraction)*np.asarray(before.xyz) + fraction*np.asarray(after.xyz)
            attitude = Slerp([0., 1.], Rotation.from_quat([before.quaternion, after.quaternion]))(fraction)
            sec, nanosec = divmod(camera.stamp, SECOND)
            return camera, {
                "frame": FRAME, "camera_frame": camera.frame, "camera_stamp": {"sec": sec, "nanosec": nanosec},
                "received_at_utc": camera.received_utc, "position_m": position.tolist(),
                "orientation_xyzw": attitude.as_quat().tolist(),
                "camera_direction": attitude.apply([1., 0., 0.]).tolist(),
                "sync": {"before_ms": (camera.stamp-before.stamp)/1e6,
                         "after_ms": (after.stamp-camera.stamp)/1e6},
                "position_sigma_m": np.maximum(before.sigma, after.sigma).tolist(),
            }
        raise RuntimeError("Hold the drone still until the camera and SLAM pose are synchronized.")

    def manifest(self, session):
        path = session_path(self.root, session, "locations.json")
        if not path.exists():
            return new_manifest(session)
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("mapping_id") != session or result.get("calibration_id") != session:
            raise ValueError("The teaching manifest belongs to a different mapping session.")
        return result

    def create(self, session):
        self.write_manifest(session, new_manifest(session))

    def write_manifest(self, session, manifest):
        atomic_write(session_path(self.root, session, "locations.json"),
                     (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode())

    def preview(self, session, owner, motion, quality, camera, sample, now):
        if self.detector is None:
            self.detector = Inspector(*load_markers(self.marker_map))
        pixels = cv2.imdecode(np.frombuffer(camera.jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        try:
            tags = self.detector.detect(pixels) if pixels is not None else []
        except cv2.error:
            tags = []
        locations = {tag.name for tag in tags if tag.kind == "slot"}
        marker = next(iter(locations)) if len(locations) == 1 else None
        identity = f"CAP-{uuid4().hex.upper()}"
        self.previews = {key: value for key, value in self.previews.items() if value.expires > now}
        if len(self.previews) >= 16:
            self.previews.pop(next(iter(self.previews)))
        result = Preview(identity, session, owner, now+PREVIEW_SECONDS, motion,
                         {**sample, "localization": quality}, camera.jpeg, marker)
        self.previews[identity] = result
        return result.public()

    def get_preview(self, identity, owner, now):
        preview = self.previews.get(identity) if isinstance(identity, str) else None
        if preview is None or preview.owner != owner or preview.expires <= now:
            raise FileNotFoundError("Capture preview expired. Take a new photo.")
        return preview

    @staticmethod
    def match_revision(request, manifest):
        if type(request.get("revision")) is not int or request["revision"] != manifest["revision"]:
            raise RuntimeError("Registered locations changed. Refresh the list before editing.")

    def edit(self, action, session, request, capture=None):
        manifest = self.manifest(session)
        self.match_revision(request, manifest)
        records = manifest["locations"]
        record_id = request.get("record_id")
        target = next((record for record in records if record["record_id"] == record_id), None)
        if record_id is not None and target is None:
            raise RuntimeError("The selected record is no longer in the calibration draft.")
        if action == "delete":
            if target is None or request.get("confirm") is not True:
                raise ValueError("Confirm removal of the selected draft location.")
            records.remove(target)
        else:
            name = location_name(request)
            duplicate = next((record for record in records if record["storage_location_id"].casefold() == name.casefold()), None)
            if duplicate is not None and duplicate is not target:
                raise RuntimeError("This location ID already exists. Select it and confirm an update.")
            if action == "rename":
                if target is None:
                    raise ValueError("Select a location to rename.")
                if target["storage_location_id"] != name:
                    target["id_source"] = "operator"
                target["storage_location_id"] = name
            else:
                if target is not None and request.get("confirm") is not True:
                    raise ValueError("Confirm replacement of the selected location and photo.")
                description = request.get("description", "")
                if not isinstance(description, str) or len(description) > 500:
                    raise ValueError("Use at most 500 characters for the operator description.")
                reference = f"locations/{capture.identity}/reference.jpg"
                atomic_write(session_path(self.root, session, *reference.split("/")), capture.jpeg)
                record = {**capture.sample, "record_id": record_id or f"LOC-{uuid4().hex.upper()}",
                          "storage_location_id": name, "calibration_id": session, "mapping_id": session,
                          "id_source": "aruco" if name == capture.marker else "operator",
                          "suggested_id": capture.marker, "description": description.strip(),
                          "status": "approved", "reference_image": reference}
                if target is None:
                    records.append(record)
                else:
                    records[records.index(target)] = record
                # A failed manifest write leaves the earlier version and image valid.
        manifest["revision"] += 1
        self.write_manifest(session, manifest)
        if capture is not None:
            self.previews.pop(capture.identity, None)
        return manifest

    def photo(self, session, capture):
        reference = f"locations/{capture}/reference.jpg"
        if not re.fullmatch(CAPTURE_ID, capture) or not any(
                record["reference_image"] == reference for record in self.manifest(session)["locations"]):
            raise FileNotFoundError
        return session_path(self.root, session, *reference.split("/")).read_bytes()
