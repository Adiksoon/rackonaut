"""Read-only transport for the localizer's packed XYZ measurement cloud."""

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from uuid import uuid4

import numpy as np
from sensor_msgs.msg import PointField


MAP_TOPIC = "/rackonaut/localization/measured_map"
ESTIMATE_TOPIC = "/rackonaut/localization/estimate"
FRAME = "rackonaut_odom"
VOXEL_METRES = .16
DETAIL = {"low": 2200, "balanced": 16000, "high": 80000}


def packed_map(cloud):
    fields = {field.name: (field.offset, field.datatype, field.count) for field in cloud.fields}
    if (cloud.header.frame_id != FRAME or cloud.height != 1 or not 0 < cloud.width <= DETAIL["high"]
            or cloud.is_bigendian or cloud.point_step != 12 or cloud.row_step != cloud.width * 12
            or len(cloud.data) != cloud.row_step
            or any(fields.get(name) != (index * 4, PointField.FLOAT32, 1) for index, name in enumerate("xyz"))):
        return None
    if not np.isfinite(np.frombuffer(cloud.data, dtype="<f4")).all():
        return None
    return bytes(cloud.data)


def spatial_sample(data, limit):
    xyz = np.frombuffer(data, dtype="<f4").reshape(-1, 3)
    if len(xyz) <= limit:
        return data
    cells = np.floor(xyz / (VOXEL_METRES * 1.5)).astype(np.int32)
    _, indices = np.unique(cells, axis=0, return_index=True)
    if len(indices) < limit:
        # Keep representatives of all coarse cells and fill spare space with
        # original voxels in spatial order, without duplicating representatives.
        spare = np.ones(len(xyz), dtype=bool)
        spare[indices] = False
        rest = np.flatnonzero(spare)
        order = np.lexsort(cells[rest].T[::-1])
        indices = np.concatenate((indices, rest[order][np.linspace(0, len(rest)-1, limit-len(indices), dtype=int)]))
    elif len(indices) > limit:
        indices = indices[np.linspace(0, len(indices)-1, limit, dtype=int)]
    return xyz[indices].tobytes()


@dataclass(frozen=True)
class Sample:
    stamp: tuple
    session: str
    received: float
    updated_at: str
    data: bytes

    def etag(self, detail):
        seconds, nanoseconds = self.stamp
        return f'"{self.session}-{seconds}-{nanoseconds}-{detail}"'

    @property
    def age_ms(self):
        return round((monotonic() - self.received) * 1000)


class MeasuredMap:
    def __init__(self):
        self.lock = Lock()
        self.session = uuid4().hex
        self.sample = None
        self.levels = {}

    def new_session(self):
        with self.lock:
            self.session = uuid4().hex
            self.sample = None
            self.levels.clear()

    def accept(self, message):
        time = message.header.stamp
        stamp = time.sec, time.nanosec
        old = self.sample
        if old and stamp <= old.stamp:
            return
        if (data := packed_map(message)) is None:
            return
        with self.lock:
            if old and len(data) < len(old.data):
                self.session = uuid4().hex
            self.sample = Sample(stamp, self.session, monotonic(), datetime.now(timezone.utc).isoformat(), data)
            self.levels.clear()

    def payload(self, sample, detail):
        with self.lock:
            cached = self.levels.get(detail) if self.sample is sample else None
        if cached is not None:
            return cached
        data = spatial_sample(sample.data, DETAIL[detail])
        with self.lock:
            if self.sample is sample:
                self.levels[detail] = data
        return data
