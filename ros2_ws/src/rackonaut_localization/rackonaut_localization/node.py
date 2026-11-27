"""LiDAR/IMU localization. The navigation port is enabled only in sensor mode."""

import json
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, perf_counter
from threading import Lock, Thread

import numpy as np
import rclpy
from ament_index_python.packages import get_package_share_path
from builtin_interfaces.msg import Time
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from scipy.spatial.transform import Rotation
from sensor_msgs.msg import Imu, PointCloud2, PointField
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_ros import TransformBroadcaster

from rackonaut_avoidance.sensor import FULL_ROUTE_RANGE, MAX_RANGE, OFFSET, TOPIC, stamp, unpack
from .inertial import GRAVITY, State, propagate
from .learned_map import FULL_WAREHOUSE_POINTS, MAP_FILE, load as load_learned_map, read_ply, save as save_learned_map
from .registration import StaticMap, voxel_sample
from .slam import FrozenRegistration, FullRouteRegistration, FullWarehouseRegistration, MeasuredRegistration
from .warehouse_config import (HISTORICAL_VARIANT, active_identifier, check_drone_model,
                               check_warehouse_variant, read, verified_package, warehouse_prefix)

FRAME, BODY = "rackonaut_odom", "rackonaut_base_link"
IMU_FRAME = "rackonaut_reference_drone/base_link/local_imu"
ESTIMATE = "/rackonaut/localization/estimate"
STATUS = "/rackonaut/localization/state"
IMU = "/rackonaut/drone/imu"
MAP = "/rackonaut/localization/measured_map"
SLAM_MAP = "/rackonaut/localization/slam_map"
MAPPING_COMMAND = "/rackonaut/localization/mapping_command"
MAPPING_ID = re.compile(r"CAL-[0-9A-F]{32}")
MAX_SCAN_AGE = .64
MAX_IMU_AGE = .36
MAP_LIMIT = 80000
MAP_SIZE = .16


@dataclass
class Measurements:
    voxels: dict = field(default_factory=dict)
    preview: list = field(default_factory=list)
    unmatched: list = field(default_factory=list)
    path: deque = field(default_factory=lambda: deque(maxlen=1600))
    stamp: float = 0.
    rejected_voxel_updates: int = 0


