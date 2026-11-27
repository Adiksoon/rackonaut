"""Keep the browser connected to one ROS-controlled inspection at a time."""

import json
import os
import signal
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import atan2, cos, hypot, radians
from pathlib import Path
from secrets import compare_digest, token_urlsafe
from threading import RLock, Thread
from time import monotonic, time
from urllib.request import urlopen
from uuid import uuid4

import cv2
import rclpy
from ament_index_python.packages import get_package_prefix, get_package_share_path
from cv_bridge import CvBridge, CvBridgeError
from nav_msgs.msg import Odometry, Path as RosPath
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import Image, PointCloud2
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_msgs.msg import TFMessage

from rackonaut_avoidance.sensor import FULL_ROUTE_RANGE, MAX_RANGE, Scanner, stamp
from rackonaut_energy.model import Model
from rackonaut_localization.node import MAPPING_COMMAND, SLAM_MAP
from rackonaut_localization.warehouse_config import HISTORICAL_VARIANT, MAX_SORTIES, trajectory_file, warehouse_prefix
from rackonaut_mission.report import TERMINAL, export, fetch_api
from rackonaut_mission.manual import COMMAND_AGE, MANUAL_STAGE, MANUAL_TOPIC, decode_axes, departure_energy
from rackonaut_safety.geometry import route_zones

from .measured_map import ESTIMATE_TOPIC, FRAME, MAP_TOPIC, MeasuredMap, Sample
from .planning import energy_forecast, plan
from .route_recording import RouteRecorder
from .route_review import RouteReview
from .service import (BLOCKED, CHARGING, FINALIZING, MAPPED, MAPPING, PRODUCTION, READY, RECOVERY,
                      TRANSITIONING, Calibration, ServiceAccess)
from .teaching import HOVER_DISPLACEMENT, HOVER_ROTATION, Teaching, atomic_write, session_path
from .visualization import Visualizations
from .warehouse import WarehouseArchive
from .web import serve


@dataclass
class Job:
    run: str
    plan: dict
    processes: list
    mapping_id: str | None = None
    manual_token: str | None = None
    manual_sequence: int = -1
    manual_at: float = -1e6
    created: float = field(default_factory=monotonic)
    status: dict = field(default_factory=dict)
    status_at: float = 0.
    planned: list = field(default_factory=list)
    flown: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    recovery: dict | None = None
    recovery_at: float = 0.
    quality_uncertain: dict = field(default_factory=dict)
    finished_at: float | None = None
    archive: dict | None = None
    error: str = ""
    export_error: str = ""
    abort_requested: bool = False
    command: object = None
    next_command: float = 0.
    archive_future: object = None
    attempts: int = 0


def stop_workers(processes):
    for process in processes:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
    for process in processes:
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


