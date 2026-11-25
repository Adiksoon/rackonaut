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
from sensor_msgs.msg import Image
from std_msgs.msg import String
from std_srvs.srv import Trigger

from rackonaut_mission.report import TERMINAL, export, fetch_api
from rackonaut_safety.geometry import route_zones

from .planning import plan
from .web import serve


@dataclass
class Job:
    run: str
    plan: dict
    processes: list
    created: float = field(default_factory=monotonic)
    status: dict = field(default_factory=dict)
    planned: list = field(default_factory=list)
    flown: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
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
        self.marker_map = warehouse / "config/control_markers.json"
        self.lock = RLock()
        self.odom_at = 0.
        self.position, self.speed = None, 0.
        self.jpeg, self.camera_at, self.frame_number = None, 0., 0
        self.camera_type = "raw"
        self.safety, self.safety_at = None, -1e6
        self.overview_jpeg, self.overview_at = None, -1e6
        self.job = None
        self.history = self.load_history()
        self.backend_state = {"online": False, "mode": "", "slots": []}
        self.bridge = CvBridge()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="control-io")
        self.health_future = None
        self.next_health = 0.
        latest = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        if self.safety_enabled:
            self.safety_request = self.create_publisher(String, "/rackonaut/safety/request", 5)
            self.worker_control = self.create_publisher(String, "/rackonaut/safety/simulation/worker_target", 5)
            if self.laser_enabled:
                self.obstacle_control = self.create_publisher(String, "/rackonaut/safety/simulation/obstacle_target", 5)
            self.create_subscription(String, "/rackonaut/safety/state", self.on_safety, latest)
            self.create_subscription(Image, "/rackonaut/safety/overview", self.on_overview, qos_profile_sensor_data)
        self.create_subscription(Odometry, "/rackonaut/drone/odom", self.on_odom, qos_profile_sensor_data)
        self.create_subscription(String, "/rackonaut/mission/status", self.on_status, latest)
        self.create_subscription(RosPath, "/rackonaut/mission/plan", self.on_plan, latest)
        self.create_subscription(RosPath, "/rackonaut/mission/path", self.on_path, latest)
        self.create_subscription(Image, "/rackonaut/camera/image_raw", self.on_raw, qos_profile_sensor_data)
        self.create_subscription(Image, "/rackonaut/perception/annotated", self.on_annotated, 1)
        self.start_client = self.create_client(Trigger, "/rackonaut/mission/start")
        self.abort_client = self.create_client(Trigger, "/rackonaut/mission/abort")
        self.timer = self.create_timer(.1, self.tick, clock=Clock(clock_type=ClockType.STEADY_TIME))

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

    def on_odom(self, message):
        if message.header.frame_id != "rackonaut_odom":
            return
        p, q = message.pose.pose.position, message.pose.pose.orientation
        v = message.twist.twist.linear
        yaw = atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        with self.lock:
            self.position = [round(value, 3) for value in (p.x, p.y, p.z, yaw)]
            self.speed = hypot(v.x, v.y, v.z)
            self.odom_at = monotonic()

    def on_status(self, message):
        status = json.loads(message.data)
        with self.lock:
            if not self.job or status["inspection_id"] != self.job.run:
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
        if not self.job or not self.job.status or self.job.error:
            self.update_camera(message, "raw")

    def on_annotated(self, message):
        if self.job and self.job.status:
            self.update_camera(message, "annotated")

    def on_safety(self, message):
        with self.lock:
            self.safety, self.safety_at = json.loads(message.data), monotonic()

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
        if not isinstance(target, str) or target not in {"outside", "A", "B", "T"}:
            raise ValueError("Choose a marked simulation destination.")
        if not self.safety_enabled or not self.worker_control.get_subscription_count():
            raise RuntimeError("Simulation worker controls are unavailable.")
        self.worker_control.publish(String(data=target))
        return {"accepted": True}

    def move_obstacle(self, request):
        target = request.get("target")
        if not isinstance(target, str) or target not in {"forklift_a", "pallet_b", "clear"}:
            raise ValueError("Choose an available simulation obstacle action.")
        if not self.safety_enabled or not self.laser_enabled or not self.obstacle_control.get_subscription_count():
            raise RuntimeError("Simulation obstacle controls are unavailable.")
        self.obstacle_control.publish(String(data=target))
        return {"accepted": True}

    def update_camera(self, message, source):
        now = monotonic()
        if self.camera_type == source and now - self.camera_at < .09:
            return
        try:
            image = self.bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
            ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 77])
        except (CvBridgeError, cv2.error, RuntimeError):
            return
        if ok:
            with self.lock:
                self.jpeg, self.camera_type, self.camera_at = encoded.tobytes(), source, now
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
        if self.safety_enabled:
            route["required_zones"] = route_zones(route.get("safety_points", route["points"]), self.layout["safety_fields"])
        return route

    def begin(self, selection):
        planned = self.preview(selection)
        with self.lock:
            if self.busy():
                raise RuntimeError("Wait for the running inspection and its report.")
            if not self.at_pad():
                raise RuntimeError("The drone must be stopped on the launch pad before dispatch.")
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
                    "safety_interlock": str(self.safety_enabled).lower(),
                    "adaptive_quality": str(planned["adaptive"] and planned["quality"]).lower(),
                }))
            except OSError:
                stop_workers(processes)
                raise
            self.job = Job(run, planned, processes)
            self.jpeg, self.camera_type, self.camera_at = None, "raw", 0.
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
        export(snapshot, source, self.data / "reports")
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
        ready_to_start = stage == "WAITING" and self.camera_type == "annotated"
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
        elif not job.abort_requested and ready_to_start and self.start_client.service_is_ready():
            job.command = self.start_client.call_async(Trigger.Request())
        job.next_command = now + .6

    def tick(self):
        now = monotonic()
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

    def frame(self, overview=False):
        with self.lock:
            if overview:
                return self.overview_jpeg if monotonic() - self.overview_at < 1.5 else None
            return self.jpeg

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
                           "evidence": job.evidence, "result": job.archive, "error": job.error or job.export_error}
            return {"robot": monotonic() - self.odom_at < 1.5, "at_pad": self.at_pad(), "busy": self.busy(),
                    "position": self.position, "backend": self.backend_state, "mission": current,
                    "camera": self.frame_number if self.jpeg and monotonic() - self.camera_at < 2 else None,
                    "camera_type": self.camera_type, "history": self.history[:12],
                    "safety_enabled": self.safety_enabled, "safety": safety,
                    "last_reservation": (self.safety or {}).get("required", []) if safety is None else [],
                    "overview": monotonic() - self.overview_at < 1.5}

    def close(self):
        if self.job:
            stop_workers(self.job.processes)
        self.pool.shutdown(wait=True, cancel_futures=True)


def main():
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
