"""Synchronize ROS frames, publish the overlay and deliver stable readings asynchronously."""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

import cv2
import message_filters
import rclpy
from ament_index_python.packages import get_package_share_path
from cv_bridge import CvBridge
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .observations import StableReadings, observation, post_observation
from .overlay import OverlayState, render
from .quality import inspect_carton
from .quality_evidence import QualityEvidence
from .vision import Inspector, load_markers


class Perception(Node):
    def __init__(self):
        super().__init__("rackonaut_perception")
        default_markers = get_package_share_path("rackonaut_perception") / "config/markers.json"
        defaults = {
            "image_topic": "/rackonaut/camera/image_raw",
            "camera_info_topic": "/rackonaut/camera/camera_info",
            "annotated_topic": "/rackonaut/perception/annotated",
            "marker_map": str(default_markers),
            "inspection_id": datetime.now(timezone.utc).strftime("INS-%Y%m%d-%H%M%S"),
            "backend_url": "",
            "stable_frames": 4,
            "uncertain_frames": 8,
            "quality_enabled": False,
            "mission_scoped": False,
            "adaptive": False,
            "quality_dir": str(Path(os.environ.get("ROS_LOG_DIR", Path.home() / ".ros" / "log")) / "quality"),
        }
        parameters = {name: self.declare_parameter(name, value).value for name, value in defaults.items()}
        run_id = parameters["inspection_id"]
        if len(run_id) > 64 or not re.fullmatch(r"INS-[A-Z0-9]+(?:-[A-Z0-9]+)*", run_id):
            raise ValueError("inspection_id must follow the OpenAPI INS- identifier pattern.")
        if min(parameters["stable_frames"], parameters["uncertain_frames"]) < 1:
            raise ValueError("Stability requires at least one frame.")
        self.backend = parameters["backend_url"].strip().rstrip("/")
        if self.backend:
            endpoint = urlsplit(self.backend)
            if endpoint.scheme not in ("http", "https") or not endpoint.hostname or endpoint.query or endpoint.fragment:
                raise ValueError("backend_url must be the HTTP(S) base URL.")
        locations, pallets = load_markers(parameters["marker_map"])
        self.inspector = Inspector(locations, pallets)
        self.adaptive = parameters["adaptive"]
        self.gate = StableReadings(parameters["stable_frames"], parameters["uncertain_frames"], self.adaptive)
        self.mission_scoped = parameters["mission_scoped"]
        self.scan_slot = None
        self.scan_attempt = None
        if self.mission_scoped:
            qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
            self.create_subscription(String, "/rackonaut/mission/status", self.on_mission_status, qos)
        self.quality = QualityEvidence(parameters["quality_dir"], run_id, self.adaptive) if parameters["quality_enabled"] else None
        self.quality_events = None
        if self.adaptive and self.quality:
            self.quality_events = self.create_publisher(String, "/rackonaut/perception/quality_evidence", 10)
        self.uncertain_events = None
        self.uncertain_observations = set()
        if self.mission_scoped and self.quality:
            self.uncertain_events = self.create_publisher(String, "/rackonaut/perception/quality_uncertain", 5)
        self.inventory = {}
        self.state = OverlayState(run_id, total=len(locations))
        if self.backend:
            self.state.api_status, self.state.api_detail = "READY", "Waiting for a stable reading"
        self.bridge = CvBridge()
        # image_view's default subscriber requests reliable delivery. Only the
        # latest preview frame is useful when a viewer cannot keep up.
        self.output = self.create_publisher(Image, parameters["annotated_topic"], 1)
        self.images = message_filters.Subscriber(
            self, Image, parameters["image_topic"], qos_profile=qos_profile_sensor_data
        )
        self.calibration = message_filters.Subscriber(
            self, CameraInfo, parameters["camera_info_topic"], qos_profile=qos_profile_sensor_data
        )
        self.synchronizer = message_filters.TimeSynchronizer([self.images, self.calibration], 10)
        self.synchronizer.registerCallback(self.on_frame)
        self.executor_http = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rackonaut-http")
        self.pending = {}
        self.inspected = set()
        self.last_frame = None
        self.preview_service = self.create_service(Trigger, "~/rearm", self.rearm)
        self.get_logger().info(f"Inspecting {parameters['image_topic']} as {run_id}")

    def on_mission_status(self, message):
        status = json.loads(message.data)
        if status["inspection_id"] != self.state.inspection_id:
            return
        self.state.total = status["total"]
        scan_stages = {"INSPECT", "REINSPECT", "QUALITY_CLOSEUP"} if self.adaptive else {"INSPECT"}
        self.scan_slot = status["target"] if status["stage"] in scan_stages else None
        if self.adaptive:
            key = (self.scan_slot, status["adaptive"]["attempt"]) if self.scan_slot else None
            if key != self.scan_attempt:
                self.scan_attempt = key
                self.gate.rearm()
                if key:
                    self.inventory.pop(self.scan_slot, None)
                if self.quality:
                    self.quality.frames.clear()

    def rearm(self, request, response):
        self.gate.rearm()
        response.success = True
        response.message = "Ready to record fresh stable readings for this inspection."
        return response

    def collect_http(self):
        for future, event in list(self.pending.items()):
            if not future.done():
                continue
            del self.pending[future]
            success, message = future.result()
            slot = event["slot_id"]
            if success:
                self.state.api_status, self.state.api_detail = "SENT", f"{slot} accepted ({message})"
                self.get_logger().info(f"API {message} {slot} {event['observation_id']}")
            else:
                self.state.api_status, self.state.api_detail = "ERROR", f"{slot} / {message}"
                self.get_logger().warning(f"{message} for {slot}. Live vision continues. Rearm to record again.")

    def publish_uncertain(self, verdicts):
        for (slot, pallet, verdict), count in self.quality.frames.items():
            event = self.inventory.get(slot)
            if (verdict == "UNCERTAIN" and count >= 4 and event and event["pallet_id"] == pallet
                    and event["observation_id"] not in self.uncertain_observations):
                self.uncertain_observations.add(event["observation_id"])
                self.uncertain_events.publish(String(data=json.dumps({
                    "inspection_id": event["inspection_id"], "slot_id": slot,
                    "observation_id": event["observation_id"], "reason": verdicts[slot].reason,
                })))

    def on_frame(self, image, info):
        if (image.header.frame_id != info.header.frame_id or not image.header.frame_id
                or (image.width, image.height) != (info.width, info.height) or info.k[0] <= 0):
            return
        captured = datetime.now(timezone.utc)
        now = monotonic()
        if self.last_frame is not None and now > self.last_frame:
            current_fps = 1 / (now - self.last_frame)
            self.state.fps = .85 * self.state.fps + .15 * current_fps if self.state.fps else current_fps
        self.last_frame = now
        self.collect_http()
        try:
            native = self.bridge.imgmsg_to_cv2(image, "bgr8")
        except (TypeError, RuntimeError, ValueError) as error:
            self.get_logger().warning(f"Cannot convert camera frame: {error}", throttle_duration_sec=3.0)
            return
        result = self.inspector.inspect(native)
        eligible = result.readings
        if self.mission_scoped:
            eligible = [reading for reading in eligible if reading.slot.name == self.scan_slot]
        readings = [] if self.adaptive and self.scan_slot in self.gate.recorded else self.gate.update(eligible, now)
        for reading in readings:
            if self.backend and len(self.pending) >= 8:
                break
            payload = observation(self.state.inspection_id, reading, captured)
            self.gate.record(reading)
            self.inspected.add(payload["slot_id"])
            if self.quality is not None:
                self.inventory[payload["slot_id"]] = payload
            self.get_logger().info(
                f"Observation {payload['slot_id']}: {payload['occupancy']} / {payload['label_status']} / "
                f"{payload['pallet_id'] or '-'}"
            )
            if self.backend:
                future = self.executor_http.submit(post_observation, self.backend, payload)
                self.pending[future] = payload
                self.state.api_status, self.state.api_detail = "SENDING", f"{payload['slot_id']} queued"
        self.state.inspected = len(self.inspected)
        if self.quality is None:
            panel = render(native, result, self.state)
        else:
            verdicts = {reading.slot.name: inspect_carton(native, reading) for reading in result.readings
                        if reading.classification.occupancy != "empty"}
            ready = self.quality.ready(verdicts, eligible, self.inventory, now)
            if self.uncertain_events:
                self.publish_uncertain(verdicts)
            panel = render(native, result, self.state, verdicts, self.quality.damage_count(ready))
            for item in ready:
                try:
                    path = self.quality.save(item, native, panel, captured, image.header)
                except (OSError, cv2.error) as error:
                    self.quality.retry_at = now + 1.
                    self.get_logger().warning(f"Cannot save quality evidence: {error}", throttle_duration_sec=3.0)
                    break
                key, verdict, observation_event = item
                if self.quality_events:
                    self.quality_events.publish(String(data=json.dumps({
                        "inspection_id": self.state.inspection_id, "slot_id": key[0],
                        "observation_id": observation_event["observation_id"], "status": verdict.status,
                        "quality_id": path.name,
                    })))
                self.get_logger().info(f"Quality {verdict.status} {key[0]} / {key[1] or '-'} "
                                       f"{path.name} linked to {observation_event['observation_id']}")
        annotated = self.bridge.cv2_to_imgmsg(panel, "bgr8")
        annotated.header = image.header
        self.output.publish(annotated)

    def close(self):
        self.executor_http.shutdown(wait=True, cancel_futures=True)


def main():
    # Camera frames are processed serially. Keep OpenCV from competing with ROS and Gazebo for cores.
    cv2.setNumThreads(1)
    rclpy.init()
    node = None
    try:
        node = Perception()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.close()
            node.destroy_node()
        rclpy.try_shutdown()