class Control(Node):
    def __init__(self):
        super().__init__("rackonaut_control")
        self.port = self.declare_parameter("http_port", 8765).value
        self.safety_enabled = self.declare_parameter("safety_enabled", False).value
        safety_sensor = self.declare_parameter("safety_sensor", "virtual").value
        self.laser_enabled = safety_sensor == "laser"
        self.backend = self.declare_parameter("backend_url", "http://127.0.0.1:8000").value.rstrip("/")
        self.data = Path(self.declare_parameter("data_dir", "control").value).expanduser().resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        self.web = get_package_share_path("rackonaut_control") / "web"
        warehouse = get_package_share_path("rackonaut_warehouse")
        variant = self.declare_parameter("warehouse_variant", HISTORICAL_VARIANT).value
        self.warehouse_prefix = warehouse_prefix(variant)
        self.layout = json.loads((warehouse / "config/control_layout.json").read_text())
        self.layout["warehouse_variant"] = variant
        if self.safety_enabled:
            self.layout["safety_fields"] = json.loads((warehouse / "config/safety_fields.json").read_text())
        if self.laser_enabled:
            self.layout["laser_fields"] = json.loads((warehouse / "config/laser_fields.json").read_text())
        self.layout["adaptive_world"] = self.declare_parameter("adaptive_world", False).value
        self.aerial_enabled = self.declare_parameter("aerial_enabled", False).value
        self.avoidance_enabled = self.declare_parameter("avoidance_enabled", False).value
        self.recovery_enabled = self.declare_parameter("autonomous_recovery", False).value
        if self.recovery_enabled:
            self.layout["recovery"] = True
            self.recovery_operator = self.create_publisher(String, "/rackonaut/recovery/operator", 5)
        self.localization_mode = self.declare_parameter("localization_mode", "ground_truth").value
        self.mapping_only = self.declare_parameter("mapping_only", False).value
        self.full_route_slam = self.declare_parameter("full_route_slam", False).value
        self.learned_mode = self.declare_parameter("learned_warehouse", False).value
        self.layout["learned_warehouse"] = self.learned_mode
        if self.mapping_only:
            self.layout["mapping_only"] = True
        self.measured_map = MeasuredMap() if self.localization_mode == "sensor_based" else None
        self.slam_map = MeasuredMap() if self.measured_map is not None else None
        self.scan_sample = None
        self.scan_requested_until = self.next_scan = self.scan_tf_at = 0.
        self.localization_diagnostics = self.declare_parameter("localization_diagnostics", False).value
        self.localization, self.localization_at, self.pose_validation = None, -1e6, None
        if self.localization_mode != "ground_truth":
            self.layout["localization"] = {"mode": self.localization_mode, "diagnostics": self.localization_diagnostics}
        self.flight_props = set()
        if self.avoidance_enabled:
            self.flight_props = set(json.loads((warehouse / "config/avoidance_layout.json").read_text()))
            self.layout["avoidance"] = True
        self.energy_enabled = self.declare_parameter("energy_enabled", False).value
        if self.energy_enabled:
            if self.aerial_enabled:
                profile = json.loads((warehouse / f"config/{self.warehouse_prefix}aerial_layout.json").read_text())
                self.layout["aerial"] = profile
                self.layout["pad"] = profile["pad"]
                self.layout["takeoff_z"] = profile["nodes"]["shaft"][2]
                self.layout["safety_fields"]["D"] = profile["technical"]
                self.layout["scene"] = profile.pop("scene")
                self.layout["dock"] = profile["dock"]
            else:
                self.layout["dock"] = json.loads((warehouse / "config/dock_layout.json").read_text())
            self.layout["scene"]["parts"]["dock"] = self.layout["dock"]["parts"]
        self.marker_map = warehouse / "config/control_markers.json"
        self.lock = RLock()
        self.service_access = ServiceAccess()
        self.calibration = Calibration(self.data / "calibration-draft.json")
        self.teaching = Teaching(self.data, self.marker_map)
        self.route_review = RouteReview(self.teaching, self.layout.get("aerial"), variant)
        self.drone_model = self.declare_parameter("drone_model", "reference").value
        self.visualizations = Visualizations(self.data, self.web.parent / "config" / "reference-camera.json", variant)
        self.warehouse_archive = WarehouseArchive(self.data, self.route_review, self.layout, safety_sensor,
                                                  self.drone_model, self.visualizations)
        if self.learned_mode:
            try:
                self.visualizations.prime("warehouse", self.warehouse_archive.active_id())
            except (OSError, ValueError):
                pass
        self.route_recording = None
        self.calibration_supported = (self.aerial_enabled and self.avoidance_enabled and self.safety_enabled
                                      and self.recovery_enabled and self.energy_enabled
                                      and self.localization_mode == "sensor_based")
        if self.calibration_supported:
            self.calibration_request = self.create_publisher(String, "/rackonaut/calibration/request", 5)
            self.manual_request = self.create_publisher(String, MANUAL_TOPIC, 1)
            self.mapping_request = self.create_publisher(String, MAPPING_COMMAND, 1)
            self.next_mapping_command = 0.
            self.layout["manual_flight"] = True
        self.odom_at = 0.
        self.position, self.speed = None, 0.
        self.orientation = None
        self.jpeg, self.camera_at, self.frame_number = None, 0., 0
        self.perception_frame_seen = False
        self.safety, self.safety_at = None, -1e6
        self.energy, self.energy_at = None, -1e6
        self.overview_jpeg, self.overview_at = None, -1e6
        self.job = None
        self.history = self.load_history()
        self.recovery_history = {}
        if self.recovery_enabled:
            for file in sorted((self.data / "recoveries").glob("REC-*.json"), key=lambda path: path.stat().st_mtime)[-12:]:
                self.remember_recovery(json.loads(file.read_text()))
        self.backend_state = {"online": False, "mode": "", "slots": []}
        self.bridge = CvBridge()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="control-io")
        self.health_future = None
        self.next_health = 0.
        latest = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        if self.localization_mode != "ground_truth":
            self.create_subscription(String, "/rackonaut/localization/state", self.on_localization, latest)
        if self.measured_map is not None:
            self.scan_decoder = Scanner(self, exact_pose=True,
                                        sensor_range=FULL_ROUTE_RANGE if self.full_route_slam else MAX_RANGE)
            self.create_subscription(PointCloud2, MAP_TOPIC, self.measured_map.accept, qos_profile_sensor_data)
            self.create_subscription(PointCloud2, SLAM_MAP, self.on_slam_map, qos_profile_sensor_data)
            self.create_subscription(Odometry, ESTIMATE_TOPIC, self.scan_decoder.odometry, qos_profile_sensor_data)
            self.create_subscription(TFMessage, "/tf", self.on_scan_tf, qos_profile_sensor_data)
        if self.localization_diagnostics:
            self.create_subscription(String, "/rackonaut/localization/validation", self.on_pose_validation, latest)
        if self.energy_enabled:
            self.create_subscription(String, "/rackonaut/energy/state", self.on_energy, latest)
        if self.safety_enabled:
            self.safety_request = self.create_publisher(String, "/rackonaut/safety/request", 5)
            self.worker_control = self.create_publisher(String, "/rackonaut/safety/simulation/worker_target", 5)
            if self.laser_enabled or self.avoidance_enabled:
                self.obstacle_control = self.create_publisher(String, "/rackonaut/safety/simulation/obstacle_target", 5)
            self.create_subscription(String, "/rackonaut/safety/state", self.on_safety, latest)
            self.create_subscription(Image, "/rackonaut/safety/overview", self.on_overview, qos_profile_sensor_data)
        self.create_subscription(Odometry, "/rackonaut/drone/odom", self.on_odom, qos_profile_sensor_data)
        self.create_subscription(String, "/rackonaut/mission/status", self.on_status, latest)
        self.create_subscription(RosPath, "/rackonaut/mission/plan", self.on_plan, latest)
        self.create_subscription(RosPath, "/rackonaut/mission/path", self.on_path, latest)
        self.create_subscription(Image, "/rackonaut/camera/image_raw", self.on_raw, qos_profile_sensor_data)
        self.create_subscription(Image, "/rackonaut/perception/annotated", self.on_annotated, 1)
        self.create_subscription(String, "/rackonaut/perception/quality_uncertain", self.on_quality_uncertain, 5)
        self.start_client = self.create_client(Trigger, "/rackonaut/mission/start")
        self.abort_client = self.create_client(Trigger, "/rackonaut/mission/abort")
        self.timer = self.create_timer(.1, self.tick, clock=Clock(clock_type=ClockType.STEADY_TIME))

    def on_localization(self, message):
        state = json.loads(message.data)
        with self.lock:
            self.teaching.set_session(state.get("mapping_id") if state.get("source") == "slam" else None)
            if state.get("state") != "TRACKING" and (self.localization or {}).get("state") == "TRACKING":
                self.teaching.motion += 1
            if self.measured_map is not None:
                previous = self.localization or {}
                identifier = state.get("mapping_id")
                if identifier != previous.get("mapping_id"):
                    self.scan_sample = None
                    if identifier:
                        self.slam_map.new_session(identifier)
                elif not identifier and (state.get("warehouse_id") != previous.get("warehouse_id")
                                         or state.get("accepted", 0) < previous.get("accepted", 0)):
                    self.measured_map.new_session(state.get("warehouse_id"))
            self.localization, self.localization_at = state, monotonic()

    def on_slam_map(self, message):
        with self.lock:
            localization = self.localization or {}
            if (localization.get("mapping_id") == self.slam_map.session
                    and stamp(message) >= localization["mapping_stamp"]):
                self.slam_map.accept(message)

    def map_stream(self):
        return self.slam_map if (self.localization or {}).get("mapping_id") else self.measured_map

    def on_scan_tf(self, message):
        if any(transform.header.frame_id == FRAME and transform.child_frame_id == "rackonaut_base_link"
               for transform in message.transforms):
            self.scan_tf_at = monotonic()

    def latest_scan(self):
        self.scan_requested_until = monotonic() + 1.8
        sample = self.scan_sample
        return sample if sample and sample.session == self.map_stream().session and sample.age_ms <= 850 else None

    def sample_live_scan(self, now):
        if now > self.scan_requested_until or now < self.next_scan:
            return
        self.next_scan = now + .33
        cloud = self.scan_decoder.current(now)
        if cloud is None:
            return
        seconds, fraction = divmod(round(cloud.time * 1e9), 10**9)
        stamp = seconds, fraction
        sample = self.scan_sample
        session = self.map_stream().session
        if sample and (sample.session, sample.stamp) == (session, stamp):
            return
        self.scan_sample = Sample(stamp, session, cloud.received, datetime.now(timezone.utc).isoformat(),
                                  cloud.hits.astype("<f4").tobytes())

    def on_pose_validation(self, message):
        self.pose_validation = json.loads(message.data)

    def load_history(self):
        result = []
        for file in sorted((self.data / "reports").glob("*/run.json"), reverse=True)[:12]:
            try:
                snapshot = json.loads(file.read_text())
                result.append(self.history_item(snapshot["mission"], bool(snapshot.get("business")),
                                                snapshot.get("drone_model")))
            except (OSError, ValueError, KeyError, TypeError) as error:
                self.get_logger().warning(f"Could not read saved inspection {file.parent.name}: {error}")
        return result

    def history_item(self, status, business, drone_model=None):
        run = status["inspection_id"]
        learned = status.get("learned") or {}
        identifier = learned.get("configuration_id")
        archive = next((item for item in self.warehouse_archive.list()
                        if item["configuration_id"] == identifier), {}) if identifier else {}
        return {"run": run, "stage": status["stage"], "landed": status["landed"],
                "warehouse_configuration_id": identifier, "warehouse_revision": learned.get("revision"),
                "warehouse_name": archive.get("name", "Saved warehouse" if identifier else "Reference warehouse"),
                "drone_model": drone_model or archive.get("drone_model"),
                "planned_slots": status.get("planned_slots", []), "business": business,
                "confirmed": len(status["confirmed"]), "total": status["total"], "url": f"/reports/{run}"}

    def remember_recovery(self, record):
        if record and record.get("result") in {"RECOVERY_COMPLETE", "RECOVERY_FAILED"}:
            recovery_id = record["recovery_id"]
            self.recovery_history[recovery_id] = {
                "recovery_id": recovery_id, "inspection_id": record["inspection_id"],
                "result": record["result"], "url": f"/recoveries/{recovery_id}.json",
            }

    def on_odom(self, message):
        if message.header.frame_id != "rackonaut_odom":
            return
        p, q = message.pose.pose.position, message.pose.pose.orientation
        v = message.twist.twist.linear
        yaw = atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        with self.lock:
            self.position = [round(value, 3) for value in (p.x, p.y, p.z, yaw)]
            self.orientation = [q.x, q.y, q.z, q.w]
            self.speed = hypot(v.x, v.y, v.z)
            self.odom_at = monotonic()
            self.teaching.add_pose(message, self.odom_at)
            if self.teaching.poses and self.teaching.poses[-1].received == self.odom_at:
                self.record_pose(self.teaching.poses[-1], self.odom_at)

    def record_pose(self, pose, now, force=False):
        recorder = self.route_recording
        job = self.job
        if not recorder or not job or job.run != recorder.run or self.teaching.session != recorder.identity:
            return
        status = job.status
        local = self.localization or {}
        safety = self.safety_status() or {}
        required = safety.get("required", [])
        zones = safety.get("zones", {})
        energy = self.energy_state() or {}
        collision = status.get("avoidance") or {}
        scan_age = collision.get("scan_age_ms")
        sample = {
            "stage": self.stage(job), "flight_phase": status.get("flight_phase") or self.stage(job),
            "dock_contact": bool(energy.get("fresh") and energy.get("contact") and energy.get("switch_engaged")
                                 and energy.get("contact_source") == "gazebo_dock_switch"),
            "localization": {"state": local.get("state") if now-self.localization_at <= .40 else "STALE",
                             "source": local.get("source"), "rms_m": local.get("rms"), "overlap": local.get("overlap"),
                             "weakest": local.get("weakest"), "scan_age_ms": local.get("scan_age_ms"),
                             "imu_age_ms": local.get("imu_age_ms")},
            "collision": {"state": collision.get("state"), "reason": collision.get("reason"),
                          "scan_stamp": collision.get("scan_stamp"),
                          "scan_age_ms": None if scan_age is None else scan_age + max(0., (now-job.status_at)*1000),
                          "verified_distance_m": collision.get("verified_distance", 0.),
                          "obstacle_distance_m": collision.get("obstacle_distance"),
                          "direction": collision.get("direction")},
            "safety": {"phase": safety.get("phase"), "zones": required,
                       "verified": bool(required and safety.get("inspection_id") == job.run
                                        and safety.get("signals_online") and not safety.get("alarm")
                                        and all(zones.get(zone, {}).get("sensor") == "FRESH"
                                                and zones[zone].get("occupied") is False
                                                and zones[zone].get("signals_acknowledged") for zone in required))},
        }
        recorder.add(pose, sample, force)

    def on_status(self, message):
        status = json.loads(message.data)
        with self.lock:
            if not self.job or status["inspection_id"] != self.job.run:
                return
            self.job.status_at = monotonic()
            if self.recovery_enabled:
                self.job.recovery = status.pop("recovery", None)
                self.remember_recovery(self.job.recovery)
                self.job.recovery_at = monotonic()
                if self.job.finished_at is not None:
                    if self.job.manual_token and "manual" in status:
                        self.job.status["manual"] = status["manual"]
                    return
            self.job.status = status
            if status["stage"] in TERMINAL and self.job.finished_at is None:
                self.job.finished_at = monotonic()

    def receive_path(self, message, field_name):
        with self.lock:
            if self.job and self.job.status and message.header.frame_id == "rackonaut_odom":
                points = [pose.pose.position for pose in message.poses]
                setattr(self.job, field_name, [[round(p.x, 2), round(p.y, 2), round(p.z, 2)] for p in points])

    def on_plan(self, message):
        self.receive_path(message, "planned")

    def on_path(self, message):
        self.receive_path(message, "flown")

    def on_raw(self, message):
        self.update_camera(message)

    def on_annotated(self, message):
        if self.job and self.job.status:
            self.perception_frame_seen = True

    def on_quality_uncertain(self, message):
        finding = json.loads(message.data)
        with self.lock:
            if self.job and finding["inspection_id"] == self.job.run and finding["slot_id"] in self.job.plan["slots"]:
                self.job.quality_uncertain[finding["slot_id"]] = finding

    def on_safety(self, message):
        with self.lock:
            self.safety, self.safety_at = json.loads(message.data), monotonic()

    def on_energy(self, message):
        with self.lock:
            self.energy, self.energy_at = json.loads(message.data), monotonic()

    def energy_state(self):
        if self.energy is None:
            return None
        if monotonic() - self.energy_at > .8:
            return {**self.energy, "fresh": False, "dock": "FAULT", "charging": False}
        return self.energy

    def on_overview(self, message):
        if monotonic() - self.overview_at < .16:
            return
        try:
            image = self.bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
            ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 83])
        except (CvBridgeError, cv2.error, RuntimeError):
            return
        if ok:
            with self.lock:
                self.overview_jpeg, self.overview_at = encoded.tobytes(), monotonic()

    def safety_status(self):
        return self.safety if monotonic() - self.safety_at <= .65 else None

    def move_worker(self, request):
        target = request.get("target")
        allowed = {"outside", "A", "B", "T"}
        if self.aerial_enabled:
            allowed.update(("DA", "DB"))
        if not isinstance(target, str) or target not in allowed:
            raise ValueError("Choose a marked simulation destination.")
        if not self.safety_enabled or not self.worker_control.get_subscription_count():
            raise RuntimeError("Simulation worker controls are unavailable.")
        self.worker_control.publish(String(data=target))
        return {"accepted": True}

    def move_obstacle(self, request):
        target = request.get("target")
        allowed = {"forklift_a", "pallet_b", "clear"} if self.laser_enabled else set()
        if self.avoidance_enabled:
            allowed.update(self.flight_props | {"clear_flight"})
        if not isinstance(target, str) or target not in allowed:
            raise ValueError("Choose an available simulation obstacle action.")
        if not self.safety_enabled or not self.obstacle_control.get_subscription_count():
            raise RuntimeError("Simulation obstacle controls are unavailable.")
        self.obstacle_control.publish(String(data=target))
        return {"accepted": True}

    def update_camera(self, message):
        now = monotonic()
        if now - self.camera_at < .09:
            return
        try:
            image = self.bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
            ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 77])
        except (CvBridgeError, cv2.error, RuntimeError):
            return
        if ok:
            with self.lock:
                self.jpeg, self.camera_at = encoded.tobytes(), now
                self.frame_number += 1
                if self.teaching.session:
                    self.teaching.add_camera(message, self.jpeg, now, datetime.now(timezone.utc).isoformat())

    def at_pad(self):
        if self.position is None or monotonic() - self.odom_at > 1.5:
            return False
        x, y, z, _ = self.position
        pad = self.layout["pad"]
        return hypot(x - pad["x"], y - pad["y"]) <= .28 and abs(z - pad["z"]) <= .12 and self.speed <= .12

    @staticmethod
    def stage(job):
        return "ERROR" if job.error else job.status.get("stage", "STARTING")

    def busy(self):
        if not self.job:
            return False
        stage = self.stage(self.job)
        if stage in TERMINAL:
            return not self.job.manual_token and self.job.archive is None and not self.job.export_error
        return stage != "ERROR"

    def preview(self, selection):
        if selection.get("mode") == "learned":
            if not self.learned_mode:
                raise RuntimeError("Launch the learned warehouse profile before planning inspections.")
            return self.warehouse_archive.plan(selection, self.energy_state())
        route = plan(self.layout, selection, orthogonal_descent=self.drone_model == "x3")
        if self.safety_enabled and not self.aerial_enabled:
            route["required_zones"] = route_zones(route.get("safety_points", route["points"]), self.layout["safety_fields"])
        if self.energy_enabled:
            route["route"]["energy_crossing_x"] = self.layout["crossing_x"]
            route["route"]["energy_zones"] = route["required_zones"]
            telemetry = self.energy_state()
            route["energy"] = energy_forecast(self.layout, route, telemetry) if telemetry and telemetry["fresh"] else None
        return route

    def start_manual(self, request, mapping=False):
        if not self.calibration_supported:
            raise RuntimeError("Manual flight requires the protected Full Robotics profile.")
        zones = request.get("aisles", ["A"])
        available = {location["aisle"] for location in self.layout["slots"].values()}
        if (not isinstance(zones, list) or not zones
                or any(not isinstance(zone, str) or zone not in available for zone in zones)):
            raise ValueError("Select functional aisles for the reservation.")
        slots = [next(slot for slot, location in self.layout["slots"].items() if location["aisle"] == zone)
                 for zone in sorted(set(zones))]
        with self.lock:
            identifier = number = None
            if mapping:
                state = self.mapping_status()
                if (self.calibration.state != READY or not state or state.get("mapping_phase") != "READY"
                        or self.calibration.mapping_run or self.calibration.cancel_pending):
                    raise RuntimeError("Wait for a new mapping session and synchronized dock scans.")
                identifier = state["mapping_id"]
                if self.calibration.draft.get("multi_sortie"):
                    number = len(self.calibration.draft["sorties"]) + 1
                    if number > MAX_SORTIES:
                        raise RuntimeError("The calibration sortie limit has been reached.")
                    energy = self.energy_state() or {}
                    charged = energy.get("dock") == "READY" or (
                        number == 1 and energy.get("dock") == "AVAILABLE"
                        and energy["percent"] >= Model(**energy["model"]).ready
                    )
                    if not self.physical_dock(energy) or not charged:
                        raise RuntimeError("Wait for verified docking and charge readiness.")
            result = self.begin({"mode": "custom", "slots": slots}, manual=True, mapping_id=identifier)
            if identifier:
                energy = self.energy_state() or {}
                self.route_recording = RouteRecorder(self.teaching.root, identifier, result["inspection_id"],
                                                      energy.get("model", {}),
                                                      {key: energy.get(key) for key in
                                                       ("contact", "switch_engaged", "contact_source", "percent", "sim_time")},
                                                      number=number)
                if self.teaching.poses:
                    self.record_pose(self.teaching.poses[-1], monotonic(), force=True)
                self.calibration.mapping_run = result["inspection_id"]
                self.calibration.set_state(MAPPING, "Protected mapping flight requested.")
                self.send_mapping(identifier, "arm", monotonic())
            return result

    def begin(self, selection, manual=False, mapping_id=None):
        with self.lock:
            learned = not manual and selection.get("mode") == "learned"
            learned_manual = manual and self.learned_mode and self.warehouse_status()["ready"]
            if self.mapping_only and not (mapping_id or learned and self.learned_mode or learned_manual):
                raise RuntimeError("Open Warehouse Calibration to dispatch on this survey profile.")
            if self.calibration.state != (READY if mapping_id else PRODUCTION):
                raise RuntimeError("Warehouse calibration is active. New inspections are locked.")
            if self.busy():
                raise RuntimeError("Wait for the running inspection and its report.")
            if learned and not self.warehouse_status()["ready"]:
                raise RuntimeError("Wait for the active learned warehouse to localize at the dock.")
            planned = self.preview(selection)
            if planned.get("requires_multiple_sorties"):
                raise RuntimeError("Review the full plan and dispatch one verified sortie at a time.")
            if learned and (self.localization.get("warehouse_id") != selection.get("configuration_id")
                            or self.localization.get("warehouse_revision") != selection.get("revision")):
                raise RuntimeError("The active warehouse revision must match the loaded localization map.")
            if self.localization_mode == "sensor_based" and (
                    not self.localization or monotonic() - self.localization_at > .40
                    or self.localization.get("state") != "TRACKING"
                    or self.localization.get("mapping_id") != mapping_id):
                raise RuntimeError("Wait for reliable sensor-based localization.")
            if not self.at_pad():
                raise RuntimeError("The drone must be stopped on the launch pad before dispatch.")
            if self.energy_enabled:
                telemetry = self.energy_state()
                if not telemetry or not telemetry["fresh"] or not telemetry["contact"]:
                    raise RuntimeError("Fresh battery data and confirmed dock position are required.")
                if manual:
                    if not telemetry.get("budget_verified"):
                        raise RuntimeError("Energy telemetry cannot verify a safe manual departure.")
                    pad = planned["route"]["pad"]
                    minimum = departure_energy(Model(**telemetry["model"]),
                                               (pad["x"], pad["y"], pad["z"], radians(pad["yaw_deg"])))
                    if telemetry["percent"] < minimum:
                        raise RuntimeError(f"Insufficient energy for manual takeoff and verified return ({minimum:.1f}% required).")
                else:
                    forecast = planned["energy"] if learned else energy_forecast(self.layout, planned, telemetry)
                    if not forecast["can_start"]:
                        requirement = "the learned route and reserve" if learned else "the first stop and safe return"
                        raise RuntimeError(f"Insufficient energy for {requirement} ({forecast['minimum_percent']:.1f}% required).")
            if not manual and not self.backend_state["online"]:
                raise RuntimeError("The inventory API is unavailable.")
            missing = set(planned["slots"]) - set(self.backend_state["slots"])
            if missing and not manual:
                raise RuntimeError(f"Inventory API does not cover {', '.join(sorted(missing))}.")
            if self.safety_enabled:
                status = self.safety_status()
                if not status or not self.safety_request.get_subscription_count():
                    raise RuntimeError("The Safety Manager is unavailable.")
                if status["phase"] in {"PREPARING", "RESERVED", "RECOVERY"}:
                    raise RuntimeError(status["message"])
            if self.job:
                stop_workers(self.job.processes)
            elif self.start_client.service_is_ready():
                raise RuntimeError("Another mission manager is already present in this ROS domain.")
            utc = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            run = f"INS-CONTROL-{utc}-{uuid4().hex[:8].upper()}"
            directory = self.data / "dispatch" / run
            directory.mkdir(parents=True)
            route = directory / "route.json"
            route.write_text(json.dumps(planned["route"], indent=2) + "\n")
            common = {"use_sim_time": "true", "inspection_id": run, "backend_url": self.backend}
            # Lidar rendering reduces the wall-clock rate of the onboard camera.
            scan_hold = "2.5" if self.laser_enabled else "1.3"
            processes = []
            try:
                if not manual:
                    processes.append(self.spawn(directory, "rackonaut_perception", "inspect", {
                        **common, "marker_map": self.marker_map, "mission_scoped": "true",
                        "quality_enabled": str(planned["quality"]).lower(), "quality_dir": self.data / "quality",
                        "adaptive": str(planned["adaptive"]).lower(),
                    }))
                processes.append(self.spawn(directory, "rackonaut_mission", "run_mission", {
                    **common, "route_file": route, "scan_hold_seconds": scan_hold if planned["quality"] else "0.0",
                    **({"travel_timeout": "70.0", "obstacle_avoidance": "true"} if self.avoidance_enabled
                       else {"travel_timeout": "52.0"} if self.aerial_enabled else {}),
                    **({"recovery_dir": self.data / "recoveries"} if self.recovery_enabled else {}),
                    **({"sensor_localization": "true"} if self.localization_mode == "sensor_based" else {}),
                    "safety_interlock": str(self.safety_enabled).lower(),
                    "adaptive_quality": str(planned["adaptive"] and planned["quality"]).lower(),
                    "drone_model": self.drone_model,
                    **({"manual_flight": "true"} if manual else {}),
                    **({"mapping_id": mapping_id} if mapping_id else {}),
                    **({"full_route_slam": "true"} if self.full_route_slam else {}),
                }))
            except OSError:
                stop_workers(processes)
                raise
            token = token_urlsafe(24) if manual else None
            points = planned.get("safety_points", planned["points"])
            if manual:
                planned = {**planned, "mode": "manual", "slots": [], "points": []}
            self.job = Job(run, planned, processes, mapping_id=mapping_id, manual_token=token)
            self.perception_frame_seen = False
            if self.safety_enabled:
                self.safety_request.publish(String(data=json.dumps({"inspection_id": run, "points": points})))
            return {"inspection_id": run, **({"token": token} if manual else {})}

    def manual_command(self, request, action):
        sequence, sent = request.get("sequence"), request.get("issued_ms")
        if (type(sequence) is not int or not 0 <= sequence < 2**53
                or type(sent) not in (int, float) or not -.25 <= time() - sent / 1000 <= COMMAND_AGE):
            raise ValueError("Manual request is stale or out of sequence.")
        axes, speed = decode_axes(request) if action == "movement" else ((), 0.)
        with self.lock:
            job, token = self.job, request.get("token")
            if (not job or not job.manual_token or request.get("inspection_id") != job.run
                    or not isinstance(token, str) or not token.isascii() or not compare_digest(job.manual_token, token)):
                raise RuntimeError("The browser does not own this manual flight session.")
            stage = self.stage(job)
            if stage in TERMINAL | {"ERROR"} or job.abort_requested:
                raise RuntimeError("The manual flight session has ended.")
            if action == "return" and stage not in {"VERTICAL_TAKEOFF", MANUAL_STAGE}:
                raise RuntimeError("Wait for manual takeoff before requesting a return.")
            if sequence <= job.manual_sequence:
                raise RuntimeError("An updated movement request was already processed.")
            job.manual_sequence, job.manual_at = sequence, monotonic()
            if job.mapping_id and (action == "return" or any(axes)):
                self.teaching.motion += 1
            self.manual_request.publish(String(data=json.dumps({
                "inspection_id": job.run, "sequence": sequence, "sent": job.manual_at,
                "action": action, "axes": axes, "speed": speed,
            })))
            return {"accepted": True}

    @staticmethod
    def spawn(directory, package, executable, parameters):
        path = Path(get_package_prefix(package)) / "lib" / package / executable
        args = [str(path), "--ros-args"]
        for name, value in parameters.items():
            args.extend(("-p", f"{name}:={value}"))
        with (directory / f"{executable}.log").open("w") as log:
            return subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)

    def abort(self, request):
        with self.lock:
            if not self.job or request.get("inspection_id") != self.job.run:
                raise RuntimeError("Choose the active inspection to abort.")
            if self.stage(self.job) in TERMINAL | {"ERROR"}:
                raise RuntimeError("This inspection has already ended.")
            self.job.abort_requested = True
            return {"accepted": True}

    @staticmethod
    def physical_dock(energy):
        return bool(energy and energy.get("fresh") is True and energy.get("contact") is True
                    and energy.get("switch_engaged") is True and energy.get("contact_source") == "gazebo_dock_switch")

    def service_telemetry(self, now):
        connection = self.position is not None and now - self.odom_at <= .40
        localization_age = now - self.localization_at
        localization = self.localization if localization_age <= .40 else None
        scan_age = (localization or {}).get("scan_age_ms")
        imu_age = (localization or {}).get("imu_age_ms")
        lidar = scan_age is not None and scan_age + 1000 * localization_age <= 640
        imu = imu_age is not None and imu_age + 1000 * localization_age <= 360
        energy = self.energy_state() or {}
        safety = self.safety_status() or {}
        camera = bool(self.jpeg and now - self.camera_at < 2.)
        contact = self.physical_dock(energy)
        job = self.job
        stage = self.stage(job) if job else None
        return {"connection": connection, "drone_model": self.drone_model,
                "localization": (localization or {}).get("state", "UNAVAILABLE"),
                "lidar": lidar, "imu": imu, "camera": camera, "contact": contact, "dock": energy.get("dock"),
                "battery": energy.get("percent") if energy.get("fresh") else None,
                "safety": safety.get("phase", "UNAVAILABLE"), "safety_sensors": safety.get("sensor"),
                "drone": ("DOCKED" if contact else "IN_FLIGHT" if connection and not self.at_pad()
                          else "AT_PAD" if connection else "UNAVAILABLE"),
                "at_pad": self.at_pad(), "busy": self.busy(),
                "safety_ready": bool(safety.get("signals_online") and
                                     (safety.get("zones", {}).get("D") or {}).get("occupied") is False
                                     and safety.get("phase") not in {"PREPARING", "RESERVED", "RECOVERY"}),
                "mission": {"inspection_id": job.run, "stage": stage, "mode": job.plan["mode"],
                            "slots": job.plan["slots"],
                            "configuration_id": (job.plan["route"].get("learned") or {}).get("configuration_id"),
                            "status": {"flight_phase": job.status.get("flight_phase"),
                                       "manual": job.status.get("manual"), "detail": job.status.get("detail")}}
                if job else None,
                "position": self.position if connection else None, "speed": self.speed if connection else None}

    def service_snapshot(self):
        with self.lock:
            learned = self.warehouse_status()
            calibration = self.calibration.snapshot()
            if draft := calibration["draft"]:
                session = draft["calibration_id"]
                try:
                    captures = self.teaching.manifest(session)["locations"]
                    calibration["locations"] = [
                        {"id": row["storage_location_id"], "photo": row["reference_image"],
                         "marker_verified": row.get("id_source") == "aruco"}
                        for row in captures
                    ]
                except (ValueError, RuntimeError, KeyError, OSError):
                    calibration["locations"] = []
                if draft.get("multi_sortie"):
                    learned_ids = {row["id"] for row in calibration["locations"] if row.get("marker_verified")}
                    calibration["remaining"] = sorted(self.layout["slots"].keys() - learned_ids)
                    calibration["location_total"] = len(self.layout["slots"])
                    calibration["return_budget"] = (self.job.status.get("energy") or {}).get("return_percent") if self.job else None
            source = ("Saved LiDAR keyframes" if learned.get("ready") else "Onboard dock localization"
                      if self.mapping_only else "Preconfigured reference warehouse geometry")
            current_map = (learned.get("active_id") or "Choose a saved configuration") if self.learned_mode else (
                "Awaiting a mapping session" if self.mapping_only else
                f"{self.warehouse_prefix}localization_map.json" if self.localization_mode == "sensor_based"
                else "Control Center reference layout")
            profile = ("Learned warehouse" if self.learned_mode else "Protected survey" if self.mapping_only else
                       "Protected aerial" if self.aerial_enabled else "Showcase reference")
            if self.warehouse_prefix:
                profile += " · Open aisle descent"
            return {"available": self.calibration_supported,
                    "full_calibration_available": bool(self.calibration_supported and self.mapping_only
                                                       and self.full_route_slam and self.warehouse_prefix),
                    "system": self.service_telemetry(monotonic()), "calibration": calibration,
                    "mapping": self.mapping_status(),
                    "learned_warehouse": learned,
                    "warehouse": {"profile": profile,
                                  "map_source": source, "map": current_map,
                                  "locations": None if self.learned_mode else len(self.layout["slots"]),
                                  "status": "ACTIVE" if not self.learned_mode or learned["ready"] else "PENDING"}}

    def warehouse_status(self):
        localization = self.localization or {}
        if not self.learned_mode:
            return {"enabled": False}
        try:
            identifier = self.warehouse_archive.active_id()
            error = localization.get("warehouse_error")
        except (OSError, ValueError) as invalid:
            identifier, error = None, str(invalid)
        return {"enabled": True, "active_id": identifier, "loaded_id": localization.get("warehouse_id"),
                "ready": bool(identifier and identifier == localization.get("warehouse_id")
                              and localization.get("warehouse_ready") and monotonic()-self.localization_at <= .40),
                "error": error}

    def warehouse_catalog(self):
        return {**self.warehouse_status(), "configurations": self.warehouse_archive.list()}

    def warehouse_action(self, action, request, owner):
        with self.teaching.operations, self.lock:
            if not self.learned_mode or not self.service_access.authorized(owner):
                raise RuntimeError("Open the learned warehouse profile and unlock Service.")
            if action == "verify":
                return self.warehouse_archive.verify(request.get("configuration_id"))
            now = monotonic()
            telemetry = self.service_telemetry(now)
            if (not telemetry["contact"] or not self.at_pad() or self.busy()
                    or telemetry["safety"] in {"PREPARING", "RESERVED", "RECOVERY", "UNAVAILABLE"}
                    or self.count_publishers("/rackonaut/drone/cmd_vel")):
                raise RuntimeError("Confirm physical docking and finish the active mission before changing the warehouse.")
            if action == "seal":
                draft = self.calibration.draft or {}
                session = draft.get("calibration_id")
                if self.calibration.state != MAPPED or request.get("calibration_id") != session:
                    raise RuntimeError("Choose the current completed calibration.")
                result = self.warehouse_archive.seal(session, draft.get("warehouse_name") or "Learned warehouse")
                self.visualizations.prime("warehouse", result["manifest"]["configuration_id"])
                return result
            if self.calibration.state != PRODUCTION or request.get("confirm") is not True:
                raise RuntimeError("Close Warehouse Calibration and confirm activation.")
            result = self.warehouse_archive.activate(request.get("configuration_id"))
            self.visualizations.prime("warehouse", result["manifest"]["configuration_id"])
            return result

    def mapping_status(self):
        localization = self.localization or {}
        draft = self.calibration.draft
        return localization if draft and localization.get("mapping_id") == draft["calibration_id"] else None

    def send_mapping(self, identifier, action, now):
        if now >= self.next_mapping_command:
            command = {"mapping_id": identifier, "action": action}
            if action == "begin" and self.calibration.draft.get("multi_sortie"):
                command["multi_sortie"] = True
            self.mapping_request.publish(String(data=json.dumps(command)))
            self.next_mapping_command = now + .32

    def start_calibration(self, request):
        warehouse = request.get("warehouse_name")
        multi = request.get("multi_sortie", False)
        if type(multi) is not bool:
            raise ValueError("multi_sortie must be true or false.")
        if multi and not (self.mapping_only and self.full_route_slam
                          and self.layout["warehouse_variant"] == "open-aisle"):
            raise RuntimeError("Full calibration requires open-aisle with full-range sensor-only mapping.")
        if warehouse is not None and (not isinstance(warehouse, str) or len(warehouse) > 100):
            raise ValueError("Use at most 100 characters for the optional warehouse name.")
        with self.lock:
            if not self.calibration_supported:
                raise RuntimeError("Calibration requires the Full Robotics profile with sensor localization and Recovery.")
            if self.calibration.state != PRODUCTION:
                raise RuntimeError("A calibration is already active.")
            job = self.job
            active = job and self.stage(job) not in TERMINAL | {"ERROR"}
            if ("expected_inspection_id" in request
                    and request["expected_inspection_id"] != (job.run if active else None)):
                raise RuntimeError("The active inspection changed. Review the current flight before starting calibration.")
            if active and job.manual_token:
                raise RuntimeError("Return the manual flight to the dock before starting calibration.")
            safety = self.safety_status()
            if safety and safety["phase"] == "RECOVERY":
                raise RuntimeError("Resolve the current incident in the Recovery Center first.")
            if job is None and self.start_client.service_is_ready():
                raise RuntimeError("An independent Mission Manager is present. It must be stopped first.")
            self.calibration.start(warehouse.strip() or None if warehouse else None,
                                   job.run if active else None, monotonic(), self.teaching.create, multi)
            return self.calibration.snapshot()

    def finish_full_calibration(self, request):
        with self.teaching.operations, self.lock:
            calibration = self.calibration
            draft = calibration.draft or {}
            identifier = draft.get("calibration_id")
            if (not draft.get("multi_sortie") or request.get("calibration_id") != identifier
                    or calibration.state not in {CHARGING, READY} or calibration.mapping_run
                    or calibration.cancel_pending or not draft["sorties"]
                    or not self.physical_dock(self.energy_state())):
                raise RuntimeError("Finish the sortie, save its checkpoint and confirm the physical dock first.")
            records = self.teaching.manifest(identifier)["locations"]
            taught = {row["storage_location_id"] for row in records if row.get("id_source") == "aruco"}
            if taught != self.layout["slots"].keys() or len(records) != len(taught):
                raise RuntimeError("Register all functional locations before finishing the full calibration.")
            calibration.set_state(FINALIZING, "Saving the complete measured warehouse at the physical dock.")
            return calibration.snapshot()

    def teaching_gate(self, now):
        mapping = self.mapping_status() or {}
        job = self.job
        if (self.calibration.state != MAPPING or mapping.get("mapping_phase") != "RECORDING"
                or not job or not job.manual_token or job.mapping_id != mapping.get("mapping_id")
                or self.stage(job) != MANUAL_STAGE or now-job.status_at > .45
                or job.abort_requested or not job.status.get("motion_owned")):
            return "Registration requires the active mapping flight."
        telemetry = self.service_telemetry(now)
        if (mapping.get("source") != "slam" or telemetry["localization"] != "TRACKING"
                or not all(telemetry[key] for key in ("lidar", "imu", "connection"))):
            return "Wait for fresh LiDAR–IMU localization in TRACKING."
        safety = self.safety_status() or {}
        energy = self.energy_state() or {}
        required = safety.get("required", [])
        zones = safety.get("zones", {})
        # Safety's permit is a departure handshake. Verify the active reservation in flight.
        if (safety.get("inspection_id") != job.run or safety.get("phase") != "RESERVED"
                or safety.get("alarm") or not safety.get("signals_online") or not required
                or not all(zones.get(zone, {}).get("sensor") == "FRESH"
                           and zones[zone].get("occupied") is False
                           and zones[zone].get("signals_acknowledged") for zone in required)
                or not energy.get("fresh") or not energy.get("budget_verified") or energy.get("contact")):
            return "Safety reservation and verified energy are required."
        if (job.status.get("manual") or {}).get("state") != "HOLD":
            return "Release the movement controls and hold position."
        return None

    def teaching_state(self):
        with self.lock:
            now = monotonic()
            draft = self.calibration.draft
            mode = self.calibration.state
            reason = self.teaching_gate(now) if draft else None
            if draft and reason is None:
                try:
                    self.teaching.inputs(now)
                except RuntimeError as error:
                    reason = str(error)
        return {"mode": mode, "manifest": self.teaching.manifest(draft["calibration_id"]) if draft else None,
                "capture_ready": draft is not None and reason is None, "reason": reason,
                "editable": mode in {MAPPING, MAPPED}}

    def teach_location(self, action, request, owner):
        with self.teaching.operations:
            with self.lock:
                now = monotonic()
                mapping = self.mapping_status() or {}
                identity = mapping.get("mapping_id")
                recording = self.calibration.state == MAPPING and mapping.get("mapping_phase") == "RECORDING"
                docked_edit = (self.calibration.state == MAPPED and mapping.get("mapping_phase") == "COMPLETE"
                               and not self.calibration.cancel_pending and action in {"rename", "delete"}
                               and self.at_pad() and self.service_telemetry(now)["contact"])
                if not identity or request.get("calibration_id") != identity or not (recording or docked_edit):
                    raise RuntimeError("Choose the current mapping flight.")
                if action in {"capture", "save"}:
                    if reason := self.teaching_gate(now):
                        raise RuntimeError(reason)
                    inputs = self.teaching.inputs(now)
                    motion = self.teaching.motion
                    quality = {key: mapping.get(key) for key in
                               ("source", "state", "rms", "overlap", "weakest", "sigma", "scan_age_ms", "imu_age_ms")}
                self.teaching.writing = action != "capture"
            try:
                if action in {"capture", "save"}:
                    camera, sample = self.teaching.pair(*inputs, now)
                    if not self.service_access.authorized(owner):
                        raise RuntimeError("Unlock Service to continue.")
                    if action == "capture":
                        return self.teaching.preview(identity, owner, motion, quality, camera, sample, now)
                    image = self.teaching.get_preview(request.get("capture_id"), owner, now)
                    if (image.session != identity or image.motion != motion
                            or hypot(*(a-b for a, b in zip(image.sample["position_m"], sample["position_m"]))) > HOVER_DISPLACEMENT
                            or abs(sum(a*b for a, b in zip(image.sample["orientation_xyzw"], sample["orientation_xyzw"])))
                            < cos(HOVER_ROTATION/2)):
                        raise RuntimeError("The drone moved after the preview. Capture a new image.")
                    with self.lock:
                        if self.teaching.motion != motion or self.teaching_gate(monotonic()):
                            raise RuntimeError("Wait for a stable hover and take a fresh capture.")
                    return self.teaching.edit(action, identity, request, image)
                if not self.service_access.authorized(owner):
                    raise RuntimeError("Unlock Service to continue.")
                return self.teaching.edit(action, identity, request)
            finally:
                self.teaching.writing = False

    def review_route(self, action, request, owner):
        with self.teaching.operations:
            with self.lock:
                draft = self.calibration.draft
                session = draft.get("calibration_id") if draft else None
                if (not session or request.get("calibration_id") != session or self.calibration.state != MAPPED
                        or self.calibration.cancel_pending or not self.service_telemetry(monotonic())["contact"]):
                    raise RuntimeError("Route review requires a completed mapping session and physical docking.")
            if not self.service_access.authorized(owner):
                raise RuntimeError("Unlock Service to continue.")
            result = self.route_review.action(action, session, request)
            if action == "approve":
                self.visualizations.prime("calibration", session)
            return result

    def cancel_calibration(self, _request):
        with self.lock:
            if self.calibration.state == PRODUCTION:
                raise RuntimeError("No active calibration.")
            if self.calibration.state == MAPPING:
                raise RuntimeError("Return the mapping flight to the dock before closing calibration.")
            self.calibration.cancel_pending = True
            self.tick_calibration(monotonic())
            return self.calibration.snapshot()

    def tick_calibration(self, now):
        calibration = self.calibration
        if calibration.state == PRODUCTION:
            return
        job = self.job
        stage = self.stage(job) if job else None
        live = stage is not None and stage not in TERMINAL | {"ERROR"}
        telemetry = self.service_telemetry(now)
        safety = self.safety_status() or {}
        reserved = telemetry["safety"] in {"PREPARING", "RESERVED", "RECOVERY"}
        docked = (not live and not reserved and self.at_pad() and telemetry["connection"] and telemetry["contact"]
                  and safety.get("signals_online") and (safety.get("zones", {}).get("D") or {}).get("occupied") is False
                  and (job is not None or not self.start_client.service_is_ready())
                  and not self.count_publishers("/rackonaut/drone/cmd_vel"))
        if not docked:
            calibration.dock_since = None
        elif calibration.dock_since is None:
            calibration.dock_since = now
        stable = calibration.dock_since is not None and now - calibration.dock_since >= .65
        session = self.mapping_status()
        identifier = calibration.draft["calibration_id"] if calibration.draft else None
        if stable and calibration.cancel_pending:
            if identifier and (self.localization or {}).get("mapping_closed") != identifier:
                if not calibration.mapping_run or (session or {}).get("mapping_phase") == "COMPLETE":
                    self.send_mapping(identifier, "close", now)
                    return
            elif telemetry["localization"] == "TRACKING" and not (self.localization or {}).get("mapping_id"):
                try:
                    calibration.clear()
                except OSError as error:
                    calibration.set_state(BLOCKED, f"The calibration draft could not be cleared: {error.strerror}.")
                return
        phase = (session or {}).get("mapping_phase")
        multi = bool(calibration.draft and calibration.draft.get("multi_sortie"))
        if multi and calibration.state == FINALIZING and stable:
            if phase != "COMPLETE":
                self.send_mapping(identifier, "finish", now)
                return
        if phase == "COMPLETE" and calibration.state != MAPPED:
            draft = {**calibration.draft, "map_reference": f"/api/service/mapping/{identifier}/map.ply"}
            try:
                calibration.store(draft)
            except OSError as error:
                calibration.set_state(BLOCKED, f"Mapping result saved. Draft storage unavailable: {error.strerror}.")
                return
            calibration.draft = draft
            calibration.set_state(MAPPED, "Mapping result and trajectories saved after verified docking.")
            self.visualizations.prime("calibration", identifier)
            return
        if multi and calibration.state == CHARGING and stable:
            energy = self.energy_state() or {}
            if energy.get("dock") == "READY" and telemetry["localization"] == "TRACKING" and all(
                telemetry[key] for key in ("lidar", "imu", "camera")
            ):
                if phase == "PAUSED":
                    self.send_mapping(identifier, "resume", now)
                elif phase == "READY":
                    calibration.set_state(READY, "Charged and localized in the same measured map. Start the next sortie or finish.")
            return
        if identifier and calibration.mapping_run:
            recorder = self.route_recording
            if phase == "READY":
                self.send_mapping(identifier, "arm", now)
            elif phase == "RECORDING" and stable and not self.teaching.writing:
                if recorder and recorder.run == calibration.mapping_run and not recorder.done.is_set():
                    if self.teaching.poses:
                        self.record_pose(self.teaching.poses[-1], now, force=True)
                    battery = job.status.get("energy", {}) if job else {}
                    recorder.finish(stage, telemetry["contact"], {"sorties": battery.get("sorties", []),
                                                                   "landing_percent": (self.energy_state() or {}).get("percent"),
                                                                   "landing_sim_time": (self.energy_state() or {}).get("sim_time"),
                                                                   "dock_contact_source": "gazebo_dock_switch"})
                elif multi:
                    if not recorder or recorder.error or not (recorder.ending or {}).get("complete"):
                        calibration.set_state(BLOCKED, "The sortie has no complete trajectory and verified return.")
                    else:
                        self.send_mapping(identifier, "pause", now)
                else:
                    self.send_mapping(identifier, "finish", now)
            elif multi and phase == "PAUSED" and stable and recorder and session.get("mapping_checkpoint") == recorder.number:
                sorties = [*calibration.draft["sorties"], {
                    "number": recorder.number, "inspection_id": recorder.run,
                    "trajectory": trajectory_file(recorder.number), "samples": recorder.count,
                    "start": recorder.header["takeoff_dock"], "end": recorder.ending["energy"],
                    "status": "DOCKED",
                }]
                draft = {**calibration.draft, "sorties": sorties}
                try:
                    index = session_path(self.teaching.root, identifier, "sorties.json")
                    atomic_write(index, (json.dumps(sorties, indent=2, allow_nan=False) + "\n").encode())
                    calibration.store(draft)
                except (OSError, ValueError) as error:
                    calibration.set_state(BLOCKED, f"The sortie checkpoint index could not be saved: {error}.")
                    return
                calibration.draft = draft
                calibration.mapping_run = None
                self.route_recording = None
                calibration.set_state(CHARGING, "Sortie saved at the physical dock. Charging for the next flight.")
            if telemetry["safety"] == "RECOVERY" and not stable:
                calibration.set_state(RECOVERY, "Mapping paused. Resolve the incident in Recovery before closing the session.")
            return
        if calibration.state not in TRANSITIONING:
            return
        if telemetry["safety"] == "RECOVERY" or (calibration.owner and stage == "ABORTED"):
            detail = safety.get("alarm") or {}
            calibration.set_state(RECOVERY, detail.get("message") or (job.status.get("detail") if job else None)
                                  or "Safety requires operator-approved Recovery.")
        elif calibration.owner and stage == "ERROR":
            calibration.set_state(BLOCKED, job.error)
        elif live and calibration.owner == job.run:
            accepted = job.status.get("calibration_id") == calibration.draft["calibration_id"]
            if (not accepted and now-calibration.started > 8.) or (accepted and now-job.status_at > 1.2):
                job.abort_requested = True
                calibration.set_state(RECOVERY, "Mission return acknowledgement lost. Verify the drone in Recovery.")
            elif accepted and stage in {"RETURN_TO_DOCK", "DOCKING", "LAND"}:
                docking = stage in {"DOCKING", "LAND"}
                calibration.set_state("WAITING_FOR_DOCK" if docking else "RETURNING_TO_DOCK", job.status["detail"])
            else:
                calibration.set_state("STOPPING_INSPECTION", "Stopping inspection and retaining its observations.")
        elif stable and telemetry["localization"] == "TRACKING" and telemetry["lidar"] and telemetry["imu"] and telemetry["camera"]:
            if (session or {}).get("mapping_phase") == "READY":
                calibration.set_state(READY, "Physical dock and measured localization confirmed. The mapping result is empty.")
            elif not calibration.cancel_pending and not session:
                calibration.set_state("PREPARING_CALIBRATION", "Starting a measured submap at the physical dock.")
                self.send_mapping(identifier, "begin", now)
        elif now - calibration.started > 25. and (not job or now - (job.finished_at or 0.) > 25.):
            calibration.set_state(BLOCKED, "Physical dock, current sensors or Safety readiness could not be confirmed.")
        else:
            calibration.set_state("WAITING_FOR_DOCK", "Waiting for stable physical dock contact, Safety and fresh sensors.")

    def recovery_action(self, request, action):
        with self.lock:
            job = self.job
            if not self.recovery_enabled or not job or request.get("inspection_id") != job.run:
                raise RuntimeError("Choose the interrupted inspection in the Recovery Center.")
            recovery = job.recovery or {}
            if monotonic()-job.recovery_at > .7 or not self.recovery_operator.get_subscription_count():
                raise RuntimeError("The mission control owner is unavailable. Physical recovery is required.")
            phase = recovery.get("phase")
            if action == "evaluate":
                safety = self.safety_status()
                if phase not in {"RECOVERY_REQUIRED", "RECOVERY_FAILED"} or not safety or safety["phase"] != "RECOVERY":
                    raise RuntimeError("A Safety recovery reservation and a stopped inspection are required.")
            elif request.get("recovery_id") != recovery.get("recovery_id") or not recovery.get("recovery_id"):
                raise RuntimeError("Choose the current recovery procedure.")
            elif action == "authorize" and (phase != "WAITING_FOR_OPERATOR_APPROVAL"
                    or request.get("proposal") != recovery.get("proposal")):
                raise RuntimeError("Review the current return plan after all recovery conditions are satisfied.")
            elif action == "abort" and phase in {"RECOVERY_COMPLETE", "RECOVERY_FAILED"}:
                raise RuntimeError("This recovery has ended.")
            payload = {k: recovery.get(k) for k in ("recovery_id", "proposal")}
            payload.update(action=action, inspection_id=job.run)
            self.recovery_operator.publish(String(data=json.dumps(payload)))
            return {"accepted": True}

    def read_backend(self):
        try:
            with urlopen(self.backend + "/health", timeout=1.5) as response:
                health = json.load(response)
            with urlopen(self.backend + "/api/inventory/expected", timeout=1.5) as response:
                inventory = json.load(response)
            return {"online": health["status"] == "ok", "mode": health["mode"],
                    "slots": [item["slot_id"] for item in inventory["locations"]]}
        except (OSError, ValueError, KeyError):
            return {"online": False, "mode": "", "slots": []}

    def make_archive(self, job):
        api = fetch_api(self.backend, job.run)
        selected = set(job.plan["slots"])
        if any(event["slot_id"] not in selected for event in api["observations"]):
            raise ValueError("Inventory API returned an observation outside this mission's scope.")
        source = self.data / "quality" / job.run
        snapshot = {"mission": job.status, "api": api, "drone_model": self.drone_model}
        export(snapshot, source, self.data / "reports", backend=self.backend)
        return {"url": f"/reports/{job.run}", "events": len(api["observations"]),
                "rows": [row for row in api["summary"]["slots"] if row["slot_id"] in selected],
                "discrepancies": [row for row in api["discrepancies"] if row["slot_id"] in selected]}

    def poll_archive(self, job, now):
        if job.archive or job.export_error:
            return
        if job.archive_future and job.archive_future.done():
            try:
                job.archive = job.archive_future.result()
                self.history.insert(0, self.history_item(job.status, self.backend_state["mode"] == "mock_sap",
                                                         self.drone_model))
            except (OSError, KeyError, ValueError) as error:
                if job.attempts == 3:
                    job.export_error = str(error)
                job.finished_at = now
            job.archive_future = None
        if not job.archive_future and not job.archive and not job.export_error and now - job.finished_at >= .65:
            job.attempts += 1
            job.archive_future = self.pool.submit(self.make_archive, job)

    def poll_mission(self, job, now):
        stage = self.stage(job)
        if stage in TERMINAL:
            if not job.manual_token:
                self.poll_archive(job, now)
            return
        if stage == "ERROR":
            return
        if any(process.poll() is not None for process in job.processes):
            stop_workers(job.processes)
            job.error = "A mission worker stopped. Check the dispatch logs."
            return
        ready_to_start = stage == "WAITING" and (now-job.manual_at < COMMAND_AGE if job.manual_token else self.perception_frame_seen)
        if self.safety_enabled:
            status = self.safety_status()
            matching = status and status["inspection_id"] == job.run
            if matching and status["phase"] == "REJECTED":
                stop_workers(job.processes)
                job.error = status["message"]
                return
            ready_to_start = ready_to_start and matching and status["permit"]
        if stage in {"WAITING", "STARTING"} and now - job.created > 20:
            stop_workers(job.processes)
            job.error = "Mission start timed out. Check robot, perception and command ownership."
            return
        if job.command is not None:
            if not job.command.done():
                return
            job.command.result()
            job.command = None
        if now < job.next_command:
            return
        if job.abort_requested and job.status and self.abort_client.service_is_ready():
            job.command = self.abort_client.call_async(Trigger.Request())
        elif (not job.abort_requested and self.calibration.state in TRANSITIONING and self.calibration.owner == job.run
              and job.status.get("calibration_id") != self.calibration.draft["calibration_id"]):
            self.calibration_request.publish(String(data=json.dumps({"inspection_id": job.run,
                                                                     "calibration_id": self.calibration.draft["calibration_id"]})))
        elif (not job.abort_requested and self.calibration.state == (MAPPING if job.mapping_id else PRODUCTION)
              and ready_to_start and self.start_client.service_is_ready()):
            job.command = self.start_client.call_async(Trigger.Request())
        job.next_command = now + .6

    def tick(self):
        now = monotonic()
        if self.measured_map is not None:
            self.sample_live_scan(now)
        with self.lock:
            if self.health_future and self.health_future.done():
                self.backend_state = self.health_future.result()
                self.health_future = None
            if not self.health_future and now >= self.next_health:
                self.health_future = self.pool.submit(self.read_backend)
                self.next_health = now + 3.
            if self.job:
                self.poll_mission(self.job, now)
                if self.job.plan["quality"]:
                    source = self.data / "quality" / self.job.run
                    self.job.evidence = [json.loads(file.read_text()) for file in sorted(source.glob("*/report.json"))]
            self.tick_calibration(now)

    def frame(self, overview=False):
        with self.lock:
            if overview:
                return self.overview_jpeg if monotonic() - self.overview_at < 1.5 else None
            return self.jpeg if monotonic() - self.camera_at < 2 else None

    def snapshot(self):
        with self.lock:
            job = self.job
            safety = self.safety_status()
            energy = self.energy_state()
            odometry_age = monotonic() - self.odom_at
            current = None
            if job:
                current = {"inspection_id": job.run, "stage": self.stage(job), "slots": job.plan["slots"],
                           "mapping_id": job.mapping_id,
                           "quality": job.plan["quality"], "adaptive": job.plan["adaptive"],
                           "mode": job.plan["mode"], "status": job.status,
                           "warehouse_configuration_id": (job.plan["route"].get("learned") or {}).get("configuration_id"),
                           "planned": [] if job.manual_token else job.planned or
                           job.plan.get("display_points", job.plan["points"]), "flown": job.flown,
                           "evidence": job.evidence, "quality_uncertain": job.quality_uncertain,
                           "result": job.archive, "error": job.error or job.export_error}
            result = {"robot": odometry_age < 1.5, "at_pad": self.at_pad(), "busy": self.busy(),
                    "drone_model": self.drone_model,
                    "physical_dock": self.physical_dock(energy) if self.energy_enabled and
                    self.localization_mode == "sensor_based" else None,
                    "position_fresh": odometry_age <= .40, "speed": self.speed if odometry_age <= .40 else None,
                    "service_mode": self.calibration.state,
                    "calibration_full": bool((self.calibration.draft or {}).get("multi_sortie")),
                    "mapping_only": self.mapping_only,
                    "position": self.position, "orientation": self.orientation,
                    "energy": energy,
                    "backend": self.backend_state, "mission": current,
                    "camera": self.frame_number if self.jpeg and monotonic() - self.camera_at < 2 else None,
                    "camera_type": "raw", "history": self.history[:12],
                    "safety_enabled": self.safety_enabled, "safety": safety,
                    "last_reservation": (self.safety or {}).get("required", []) if safety is None else [],
                    "overview": monotonic() - self.overview_at < 1.5}
            if self.learned_mode:
                result["warehouse"] = self.warehouse_status()
            if self.recovery_enabled:
                recovery = job.recovery if job else None
                if job and safety and safety["phase"] == "RECOVERY" and monotonic()-job.recovery_at > .85:
                    recovery = {**(recovery or {}), "phase": "RECOVERY_FAILED", "inspection_id": job.run,
                                "cause": "COMMUNICATION_FAILURE", "detail": "Mission control heartbeat lost. Physical recovery required.",
                                "conditions": {}}
                result["recovery"] = recovery
                result["recovery_history"] = list(reversed(self.recovery_history.values()))[:12]
            if self.localization_mode != "ground_truth":
                value = self.localization
                if value and monotonic() - self.localization_at > .65:
                    value = {**value, "state": "LOST", "reason": "Localization heartbeat stopped advancing"}
                result["localization"] = value
                if self.localization_diagnostics:
                    result["localization_validation"] = self.pose_validation
            return result

    def close(self):
        if self.job:
            stop_workers(self.job.processes)
        if self.route_recording and not self.route_recording.done.is_set():
            self.route_recording.finish("INTERRUPTED", False, {})
            self.route_recording.worker.join(timeout=1.)
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.visualizations.close()


def main():
    # Camera frames are processed serially. Keep OpenCV from competing with ROS and Gazebo for cores.
    cv2.setNumThreads(1)
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    control = server = None
    try:
        control = Control()
        server = serve(control, control.port)
        Thread(target=server.serve_forever, daemon=True, name="control-http").start()
        control.get_logger().info(f"Control Center http://127.0.0.1:{control.port}/")
        rclpy.spin(control)
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if control:
            control.close()
            control.destroy_node()
        rclpy.try_shutdown()
