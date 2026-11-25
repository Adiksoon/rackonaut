"""LiDAR/IMU localization. The navigation port is enabled only in sensor mode."""

import json
from collections import deque
from pathlib import Path
from time import monotonic, perf_counter

import numpy as np
import rclpy
from ament_index_python.packages import get_package_share_path
from builtin_interfaces.msg import Time
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from scipy.spatial.transform import Rotation
from sensor_msgs.msg import Imu, PointCloud2, PointField
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_ros import TransformBroadcaster

from rackonaut_avoidance.sensor import OFFSET, TOPIC, stamp, unpack
from .inertial import GRAVITY, State, propagate
from .registration import StaticMap, voxel_sample

FRAME, BODY = "rackonaut_odom", "rackonaut_base_link"
IMU_FRAME = "rackonaut_reference_drone/base_link/local_imu"
ESTIMATE = "/rackonaut/localization/estimate"
STATUS = "/rackonaut/localization/state"
IMU = "/rackonaut/drone/imu"
MAP = "/rackonaut/localization/measured_map"
MAX_SCAN_AGE = .64
MAX_IMU_AGE = .36
MAP_LIMIT = 80000
MAP_SIZE = .16


def ros_time(seconds):
    whole, nanos = divmod(round(seconds * 1e9), 10**9)
    return Time(sec=whole, nanosec=nanos)


def rounded(values, precision=3):
    return [round(float(x), precision) for x in values]


def odometry(state, gyro, sigma):
    message = Odometry()
    message.header.stamp, message.header.frame_id = ros_time(state.time), FRAME
    message.child_frame_id = BODY
    p = message.pose.pose.position
    p.x, p.y, p.z = state.xyz
    q = message.pose.pose.orientation
    q.x, q.y, q.z, q.w = state.attitude.as_quat()
    twist = message.twist.twist
    twist.linear.x, twist.linear.y, twist.linear.z = state.attitude.inv().apply(state.velocity)
    twist.angular.x, twist.angular.y, twist.angular.z = gyro
    for axis, uncertainty in enumerate([*sigma, .01, .01, .026]):
        message.pose.covariance[axis*7] = float(uncertainty**2)
    return message