@dataclass
class Mapping:
    id: str
    stamp: float
    phase: str = "EMPTY"
    error: str = ""
    multi_sortie: bool = False
    checkpoint: int = 0


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
        if self.mode not in {"shadow", "sensor_based", "slam_shadow"}:
            raise ValueError("Unknown localization mode")
        self.directory = Path(self.declare_parameter("data_dir", "control").value)
        self.drone_model = self.declare_parameter("drone_model", "reference").value
        self.warehouse_variant = self.declare_parameter("warehouse_variant", HISTORICAL_VARIANT).value
        prefix = warehouse_prefix(self.warehouse_variant)
        self.mapping_only = self.declare_parameter("mapping_only", False).value
        full_route = self.declare_parameter("full_route_slam", False).value
        self.learned_mode = self.declare_parameter("learned_warehouse", False).value
        if self.learned_mode and (self.mode != "sensor_based" or not self.mapping_only or not full_route):
            raise ValueError("Learned warehouse requires the sensor-based 16 m localization profile.")
        self.registration_type = FullRouteRegistration if full_route else MeasuredRegistration
        self.sensor_range = FULL_ROUTE_RANGE if full_route else MAX_RANGE
        self.slam = self.registration_type() if self.mode == "slam_shadow" or self.mapping_only else None
        self.reference = None
        if self.slam is not None:
            dock = [-4.7, 10.3, .05]
        else:
            config = get_package_share_path("rackonaut_warehouse") / "config"
            layout = json.loads((config / f"{prefix}localization_map.json").read_text())
            self.reference = StaticMap(layout["boxes"], layout["triangles"])
            dock = json.loads((config / f"{prefix}aerial_layout.json").read_text())["nodes"]["dock"]
        self.dock = np.array(self.declare_parameter("dock_xyz", dock).value)
        self.installation_dock = self.dock.copy()
        self.warehouse_id = None
        self.warehouse_revision = None
        self.warehouse_error = ""
        self.warehouse_seen = None
        self.last_warehouse_check = -1e6
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
        self.production = self.cloud = Measurements()
        self.mapping = None
        self.mapping_closed = None
        self.energy, self.energy_at = {}, -1e6
        latest = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.estimate_pub = self.create_publisher(Odometry, ESTIMATE, qos_profile_sensor_data)
        self.diag_pub = self.create_publisher(String, STATUS, latest)
        self.map_pub = self.create_publisher(PointCloud2, MAP, qos_profile_sensor_data)
        self.imu_worker = None
        full_warehouse_profile = self.mapping_only and full_route and self.warehouse_variant == "open-aisle"
        if self.mode == "sensor_based" and (self.drone_model == "x3" or full_warehouse_profile):
            # Registration and map publication share the main executor. Record IMU arrivals
            # independently so a busy scan fit cannot delay receipt of new inertial samples.
            self.imu_inbox = deque(maxlen=32)
            self.imu_lock = Lock()
            receiver_name = ("rackonaut_x3_imu_receiver" if self.drone_model == "x3"
                             else "rackonaut_localization_imu_receiver")
            self.imu_receiver = Node(receiver_name)
            self.imu_receiver.create_subscription(Imu, IMU, self.enqueue_imu, qos_profile_sensor_data)
            self.imu_executor = SingleThreadedExecutor()
            self.imu_executor.add_node(self.imu_receiver)
            self.imu_worker = Thread(target=self.receive_imu, name="localization-imu")
            self.imu_worker.start()
        else:
            self.create_subscription(Imu, IMU, self.on_imu, qos_profile_sensor_data)
        self.create_subscription(PointCloud2, TOPIC, self.on_scan, qos_profile_sensor_data)
        self.create_service(Trigger, "/rackonaut/localization/export_map", self.export_map)
        if self.mode == "sensor_based":
            self.active_pub = self.create_publisher(Odometry, "/rackonaut/drone/odom", qos_profile_sensor_data)
            self.tf = TransformBroadcaster(self)
            self.slam_map_pub = self.create_publisher(PointCloud2, SLAM_MAP, qos_profile_sensor_data)
            self.create_subscription(String, MAPPING_COMMAND, self.on_mapping, 1)
            self.create_subscription(String, "/rackonaut/energy/state", self.on_energy, latest)
        self.create_timer(.025, self.tick)

    def on_energy(self, message):
        self.energy, self.energy_at = json.loads(message.data), monotonic()

    def physical_switch(self, now):
        return (now - self.energy_at <= .7
                and self.energy.get("switch_engaged")
                and self.energy.get("contact_source") == "gazebo_dock_switch")

    def check_warehouse(self, now):
        if (not self.learned_mode or self.mapping or now - self.last_warehouse_check < 1.
                or not self.physical_switch(now) or self.count_publishers("/rackonaut/drone/cmd_vel")):
            return
        self.last_warehouse_check = now
        try:
            identifier = active_identifier(self.directory)
            if identifier == self.warehouse_seen and not self.warehouse_error:
                return
            if identifier is None:
                self.set_warehouse(None, None, self.registration_type(), self.installation_dock, Measurements())
                return
            folder, manifest = verified_package(self.directory, identifier)
            check_drone_model(read(folder / "sensors.json"), self.drone_model)
            result = read(folder / "result.json")
            check_drone_model(result, self.drone_model)
            check_warehouse_variant(result, self.warehouse_variant)
            dock, frames = load_learned_map(folder / MAP_FILE)
            if np.linalg.norm(dock-self.installation_dock) > .02:
                raise ValueError("Learned warehouse dock does not match the physical installation.")
            points = read_ply(folder / "map.ply")
            cells = np.floor(points / MAP_SIZE).astype(np.int32)
            cloud = Measurements(voxels={tuple(cell): point for cell, point in zip(cells, points)},
                                 stamp=self.samples[-1][0] if self.samples else 0.)
            self.set_warehouse(identifier, manifest["revision"], FrozenRegistration(frames, dock), dock, cloud)
        except (OSError, ValueError, KeyError) as error:
            self.warehouse_error = str(error)
            if self.warehouse_id:
                self.slam = self.registration_type()
                self.warehouse_id = self.warehouse_revision = self.warehouse_seen = None
                self.reset_match("Active learned warehouse failed integrity verification")

    def set_warehouse(self, identifier, revision, registration, dock, cloud):
        self.slam, self.dock = registration, dock
        self.warehouse_id, self.warehouse_revision = identifier, revision
        self.warehouse_seen, self.warehouse_error = identifier, ""
        self.production = self.cloud = cloud
        self.reset_match("Matching the saved LiDAR map from the physical dock"
                         if identifier else "Initializing LiDAR around the physical dock")

    def on_mapping(self, message):
        now = monotonic()
        try:
            command = json.loads(message.data)
        except ValueError:
            return
        if not isinstance(command, dict) or not isinstance(command.get("mapping_id"), str):
            return
        identifier, action = command["mapping_id"], command.get("action")
        if not MAPPING_ID.fullmatch(identifier):
            return
        if action == "arm" and self.mapping and self.mapping.id == identifier and self.mapping.phase == "READY":
            self.mapping.phase = "RECORDING"
            return
        if (now - self.energy_at > .7 or not self.energy.get("contact") or not self.energy.get("switch_engaged")
                or self.energy.get("contact_source") != "gazebo_dock_switch"
                or self.count_publishers("/rackonaut/drone/cmd_vel")):
            return
        if action in {"close", "discard"} and self.mapping is None:
            self.mapping_closed = identifier
        elif action == "begin" and self.mapping is None:
            if not self.anchor or self.status(now)[0] != "TRACKING":
                return
            multi = command.get("multi_sortie") is True and self.mapping_only and self.registration_type is FullRouteRegistration
            self.mapping = Mapping(identifier, self.samples[-1][0], multi_sortie=multi)
            self.slam = FullWarehouseRegistration() if multi else self.registration_type()
            self.cloud = Measurements()
            self.reset_match("Initializing submap from the first synchronized dock scan")
        elif self.mapping and self.mapping.id == identifier:
            if action == "pause" and self.mapping.multi_sortie and self.mapping.phase == "RECORDING":
                number = self.mapping.checkpoint + 1
                destination = self.directory / "mapping" / identifier / "checkpoints" / f"{number:02d}"
                try:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with TemporaryDirectory(dir=destination.parent) as scratch:
                        staged = Path(scratch) / "measured"
                        self.save_session(staged)
                        staged.replace(destination)
                except (OSError, ValueError) as error:
                    self.mapping.error = f"Mapping checkpoint could not be saved: {error}"
                else:
                    self.mapping.checkpoint = number
                    self.mapping.phase, self.mapping.error = "PAUSED", ""
            elif action == "resume" and self.mapping.phase == "PAUSED" and self.status(now)[0] == "TRACKING":
                self.mapping.phase = "READY"
            elif action == "finish" and (
                self.mapping.phase == "RECORDING" and not self.mapping.multi_sortie
                or self.mapping.multi_sortie and self.mapping.checkpoint and self.mapping.phase in {"PAUSED", "READY"}
            ):
                try:
                    self.save_session()
                except (OSError, ValueError) as error:
                    self.mapping.error = f"Mapping result could not be saved: {error}"
                else:
                    self.mapping.phase, self.mapping.error = "COMPLETE", ""
            elif (action == "close" and self.mapping.phase in {"EMPTY", "READY", "PAUSED", "COMPLETE"}
                  or action == "discard" and self.mapping.multi_sortie):
                self.mapping = None
                self.slam = self.registration_type() if self.mapping_only else None
                self.mapping_closed = identifier
                self.cloud = self.production
                if self.learned_mode:
                    self.production = self.cloud = Measurements()
                    self.warehouse_seen = self.warehouse_id = self.warehouse_revision = None
                    self.dock = self.installation_dock
                self.reset_match("Reacquiring dock localization")

    def reset_match(self, reason):
        self.anchor = self.fit = self.latest_estimate = self.pending = None
        self.match_at = -1e6
        self.quality, self.reason = "STARTING", reason
        self.accepted = self.failures = 0
        self.updates.clear()

    def receive_imu(self):
        try:
            self.imu_executor.spin()
        except ExternalShutdownException:
            pass

    def enqueue_imu(self, message):
        received = monotonic()
        with self.imu_lock:
            self.imu_inbox.append((received, message))

    def drain_imu(self):
        with self.imu_lock:
            batch = tuple(self.imu_inbox)
            self.imu_inbox.clear()
        for received, message in batch:
            previous = self.samples[-1] if self.samples else None
            self.on_imu(message)
            if self.samples and self.samples[-1] is not previous:
                self.imu_at = received

    def close(self):
        if self.imu_worker is not None:
            self.imu_executor.shutdown()
            self.imu_worker.join()
            self.imu_receiver.destroy_node()

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
            if self.warehouse_id and not self.physical_switch(now):
                return
            self.anchor = State(time, self.dock, np.zeros(3), Rotation.identity())
        dt = time - self.anchor.time
        if dt < 0.:
            return
        # Confidence is evaluated against the measured fit, not the inertial prediction.
        predicted = self.advance(time) if dt < .70 else State(time, self.anchor.xyz, np.zeros(3), self.anchor.attitude)
        try:
            _, raw, _ = unpack(message, sensor_range=self.sensor_range)
        except ValueError as error:
            self.reject(str(error))
            return
        if self.slam is None:
            chosen = self.reference.features(raw)
            fit = self.reference.match(chosen + OFFSET, predicted.xyz, predicted.attitude)
        elif self.slam.target is None:
            if not self.slam.consider(raw, OFFSET, self.dock, Rotation.identity()):
                self.reject("Insufficient measured surfaces to initialize the local submap")
            return
        else:
            fit = self.slam.match(raw, OFFSET, predicted.xyz, predicted.attitude)
        self.fit = fit
        if fit is None or fit.overlap < .34 or fit.rms > .059:
            self.reject("Insufficient measured correspondences" if self.slam else "Insufficient static correspondences")
            return
        if self.warehouse_id and not self.mapping and not self.accepted and np.linalg.norm(fit.xyz-self.dock) > .12:
            self.reject("The measured position is inconsistent with the learned dock")
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
        if self.quality == "TRACKING":
            if self.slam is not None and not (self.mapping and self.mapping.phase in {"PAUSED", "COMPLETE"}):
                self.slam.consider(raw, OFFSET, position, fit.attitude)
            if self.mapping and self.mapping.phase == "EMPTY" and self.accepted >= 3:
                self.mapping.phase = "READY"
            if (self.mapping is None and not self.mapping_only) or (self.mapping and self.mapping.phase == "RECORDING"):
                if not self.cloud.path or np.linalg.norm(position-self.cloud.path[-1]) >= .13:
                    self.cloud.path.append(position.copy())
                self.accumulate(raw)
                self.cloud.stamp = time
        self.compute_ms = (perf_counter() - start) * 1000
        self.pipeline_ms = (monotonic()-received) * 1000
        self.clock_lag_ms = max(0., (self.samples[-1][0]-time)*1000)

    def accumulate(self, raw):
        local = voxel_sample(raw[np.linalg.norm(raw, axis=1) <= 7.5], .14, 1500)
        world = self.anchor.attitude.apply(local + OFFSET) + self.anchor.xyz
        keys = np.floor(world / MAP_SIZE).astype(np.int32)
        limit = FULL_WAREHOUSE_POINTS if self.mapping and self.mapping.multi_sortie else MAP_LIMIT
        for key, point in zip(keys, world):
            cell = tuple(key)
            previous = self.cloud.voxels.get(cell)
            if previous is not None:
                self.cloud.voxels[cell] = .85 * previous + .15 * point
            elif len(self.cloud.voxels) < limit:
                self.cloud.voxels[cell] = point
            else:
                self.cloud.rejected_voxel_updates += 1
        if self.slam is None:
            distances, _ = self.reference.tree.query(world)
            self.cloud.unmatched = [rounded(p) for p in voxel_sample(world[distances > .23], .22, 120)]

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
        if self.imu_worker is not None:
            self.drain_imu()
        now = monotonic()
        self.check_warehouse(now)
        if self.calibrated and self.pending:
            message, received = self.pending
            time = stamp(message)
            if self.samples and time <= self.samples[-1][0] + .003:
                self.pending = None
                if now-self.imu_at <= MAX_IMU_AGE and time >= self.samples[0][0]-.025:
                    self.match(message, received, now)
            elif now-received > .20:
                self.pending = None
        if self.imu_worker is not None:
            self.drain_imu()
            now = monotonic()
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
        if not self.cloud.voxels:
            return
        points = np.asarray(tuple(self.cloud.voxels.values()), dtype="<f4")
        preview = points[np.linspace(0, len(points)-1, min(2200, len(points)), dtype=int)]
        self.cloud.preview = [rounded(p) for p in preview]
        if len(points) > MAP_LIMIT:
            points = points[np.linspace(0, len(points)-1, MAP_LIMIT, dtype=int)]
        cloud = PointCloud2(height=1, width=len(points), point_step=12, row_step=len(points)*12,
                            fields=[PointField(name=c, offset=i*4, datatype=PointField.FLOAT32, count=1)
                                    for i, c in enumerate("xyz")], is_dense=True, data=points.tobytes())
        cloud.header.frame_id, cloud.header.stamp = FRAME, ros_time(self.cloud.stamp)
        publisher = self.slam_map_pub if self.mapping else self.map_pub
        publisher.publish(cloud)

    def publish_status(self, now, state, reason):
        estimate, fit = self.latest_estimate, self.fit
        update_hz = sim_hz = 0.
        if len(self.updates) > 1:
            first, last = self.updates[0], self.updates[-1]
            update_hz = (len(self.updates)-1)/max(.001, last[1]-first[1])
            sim_hz = (len(self.updates)-1)/max(.001, last[0]-first[0])
        value = {
            "mode": self.mode, "state": state, "reason": reason, "accepted": self.accepted,
            "source": "learned_map" if self.warehouse_id and not self.mapping else
                      "slam" if self.slam is not None else "reference",
            "warehouse_id": self.warehouse_id if not self.mapping else None,
            "warehouse_revision": self.warehouse_revision if not self.mapping else None,
            "warehouse_error": self.warehouse_error,
            "warehouse_ready": bool(self.warehouse_id and not self.mapping and state == "TRACKING" and self.accepted >= 3),
            "mapping_id": self.mapping.id if self.mapping else None,
            "mapping_phase": self.mapping.phase if self.mapping else None,
            "mapping_closed": self.mapping_closed,
            "mapping_stamp": self.mapping.stamp if self.mapping else None,
            "mapping_checkpoint": self.mapping.checkpoint if self.mapping else None,
            "mapping_error": self.mapping.error if self.mapping else "",
            "keyframe_count": self.slam.keyframe_count if self.slam is not None else None,
            "keyframe_window": len(self.slam.keyframes) if self.slam is not None else None,
            "position": rounded(estimate.xyz) if estimate else None,
            "orientation": rounded(estimate.attitude.as_quat(), 6) if estimate else None,
            "scan_age_ms": round((now-self.match_at)*1000) if estimate else None,
            "imu_age_ms": round((now-self.imu_at)*1000) if self.samples else None,
            "update_hz": round(update_hz, 2), "sim_hz": round(sim_hz, 2),
            "rms": round(fit.rms, 4) if fit else None, "overlap": round(fit.overlap, 3) if fit else None,
            "sigma": rounded(fit.sigma, 4) if fit else None, "weakest": round(fit.weakest, 5) if fit else None,
            "processing_ms": round(self.compute_ms, 2), "pipeline_ms": round(self.pipeline_ms, 2),
            "scan_lag_sim_ms": round(self.clock_lag_ms), "map_voxels": len(self.cloud.voxels),
            "rejected_voxel_updates": self.cloud.rejected_voxel_updates,
            "map_points": self.cloud.preview, "unmatched": self.cloud.unmatched, "trajectory": [rounded(p) for p in self.cloud.path],
        }
        self.diag_pub.publish(String(data=json.dumps(value, separators=(",", ":"))))

    def export_map(self, _request, response):
        if not self.cloud.voxels or self.mapping:
            response.message = "No measured map is available"
            return response
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / "localization-measured.ply"
        self.write_ply(path)
        response.success, response.message = True, str(path)
        return response

    def write_ply(self, path):
        points = np.asarray(tuple(self.cloud.voxels.values()), dtype="<f4").reshape(-1, 3)
        header = (f"ply\nformat binary_little_endian 1.0\nelement vertex {len(points)}\n"
                  "property float x\nproperty float y\nproperty float z\nend_header\n")
        pending = path.with_suffix(".ply.tmp")
        pending.write_bytes(header.encode() + points.tobytes())
        pending.replace(path)

    def save_session(self, directory=None):
        directory = directory or self.directory / "mapping" / self.mapping.id
        directory.mkdir(parents=True, exist_ok=True)
        self.write_ply(directory / "map.ply")
        result = {"mapping_id": self.mapping.id, "frame": FRAME, "dock": rounded(self.dock),
                  "started_sim": self.mapping.stamp, "last_measurement_sim": self.cloud.stamp,
                  "points": len(self.cloud.voxels), "trajectory": [rounded(point, 5) for point in self.cloud.path]}
        if self.drone_model != "reference":
            result["drone_model"] = self.drone_model
        if self.warehouse_variant != HISTORICAL_VARIANT:
            result["warehouse_variant"] = self.warehouse_variant
        if self.mapping.multi_sortie:
            result.update(multi_sortie=True, retained_keyframes=len(self.slam.keyframes),
                          accepted_keyframes=self.slam.keyframe_count,
                          rejected_voxel_updates=self.cloud.rejected_voxel_updates)
        if isinstance(self.slam, FullRouteRegistration):
            save_learned_map(directory / MAP_FILE, self.slam.keyframes, self.dock)
            result["localization_archive"] = MAP_FILE
        pending = directory / "result.tmp"
        pending.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        pending.replace(directory / "result.json")


def main():
    rclpy.init()
    node = Localization()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.close()
        node.destroy_node()
        rclpy.try_shutdown()
