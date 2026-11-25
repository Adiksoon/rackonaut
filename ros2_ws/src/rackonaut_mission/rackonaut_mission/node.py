"""Run an odometry-guided inspection in the reference simulation."""

import json
import re
import signal
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from math import atan2, dist, hypot, isfinite
from time import monotonic
from urllib.parse import urlsplit

import rclpy
from ament_index_python.packages import get_package_share_path
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry, Path
from rclpy.clock import Clock, ClockType
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from std_msgs.msg import String
from std_srvs.srv import Trigger
from visualization_msgs.msg import MarkerArray

from .confirmation import current_observation, fetch_observations
from .route import Target, heading_error, load_route, velocity
from .visualization import make_markers, planned_path, stamped_pose


MISSION = "/rackonaut/mission"
TERMINAL = {"COMPLETE", "COMPLETE_WITH_MISSES", "ABORTED"}


class Mission(Node):
    def __init__(self):
        super().__init__("rackonaut_mission")
        share = get_package_share_path("rackonaut_mission")
        defaults = {
            "route_file": str(share / "config/showcase.json"),
            "inspection_id": "INS-MISSION",
            "backend_url": "http://127.0.0.1:8000",
            "odom_topic": "/rackonaut/drone/odom",
            "cmd_vel_topic": "/rackonaut/drone/cmd_vel",
            "odom_frame": "rackonaut_odom",
            "rearm_service": "/rackonaut_perception/rearm",
            "autostart": False,
            "land": True,
            "travel_timeout": 38.0,
            "inspection_timeout": 8.0,
            "scan_hold_seconds": 0.0,
        }
        settings = {key: self.declare_parameter(key, value).value for key, value in defaults.items()}
        self.inspection_id = settings["inspection_id"]
        if len(self.inspection_id) > 64 or not re.fullmatch(r"INS-[A-Z0-9]+(?:-[A-Z0-9]+)*", self.inspection_id):
            raise ValueError("inspection_id must follow the OpenAPI INS- identifier pattern.")
        self.backend = settings["backend_url"].rstrip("/")
        url = urlsplit(self.backend)
        if url.scheme not in ("http", "https") or not url.hostname or url.query or url.fragment:
            raise ValueError("backend_url must be the HTTP(S) base URL.")
        self.travel_timeout, self.inspection_timeout = settings["travel_timeout"], settings["inspection_timeout"]
        if not all(isfinite(value) and value > 0 for value in (self.travel_timeout, self.inspection_timeout)):
            raise ValueError("Mission timeouts must be finite and positive.")
        self.scan_hold = settings["scan_hold_seconds"]
        if not 0. <= self.scan_hold < self.inspection_timeout:
            raise ValueError("The minimum scan hold must be below the inspection timeout.")

        self.route = load_route(settings["route_file"])
        self.frame = settings["odom_frame"]
        self.command_topic = settings["cmd_vel_topic"]
        self.autostart = settings["autostart"]
        self.land = settings["land"]
        self.odometry = self.create_subscription(Odometry, settings["odom_topic"], self.on_odom, qos_profile_sensor_data)
        self.rearm_client = self.create_client(Trigger, settings["rearm_service"])
        self.create_service(Trigger, f"{MISSION}/start", self.on_start)
        self.create_service(Trigger, f"{MISSION}/abort", self.on_abort)
        latest = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.status_pub = self.create_publisher(String, f"{MISSION}/status", latest)
        self.plan_pub = self.create_publisher(Path, f"{MISSION}/plan", latest)
        self.path_pub = self.create_publisher(Path, f"{MISSION}/path", latest)
        self.markers_pub = self.create_publisher(MarkerArray, f"{MISSION}/markers", latest)
        self.plan_pub.publish(planned_path(self.route, self.frame, self.land))
        self.track = Path()
        self.track.header.frame_id = self.frame

        self.command = None
        self.pose, self.odom_stamp = None, None
        self.odom_at = self.speed = 0.0
        self.stage = "WAITING"
        self.started = self.ended = self.settled_since = None
        self.created = self.stage_since = monotonic()
        self.status_at = self.track_at = 0.0
        self.detail = "Waiting for a mission start"
        self.target = self.route.pad
        self.stop_index = 0
        self.visits, self.confirmed, self.missed = [], {}, []
        self.landed = False

        self.http = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rackonaut-mission-http")
        self.http_request = self.rearm_request = self.capture_after = None
        self.poll_at = 0.0
        self.control_timer = self.create_timer(.1, self.tick, clock=Clock(clock_type=ClockType.STEADY_TIME))

    def on_odom(self, message):
        if message.header.frame_id != self.frame or message.child_frame_id != "rackonaut_base_link":
            return
        stamp = message.header.stamp
        key = (stamp.sec, stamp.nanosec)
        if self.odom_stamp is not None and key <= (self.odom_stamp.sec, self.odom_stamp.nanosec):
            return
        p, q = message.pose.pose.position, message.pose.pose.orientation
        v = message.twist.twist.linear
        if not all(isfinite(value) for value in (p.x, p.y, p.z, q.x, q.y, q.z, q.w, v.x, v.y, v.z)):
            return
        yaw = atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        self.pose, self.odom_stamp = Target(p.x, p.y, p.z, yaw), stamp
        self.speed, self.odom_at = hypot(v.x, v.y, v.z), monotonic()

    def readiness(self, now):
        if self.pose is None or now - self.odom_at > .65:
            return f"Waiting for fresh odometry in {self.frame}"
        if self.count_publishers(self.command_topic):
            return f"A command publisher already owns {self.command_topic}"
        if not self.count_subscribers(self.command_topic):
            return "Waiting for a drone command subscriber"
        if not self.rearm_client.service_is_ready():
            return "Waiting for the perception rearm service"
        p, pad = self.pose, self.route.pad
        if hypot(p.x - pad.x, p.y - pad.y) > .28 or abs(p.z - pad.z) > .15 or self.speed > .12:
            return "Place the stopped drone on the configured launch pad"
        return ""

    def start(self, now):
        if self.stage != "WAITING":
            return f"Mission is {self.stage}. Start a new process with a new inspection ID."
        reason = self.readiness(now)
        if reason:
            return reason
        self.command = self.create_publisher(Twist, self.command_topic, 10)
        self.started = now
        self.transition("TAKEOFF", self.route.takeoff, now, "Climbing above the launch pad")
        return ""

    def on_start(self, _request, response):
        reason = self.start(monotonic())
        response.success = not reason
        response.message = reason or f"Started {self.inspection_id}"
        return response

    def on_abort(self, _request, response):
        response.success = self.stage not in TERMINAL
        if response.success:
            self.finish("ABORTED", "Stopped by the operator", monotonic())
        response.message = self.detail
        return response

    def transition(self, stage, target, now, detail):
        self.stage, self.target, self.stage_since, self.detail = stage, target, now, detail
        self.settled_since = None
        self.get_logger().info(f"{stage} {target.slot_id or 'PAD'} | {detail}")

    def send_velocity(self):
        x, y, z, yaw_rate = velocity(self.target, self.pose)
        command = Twist()
        command.linear.x, command.linear.y, command.linear.z = x, y, z
        command.angular.z = yaw_rate
        self.command.publish(command)

    def stable(self, now, duration=.45, touchdown=False):
        p, goal = self.pose, self.target
        horizontal = hypot(p.x - goal.x, p.y - goal.y)
        altitude = p.z <= self.route.pad.z + .018 if touchdown else abs(p.z - goal.z) <= .06
        if horizontal <= .065 and altitude and abs(heading_error(goal.yaw, p.yaw)) <= .055 and self.speed <= .11:
            if self.settled_since is None:
                self.settled_since = now
            return now - self.settled_since >= duration
        self.settled_since = None
        return False

    def next_stop(self, now):
        if self.stop_index == len(self.route.waypoints):
            self.transition("RETURN", self.route.takeoff, now, "Returning along the clear aisle to the pad")
            return
        stop = self.route.waypoints[self.stop_index]
        if stop.slot_id:
            self.transition("TRANSIT", replace(stop, yaw=self.target.yaw), now, "Flying to the inspection viewpoint")
        else:
            self.transition("CORRIDOR", stop, now, "Following the clear transfer corridor")

    def begin_scan(self, now):
        slot = self.target.slot_id
        self.visits.append(slot)
        self.transition("INSPECT", self.target, now, "Waiting for a fresh camera observation in the API")
        self.capture_after = datetime.now(timezone.utc)
        self.rearm_request = self.rearm_client.call_async(Trigger.Request())
        self.poll_at = now

    def scan(self, now):
        slot = self.target.slot_id
        if slot in self.confirmed:
            if now - self.stage_since >= self.scan_hold:
                self.end_scan(now)
            return
        if self.rearm_request.done() and self.rearm_request.result().success:
            if self.http_request is not None and self.http_request.done():
                events, problem = self.http_request.result()
                self.http_request = None
                self.detail = problem or "Waiting for a fresh camera observation in the API"
                seen = {event["observation_id"] for event in self.confirmed.values()}
                event = current_observation(events, self.inspection_id, slot, self.capture_after, seen)
                if event is not None:
                    self.confirmed[slot] = event
                    self.get_logger().info(f"CONFIRMED {slot} {event['occupancy']} "
                                           f"{event.get('pallet_id') or '-'} {event['observation_id']}")
                    if now - self.stage_since >= self.scan_hold:
                        self.end_scan(now)
                    return
            if self.http_request is None and now >= self.poll_at:
                self.http_request = self.http.submit(fetch_observations, self.backend, self.inspection_id)
                self.poll_at = now + .45
        if now - self.stage_since >= self.inspection_timeout:
            self.missed.append(slot)
            self.get_logger().warning(f"MISSED {slot} | No fresh API confirmation within the hold")
            self.end_scan(now)

    def end_scan(self, now):
        if not self.rearm_request.done():
            self.rearm_client.remove_pending_request(self.rearm_request)
        self.rearm_request = None
        # A previous GET may still be running. Keep one worker/request, and
        # apply the next slot's own UTC cutoff before accepting any event.
        self.stop_index += 1
        self.next_stop(now)

    def finish(self, result, detail, now, competing=False):
        if self.command is not None:
            if not competing and self.count_publishers(self.command_topic) <= 1:
                self.command.publish(Twist())
                self.command.wait_for_all_acked(Duration(seconds=.18))
            self.destroy_publisher(self.command)
            self.command = None
        self.ended = now
        self.transition(result, self.target, now, detail)
        self.publish_state(now)

    def advance(self, now):
        if self.stage == "INSPECT":
            self.scan(now)
            return
        if now - self.stage_since >= self.travel_timeout:
            self.finish("ABORTED", f"Motion timed out at {self.stage}", now)
            return
        if not self.stable(now, duration=.65 if self.stage == "ALIGN" else .45, touchdown=self.stage == "LAND"):
            return
        if self.stage == "TAKEOFF":
            self.next_stop(now)
        elif self.stage == "CORRIDOR":
            self.stop_index += 1
            self.next_stop(now)
        elif self.stage == "TRANSIT":
            self.transition("ALIGN", self.route.waypoints[self.stop_index], now, "Turning toward the rack and settling")
        elif self.stage == "ALIGN":
            self.begin_scan(now)
        elif self.stage == "RETURN" and self.land:
            touchdown = replace(self.route.pad, z=max(0., self.route.pad.z - .05))
            self.transition("LAND", touchdown, now, "Descending onto the launch pad")
        else:
            self.landed = self.stage == "LAND"
            result = "COMPLETE_WITH_MISSES" if self.missed else "COMPLETE"
            self.finish(result, "Landed on the launch pad" if self.landed else "Holding above the launch pad", now)

    def tick(self):
        now = monotonic()
        if self.stage == "WAITING" and self.autostart:
            self.detail = self.start(now) or self.detail
            if self.stage == "WAITING" and now - self.created > 25.0:
                self.finish("ABORTED", self.detail, now)
        if self.command is not None:
            if self.count_publishers(self.command_topic) > 1:
                self.finish("ABORTED", "Another publisher claimed the command topic", now, competing=True)
            elif now - self.odom_at > .65:
                self.finish("ABORTED", "Odometry stopped advancing", now)
            else:
                if not self.track.poses or now - self.track_at >= .20:
                    self.track.poses.append(stamped_pose(self.pose, self.frame, self.odom_stamp))
                    self.track.header.stamp = self.odom_stamp
                    self.track_at = now
                self.send_velocity()
                self.advance(now)
        if now - self.status_at >= .25:
            self.publish_state(now)

    def publish_state(self, now):
        elapsed = (now if self.ended is None else self.ended) - self.started if self.started is not None else 0.0
        status = {
            "inspection_id": self.inspection_id,
            "stage": self.stage,
            "target": self.target.slot_id or ("CORRIDOR" if self.stage == "CORRIDOR" else "PAD"),
            "target_pose": [round(value, 3) for value in (self.target.x, self.target.y, self.target.z, self.target.yaw)],
            "position": [round(value, 3) for value in (self.pose.x, self.pose.y, self.pose.z, self.pose.yaw)]
            if self.pose is not None else None,
            "elapsed_seconds": round(elapsed, 1),
            "total": len(self.route.stops),
            "planned_slots": [stop.slot_id for stop in self.route.stops],
            "visited": self.visits,
            "confirmed": self.confirmed,
            "missed": self.missed,
            "landed": self.landed,
            "detail": self.detail,
        }
        self.status_pub.publish(String(data=json.dumps(status, separators=(",", ":"))))
        if self.track.poses:
            self.path_pub.publish(self.track)
        self.markers_pub.publish(make_markers(self.route, self.pose, self.frame, status))
        self.status_at = now

    def close(self):
        if self.command is not None:
            self.finish("ABORTED", "Mission process stopped", monotonic())
        self.http.shutdown(wait=True, cancel_futures=True)


def main():
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    node = None
    try:
        node = Mission()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.close()
            node.destroy_node()
        rclpy.try_shutdown()
