"""Decode the organized Fortress cloud and align it to odometry at capture time."""

from collections import deque
from dataclasses import dataclass
from math import pi
from time import monotonic

import numpy as np
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import PointCloud2, PointField

TOPIC = "/rackonaut/drone/lidar/points"
FRAME = "rackonaut_reference_drone/base_link/local_lidar"
OFFSET = np.array([0., 0., .09])
WIDTH, HEIGHT = 192, 37
MIN_RANGE, MAX_RANGE = .10, 8.
MAX_ELEVATION = 88 * pi / 180
STALE_SECONDS = .65

AZIMUTH = np.linspace(-pi, pi, WIDTH)
ELEVATION = np.linspace(-MAX_ELEVATION, MAX_ELEVATION, HEIGHT)[:, None]
BEAMS = np.stack(np.broadcast_arrays(
    np.cos(ELEVATION) * np.cos(AZIMUTH),
    np.cos(ELEVATION) * np.sin(AZIMUTH),
    np.sin(ELEVATION),
), axis=2)
AXIS = np.argmax(np.abs(BEAMS), axis=2)[..., None]
COMPONENT = np.take_along_axis(BEAMS, AXIS, axis=2)[..., 0]


def rotation(q):
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([
        [1 - 2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
        [2*(x*y+w*z), 1 - 2*(x*x+z*z), 2*(y*z-w*x)],
        [2*(x*z-w*y), 2*(y*z+w*x), 1 - 2*(x*x+y*y)],
    ])


def stamp(message):
    return message.header.stamp.sec + message.header.stamp.nanosec * 1.e-9


def unpack(message):
    fields = {field.name: (field.offset, field.datatype, field.count) for field in message.fields}
    if (message.header.frame_id != FRAME or (message.width, message.height) != (WIDTH, HEIGHT)
            or any(fields.get(name) != (index * 4, PointField.FLOAT32, 1)
                   for index, name in enumerate("xyz"))
            or message.point_step < 12 or message.row_step < WIDTH * message.point_step
            or len(message.data) != HEIGHT * message.row_step):
        raise ValueError("Unexpected organized lidar cloud format")
    xyz = np.ndarray((HEIGHT, WIDTH, 3), dtype=">f4" if message.is_bigendian else "<f4",
                     buffer=message.data, strides=(message.row_step, message.point_step, 4))
    # A negative range reverses the signs of the Cartesian components. Recover
    # REP 117's signed infinities using the strongest axis of the calibrated ray.
    ranges = np.take_along_axis(xyz, AXIS, axis=2)[..., 0] / COMPONENT
    finite = np.isfinite(xyz).all(axis=2) & (ranges >= MIN_RANGE - .001) & (ranges <= MAX_RANGE + .001)
    far = np.isposinf(ranges) & ~np.isnan(xyz).any(axis=2)
    near = np.isneginf(ranges) & ~np.isnan(xyz).any(axis=2)
    if np.count_nonzero(finite | far | near) < .85 * WIDTH * HEIGHT:
        raise ValueError("Lidar scan has insufficient valid beams")
    ranges = np.where(finite, ranges, np.where(far, MAX_RANGE, np.nan))
    return ranges, xyz[finite], BEAMS[near]


@dataclass(frozen=True)
class Cloud:
    time: float
    received: float
    origin: np.ndarray
    orientation: np.ndarray
    ranges: np.ndarray
    hits: np.ndarray
    near: np.ndarray

    def observed(self, samples):
        local = (samples - self.origin) @ self.orientation
        radius = np.linalg.norm(local, axis=1)
        yaw = (np.arctan2(local[:, 1], local[:, 0]) + pi) / (2*pi) * (WIDTH - 1)
        pitch = np.arctan2(local[:, 2], np.hypot(local[:, 0], local[:, 1]))
        # The two blind caps remain unknown. Their nearest ring may establish
        # a hit, but is not used to mark the caps free.
        elevation = np.clip((pitch + MAX_ELEVATION) / (2*MAX_ELEVATION) * (HEIGHT-1), 0, HEIGHT-1)
        i0, j0 = np.floor(elevation).astype(int), np.floor(yaw).astype(int)
        i1, j1 = np.minimum(HEIGHT-1, i0+1), np.minimum(WIDTH-1, j0+1)
        measured = np.minimum.reduce([self.ranges[i0, j0], self.ranges[i0, j1],
                                      self.ranges[i1, j0], self.ranges[i1, j1]])
        return ((radius >= MIN_RANGE) & (np.abs(pitch) <= MAX_ELEVATION)
                & (radius + .045 < measured))


class Scanner:
    def __init__(self, node, exact_pose=False):
        self.poses = deque(maxlen=16)
        self.pending = None
        self.cloud = None
        self.latest_stamp = -1.
        self.exact_pose = exact_pose
        self.subscription = node.create_subscription(PointCloud2, TOPIC, self.receive, qos_profile_sensor_data)

    def odometry(self, message):
        p, q = message.pose.pose.position, message.pose.pose.orientation
        position = np.array([p.x, p.y, p.z])
        orientation = np.array([q.x, q.y, q.z, q.w])
        if np.isfinite(orientation).all() and np.linalg.norm(orientation) > .5:
            self.poses.append((stamp(message), position, rotation(orientation)))

    def receive(self, message):
        time = stamp(message)
        if time > self.latest_stamp:
            self.latest_stamp = time
            self.pending = message, monotonic()

    def current(self, now):
        if self.pending and self.poses:
            message, received = self.pending
            time = stamp(message)
            # Wait for bracketing odometry where possible and never align an
            # image to a pose taken long after the measurement.
            if self.poses[-1][0] >= time or now - received > .13:
                self.pending = None
                pose_time, center, matrix = min(self.poses, key=lambda pose: abs(time - pose[0]))
                if abs(pose_time - time) <= (.001 if self.exact_pose else .085):
                    try:
                        ranges, finite, near = unpack(message)
                    except ValueError:
                        pass
                    else:
                        origin = center + matrix @ OFFSET
                        self.cloud = Cloud(time, received, origin, matrix, ranges,
                                           finite @ matrix.T + origin, near @ matrix.T)
        return self.cloud if self.cloud and now - self.cloud.received <= STALE_SECONDS else None
