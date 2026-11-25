"""Synchronize ROS frames, publish the overlay and deliver stable readings asynchronously."""

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
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
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
        self.gate = StableReadings(parameters["stable_frames"], parameters["uncertain_frames"])
        self.quality = QualityEvidence(parameters["quality_dir"], run_id) if parameters["quality_enabled"] else None
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
        for reading in self.gate.update(result.readings, now):
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
            ready = self.quality.ready(verdicts, result.readings, self.inventory, now)
            panel = render(native, result, self.state, verdicts, self.quality.damage_count(ready))
            for item in ready:
                try:
                    path = self.quality.save(item, native, panel, captured, image.header)
                except (OSError, cv2.error) as error:
                    self.quality.retry_at = now + 1.
                    self.get_logger().warning(f"Cannot save quality evidence: {error}", throttle_duration_sec=3.0)
                    break
                key, verdict, observation_event = item
                self.get_logger().info(f"Quality {verdict.status} {key[0]} / {key[1] or '-'} "
                                       f"{path.name} linked to {observation_event['observation_id']}")
        annotated = self.bridge.cv2_to_imgmsg(panel, "bgr8")
        annotated.header = image.header
        self.output.publish(annotated)

    def close(self):
        self.executor_http.shutdown(wait=True, cancel_futures=True)


def main():
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