class Localization(Node):
    def __init__(self):
        super().__init__("rackonaut_localization")
        self.mode = self.declare_parameter("mode", "shadow").value
        if self.mode not in {"shadow", "sensor_based"}:
            raise ValueError("Unknown localization mode")
        self.directory = Path(self.declare_parameter("data_dir", "control").value)
        config = get_package_share_path("rackonaut_warehouse") / "config"
        layout = json.loads((config / "localization_map.json").read_text())
        self.map = StaticMap(layout["boxes"], layout["triangles"])
        dock = json.loads((config / "aerial_layout.json").read_text())["nodes"]["dock"]
        self.dock = np.array(dock)
        self.anchor, self.fit, self.latest_estimate = None, None, None
        self.samples = deque(maxlen=100)
        self.calibration = deque(maxlen=25)
        self.gyro_bias, self.force_bias = np.zeros(3), np.zeros(3)
        self.calibrated = False
        self.pending, self.scan_time = None, -1.
        self.imu_at = self.match_at = self.last_pub = self.last_map = self.last_status = -1e6
        self.compute_ms = self.pipeline_ms = 0.
        self.clock_lag_ms = 0.
        self.quality = "STARTING"
        self.reason = "Calibrating IMU at the known installation dock"
        self.failures = 0
        self.accepted = 0
        self.updates = deque(maxlen=30)
        self.map_voxels = {}
        self.map_preview, self.unmatched = [], []
        self.path = deque(maxlen=1600)
        self.preview_count = 0
        latest = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.estimate_pub = self.create_publisher(Odometry, ESTIMATE, qos_profile_sensor_data)
        self.diag_pub = self.create_publisher(String, STATUS, latest)
        self.map_pub = self.create_publisher(PointCloud2, MAP, qos_profile_sensor_data)
        self.create_subscription(Imu, IMU, self.on_imu, qos_profile_sensor_data)
        self.create_subscription(PointCloud2, TOPIC, self.on_scan, qos_profile_sensor_data)
        self.create_service(Trigger, "/rackonaut/localization/export_map", self.export_map)
        if self.mode == "sensor_based":
            self.active_pub = self.create_publisher(Odometry, "/rackonaut/drone/odom", qos_profile_sensor_data)
            self.tf = TransformBroadcaster(self)
        self.create_timer(.025, self.tick)

    def on_imu(self, message):
        if message.header.frame_id != IMU_FRAME:
            return
        time = stamp(message)
        if self.samples and time <= self.samples[-1][0]:
            return
        w, a = message.angular_velocity, message.linear_acceleration
        gyro, force = np.array([w.x, w.y, w.z]), np.array([a.x, a.y, a.z])
        if not np.isfinite(gyro).all() or not np.isfinite(force).all():
            return
        # The simulator orientation field is deliberately unused.
        self.imu_at = monotonic()
        self.samples.append((time, gyro, force))
        if not self.calibrated:
            if np.linalg.norm(gyro) < .025 and np.linalg.norm(force - GRAVITY) < .20:
                self.calibration.append((gyro, force))
            else:
                self.calibration.clear()
            if len(self.calibration) == self.calibration.maxlen:
                self.gyro_bias, average = np.mean(self.calibration, axis=0)
                self.force_bias = average - GRAVITY
                self.calibrated = True
                self.reason = "Waiting for the first synchronized map match"

    def on_scan(self, message):
        time = stamp(message)
        if time > self.scan_time:
            self.scan_time = time
            self.pending = message, monotonic()

    def advance(self, time):
        return propagate(self.anchor, time, self.samples, self.gyro_bias, self.force_bias)

    def reject(self, reason):
        self.failures += 1
        self.quality = "LOST" if self.failures >= 2 else "DEGRADED"
        self.reason = reason

    def match(self, message, received, now):
        start = perf_counter()
        time = stamp(message)
        if self.anchor is None:
            self.anchor = State(time, self.dock, np.zeros(3), Rotation.identity())
        dt = time - self.anchor.time
        if dt < 0.:
            return
        # Confidence is evaluated against the measured fit, not the inertial prediction.
        predicted = self.advance(time) if dt < .70 else State(time, self.anchor.xyz, np.zeros(3), self.anchor.attitude)
        try:
            _, raw, _ = unpack(message)
        except ValueError as error:
            self.reject(str(error))
            return
        chosen = self.map.features(raw)
        fit = self.map.match(chosen + OFFSET, predicted.xyz, predicted.attitude)
        self.fit = fit
        if fit is None or fit.overlap < .34 or fit.rms > .059:
            self.reject("Insufficient static correspondences")
            return
        correction = fit.xyz - predicted.xyz
        velocity = predicted.velocity + .28 * correction / max(.13, min(dt, .25))
        limited = np.linalg.norm(velocity)
        if limited > 1.10:
            self.reject("Inertial prediction and scan position diverged")
            return
        if limited < .024 and np.linalg.norm(correction) < .009:
            velocity *= .55
        position = predicted.xyz + .86 * correction
        self.anchor = State(time, position, velocity, fit.attitude)
        self.match_at = received
        self.failures = 0
        self.accepted += 1
        self.updates.append((time, now))
        if fit.weakest < .011 or np.max(fit.sigma) > .058:
            self.quality, self.reason = "DEGRADED", "Weak geometry in at least one direction"
        else:
            self.quality, self.reason = "TRACKING", "Synchronized LiDAR fit and inertial prediction"
        gyro = self.samples[-1][1] - self.gyro_bias
        self.estimate_pub.publish(odometry(self.anchor, gyro, fit.sigma))
        self.latest_estimate = self.anchor
        if not self.path or np.linalg.norm(position-self.path[-1]) >= .13:
            self.path.append(position.copy())
        if self.quality == "TRACKING":
            self.accumulate(raw)
        self.compute_ms = (perf_counter() - start) * 1000
        self.pipeline_ms = (monotonic()-received) * 1000
        self.clock_lag_ms = max(0., (self.samples[-1][0]-time)*1000)

    def accumulate(self, raw):
        local = voxel_sample(raw[np.linalg.norm(raw, axis=1) <= 7.5], .14, 1500)
        world = self.anchor.attitude.apply(local + OFFSET) + self.anchor.xyz
        keys = np.floor(world / MAP_SIZE).astype(np.int32)
        for key, point in zip(keys, world):
            cell = tuple(key)
            previous = self.map_voxels.get(cell)
            if previous is not None:
                self.map_voxels[cell] = .85 * previous + .15 * point
            elif len(self.map_voxels) < MAP_LIMIT:
                self.map_voxels[cell] = point
        distances, _ = self.map.tree.query(world)
        self.unmatched = [rounded(p) for p in voxel_sample(world[distances > .23], .22, 120)]

    def status(self, now):
        imu_age, scan_age = now - self.imu_at, now - self.match_at
        if not self.calibrated or (not self.accepted and self.failures < 2):
            state = "DEGRADED"
        elif imu_age > MAX_IMU_AGE or scan_age > MAX_SCAN_AGE:
            state = "LOST"
        else:
            state = self.quality
        reason = self.reason
        if state == "LOST" and imu_age > MAX_IMU_AGE:
            reason = "IMU data stopped advancing"
        elif state == "LOST" and scan_age > MAX_SCAN_AGE and self.failures == 0:
            reason = "Matched scans stopped advancing"
        return state, reason

    def tick(self):
        now = monotonic()
        if self.calibrated and self.pending:
            message, received = self.pending
            time = stamp(message)
            if self.samples and time <= self.samples[-1][0] + .003:
                self.pending = None
                if now-self.imu_at <= MAX_IMU_AGE and time >= self.samples[0][0]-.025:
                    self.match(message, received, now)
            elif now-received > .20:
                self.pending = None
        state, reason = self.status(now)
        if self.mode == "sensor_based" and state == "TRACKING":
            time, gyro, _ = self.samples[-1]
            if time-self.last_pub >= .037:
                self.active_odometry(time, gyro)
        if now-self.last_map >= 1.:
            self.publish_map()
            self.last_map = now
        if now-self.last_status >= .16:
            self.publish_status(now, state, reason)
            self.last_status = now

    def active_odometry(self, time, gyro):
        estimate = self.advance(time) if time >= self.anchor.time else self.anchor
        message = odometry(estimate, gyro-self.gyro_bias, self.fit.sigma)
        self.active_pub.publish(message)
        pose = message.pose.pose
        tf = TransformStamped(header=message.header, child_frame_id=BODY)
        tf.transform.translation.x, tf.transform.translation.y, tf.transform.translation.z = estimate.xyz
        tf.transform.rotation = pose.orientation
        self.tf.sendTransform(tf)
        self.last_pub = time

    def publish_map(self):
        self.preview_count = len(self.map_voxels)
        if not self.map_voxels or self.anchor is None:
            return
        points = np.asarray(tuple(self.map_voxels.values()), dtype="<f4")
        preview = points[np.linspace(0, len(points)-1, min(2200, len(points)), dtype=int)]
        self.map_preview = [rounded(p) for p in preview]
        cloud = PointCloud2(height=1, width=len(points), point_step=12, row_step=len(points)*12,
                            fields=[PointField(name=c, offset=i*4, datatype=PointField.FLOAT32, count=1)
                                    for i, c in enumerate("xyz")], is_dense=True, data=points.tobytes())
        cloud.header.frame_id, cloud.header.stamp = FRAME, ros_time(self.anchor.time)
        self.map_pub.publish(cloud)

    def publish_status(self, now, state, reason):
        estimate, fit = self.latest_estimate, self.fit
        update_hz = sim_hz = 0.
        if len(self.updates) > 1:
            first, last = self.updates[0], self.updates[-1]
            update_hz = (len(self.updates)-1)/max(.001, last[1]-first[1])
            sim_hz = (len(self.updates)-1)/max(.001, last[0]-first[0])
        value = {
            "mode": self.mode, "state": state, "reason": reason, "accepted": self.accepted,
            "position": rounded(estimate.xyz) if estimate else None,
            "orientation": rounded(estimate.attitude.as_quat(), 6) if estimate else None,
            "scan_age_ms": round((now-self.match_at)*1000) if estimate else None,
            "imu_age_ms": round((now-self.imu_at)*1000) if self.samples else None,
            "update_hz": round(update_hz, 2), "sim_hz": round(sim_hz, 2),
            "rms": round(fit.rms, 4) if fit else None, "overlap": round(fit.overlap, 3) if fit else None,
            "sigma": rounded(fit.sigma, 4) if fit else None, "weakest": round(fit.weakest, 5) if fit else None,
            "processing_ms": round(self.compute_ms, 2), "pipeline_ms": round(self.pipeline_ms, 2),
            "scan_lag_sim_ms": round(self.clock_lag_ms), "map_voxels": self.preview_count,
            "map_points": self.map_preview, "unmatched": self.unmatched, "trajectory": [rounded(p) for p in self.path],
        }
        self.diag_pub.publish(String(data=json.dumps(value, separators=(",", ":"))))

    def export_map(self, _request, response):
        if not self.map_voxels:
            response.message = "No measured map is available"
            return response
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / "localization-measured.ply"
        points = np.asarray(tuple(self.map_voxels.values()), dtype="<f4")
        header = (f"ply\nformat binary_little_endian 1.0\nelement vertex {len(points)}\n"
                  "property float x\nproperty float y\nproperty float z\nend_header\n")
        path.write_bytes(header.encode() + points.tobytes())
        response.success, response.message = True, str(path)
        return response


def main():
    rclpy.init()
    node = Localization()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
