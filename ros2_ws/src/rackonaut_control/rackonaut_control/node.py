"""Keep the browser connected to one ROS-controlled inspection at a time."""

import json
import os
import signal
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import atan2, hypot
from pathlib import Path
from threading import RLock, Thread
from time import monotonic
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

from rackonaut_avoidance.sensor import Scanner
from rackonaut_mission.report import TERMINAL, export, fetch_api
from rackonaut_safety.geometry import route_zones

from .measured_map import ESTIMATE_TOPIC, FRAME, MAP_TOPIC, MeasuredMap, Sample
from .planning import energy_forecast, plan
from .service import BLOCKED, PRODUCTION, READY, RECOVERY, TRANSITIONING, Calibration, ServiceAccess
from .web import serve


@dataclass
class Job:
    run: str
    plan: dict
    processes: list
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
        self.laser_enabled = self.declare_parameter("safety_sensor", "virtual").value == "laser"
        self.backend = self.declare_parameter("backend_url", "http://127.0.0.1:8000").value.rstrip("/")
        self.data = Path(self.declare_parameter("data_dir", "control").value).expanduser().resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        self.web = get_package_share_path("rackonaut_control") / "web"
        warehouse = get_package_share_path("rackonaut_warehouse")
        self.layout = json.loads((warehouse / "config/control_layout.json").read_text())
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
        self.measured_map = MeasuredMap() if self.localization_mode == "sensor_based" else None
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
                profile = json.loads((warehouse / "config/aerial_layout.json").read_text())
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
        self.calibration_supported = (self.aerial_enabled and self.avoidance_enabled and self.safety_enabled
                                      and self.recovery_enabled and self.energy_enabled
                                      and self.localization_mode == "sensor_based")
        if self.calibration_supported:
            self.calibration_request = self.create_publisher(String, "/rackonaut/calibration/request", 5)
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
            self.scan_decoder = Scanner(self, exact_pose=True)
            self.create_subscription(PointCloud2, MAP_TOPIC, self.measured_map.accept, qos_profile_sensor_data)
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
            if self.measured_map is not None and self.localization:
                if state.get("accepted", 0) < self.localization.get("accepted", 0):
                    self.measured_map.new_session()
            self.localization, self.localization_at = state, monotonic()

    def on_scan_tf(self, message):
        if any(transform.header.frame_id == FRAME and transform.child_frame_id == "rackonaut_base_link"
               for transform in message.transforms):
            self.scan_tf_at = monotonic()

    def latest_scan(self):
        self.scan_requested_until = monotonic() + 1.8
        sample = self.scan_sample
        return sample if sample and sample.session == self.measured_map.session and sample.age_ms <= 850 else None

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
        session = self.measured_map.session
        if sample and (sample.session, sample.stamp) == (session, stamp):
            return
        self.scan_sample = Sample(stamp, session, cloud.received, datetime.now(timezone.utc).isoformat(),
                                  cloud.hits.astype("<f4").tobytes())

    def on_pose_validation(self, message):
        self.pose_validation = json.loads(message.data)

    def load_history(self):
        result = []
        for file in sorted((self.data / "reports").glob("*/run.json"), reverse=True)[:12]:
            value = json.loads(file.read_text())["mission"]
            result.append(self.history_item(value))
        return result

    @staticmethod
    def history_item(status):
        run = status["inspection_id"]
        return {"run": run, "stage": status["stage"], "landed": status["landed"],
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
            return self.job.archive is None and not self.job.export_error
        return stage != "ERROR"

    def preview(self, selection):
        route = plan(self.layout, selection)
        if self.safety_enabled and not self.aerial_enabled:
            route["required_zones"] = route_zones(route.get("safety_points", route["points"]), self.layout["safety_fields"])
        if self.energy_enabled:
            route["route"]["energy_crossing_x"] = self.layout["crossing_x"]
            route["route"]["energy_zones"] = route["required_zones"]
            telemetry = self.energy_state()
            route["energy"] = energy_forecast(self.layout, route, telemetry) if telemetry and telemetry["fresh"] else None
        return route

    def begin(self, selection):
        planned = self.preview(selection)
        with self.lock:
            if self.calibration.state != PRODUCTION:
                raise RuntimeError("Warehouse calibration is active. New inspections are locked.")
            if self.busy():
                raise RuntimeError("Wait for the running inspection and its report.")
            if self.localization_mode == "sensor_based" and (
                    not self.localization or monotonic() - self.localization_at > .40
                    or self.localization.get("state") != "TRACKING"):
                raise RuntimeError("Wait for reliable sensor-based localization.")
            if not self.at_pad():
                raise RuntimeError("The drone must be stopped on the launch pad before dispatch.")
            if self.energy_enabled:
                telemetry = self.energy_state()
                if not telemetry or not telemetry["fresh"] or not telemetry["contact"]:
                    raise RuntimeError("Fresh battery data and confirmed dock position are required.")
                forecast = energy_forecast(self.layout, planned, telemetry)
                if not forecast["can_start"]:
                    raise RuntimeError(f"Insufficient energy for the first stop and safe return ({forecast['minimum_percent']:.1f}% required).")
            if not self.backend_state["online"]:
                raise RuntimeError("The inventory API is unavailable.")
            missing = set(planned["slots"]) - set(self.backend_state["slots"])
            if missing:
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
                }))
            except OSError:
                stop_workers(processes)
                raise
            self.job = Job(run, planned, processes)
            self.perception_frame_seen = False
            if self.safety_enabled:
                points = planned.get("safety_points", planned["points"])
                self.safety_request.publish(String(data=json.dumps({"inspection_id": run, "points": points})))
            return {"inspection_id": run}

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
        contact = (energy.get("fresh") is True and energy.get("contact") is True
                   and energy.get("switch_engaged") is True and energy.get("contact_source") == "gazebo_dock_switch")
        job = self.job
        stage = self.stage(job) if job else None
        return {"connection": connection, "localization": (localization or {}).get("state", "UNAVAILABLE"),
                "lidar": lidar, "imu": imu, "camera": camera, "contact": contact, "dock": energy.get("dock"),
                "battery": energy.get("percent") if energy.get("fresh") else None,
                "safety": safety.get("phase", "UNAVAILABLE"), "safety_sensors": safety.get("sensor"),
                "drone": ("DOCKED" if contact else "IN_FLIGHT" if connection and not self.at_pad()
                          else "AT_PAD" if connection else "UNAVAILABLE"),
                "mission": {"inspection_id": job.run, "stage": stage} if job else None,
                "position": self.position if connection else None, "speed": self.speed if connection else None}

    def service_snapshot(self):
        with self.lock:
            return {"available": self.calibration_supported,
                    "system": self.service_telemetry(monotonic()), "calibration": self.calibration.snapshot(),
                    "warehouse": {"profile": "Protected aerial" if self.aerial_enabled else "Showcase reference",
                                  "map_source": "Preconfigured reference warehouse geometry",
                                  "map": ("localization_map.json" if self.localization_mode == "sensor_based"
                                          else "Control Center reference layout"),
                                  "locations": len(self.layout["slots"]), "status": "ACTIVE"}}

    def start_calibration(self, request):
        warehouse = request.get("warehouse_name")
        if warehouse is not None and (not isinstance(warehouse, str) or len(warehouse) > 100):
            raise ValueError("Use at most 100 characters for the optional warehouse name.")
        with self.lock:
            if not self.calibration_supported:
                raise RuntimeError("Calibration requires the Full Robotics profile with sensor localization and Recovery.")
            if self.calibration.state != PRODUCTION:
                raise RuntimeError("A calibration is already active.")
            job = self.job
            active = job and self.stage(job) not in TERMINAL | {"ERROR"}
            safety = self.safety_status()
            if safety and safety["phase"] == "RECOVERY":
                raise RuntimeError("Resolve the current incident in the Recovery Center first.")
            if job is None and self.start_client.service_is_ready():
                raise RuntimeError("An independent Mission Manager is present. It must be stopped first.")
            self.calibration.start(warehouse.strip() or None if warehouse else None,
                                   job.run if active else None, monotonic())
            return self.calibration.snapshot()

    def cancel_calibration(self, _request):
        with self.lock:
            if self.calibration.state == PRODUCTION:
                raise RuntimeError("No active calibration.")
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
        if stable and calibration.cancel_pending:
            try:
                calibration.clear()
            except OSError as error:
                calibration.set_state(BLOCKED, f"The calibration draft could not be cleared: {error.strerror}.")
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
            if calibration.state == "PREPARING_CALIBRATION":
                calibration.set_state(READY, "Physical dock confirmed. The new warehouse draft is ready.")
            else:
                calibration.set_state("PREPARING_CALIBRATION", "Preparing a new warehouse draft at the physical dock.")
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
        snapshot = {"mission": job.status, "api": api}
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
                self.history.insert(0, self.history_item(job.status))
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
            self.poll_archive(job, now)
            return
        if stage == "ERROR":
            return
        if any(process.poll() is not None for process in job.processes):
            stop_workers(job.processes)
            job.error = "A mission worker stopped. Check the dispatch logs."
            return
        ready_to_start = stage == "WAITING" and self.perception_frame_seen
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
        elif (not job.abort_requested and self.calibration.state == PRODUCTION
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
            current = None
            if job:
                current = {"inspection_id": job.run, "stage": self.stage(job), "slots": job.plan["slots"],
                           "quality": job.plan["quality"], "adaptive": job.plan["adaptive"],
                           "mode": job.plan["mode"], "status": job.status,
                           "planned": job.planned or job.plan["points"], "flown": job.flown,
                           "evidence": job.evidence, "quality_uncertain": job.quality_uncertain,
                           "result": job.archive, "error": job.error or job.export_error}
            result = {"robot": monotonic() - self.odom_at < 1.5, "at_pad": self.at_pad(), "busy": self.busy(),
                    "service_mode": self.calibration.state,
                    "position": self.position, "orientation": self.orientation,
                    "energy": self.energy_state(),
                    "backend": self.backend_state, "mission": current,
                    "camera": self.frame_number if self.jpeg and monotonic() - self.camera_at < 2 else None,
                    "camera_type": "raw", "history": self.history[:12],
                    "safety_enabled": self.safety_enabled, "safety": safety,
                    "last_reservation": (self.safety or {}).get("required", []) if safety is None else [],
                    "overview": monotonic() - self.overview_at < 1.5}
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
        self.pool.shutdown(wait=True, cancel_futures=True)


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
