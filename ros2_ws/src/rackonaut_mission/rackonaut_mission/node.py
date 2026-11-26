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
from std_msgs.msg import Bool, String
from std_srvs.srv import Trigger
from visualization_msgs.msg import MarkerArray
from rackonaut_avoidance.planner import DETOUR_SCALE, Navigator, sweep
from rackonaut_avoidance.sensor import MAX_RANGE, Scanner
from rackonaut_energy.aerial import Leg, interval
from rackonaut_energy.model import Model, dock_path, estimate, first_requirement, sortie_path

from .adaptive import (MAX_RETRIES, QUALITY_SECONDS, RETRY_SECONDS, RETRY_TEXT, RETURN_MARGIN,
                       first_unused, next_issue, reading_issue)
from .confirmation import current_observation, fetch_observations
from .recovery import ACTIVE as RECOVERY_ACTIVE, FAILED as RECOVERY_FAILED, Recovery
from .route import Target, heading_error, load_route, velocity
from .visualization import make_markers, planned_path, stamped_pose


MISSION = "/rackonaut/mission"
TERMINAL = {"COMPLETE", "COMPLETE_WITH_MISSES", "ABORTED"}
DOCK_WAIT = {"CHARGING", "READY_TO_RESUME"}
AERIAL_MOTION = {"ENTERING_CORRIDOR", "OVERHEAD_TRANSIT", "AISLE_DESCENT", "AISLE_ASCENT", "AISLE_APPROACH",
                 "RETURN_TRANSIT"}


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
            "safety_interlock": False,
            "adaptive_quality": False,
            "obstacle_avoidance": False,
            "sensor_localization": False,
            "recovery_dir": "",
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
        self.aerial = self.route.aerial
        self.sensor_localization = settings["sensor_localization"]
        self.localization, self.localization_at = {}, -1e6
        self.navigation = Navigator() if settings["obstacle_avoidance"] else None
        if self.navigation and not self.aerial:
            raise ValueError("Local obstacle avoidance requires a reserved aerial route.")
        self.scanner = Scanner(self, exact_pose=self.sensor_localization) if self.navigation else None
        self.frame = settings["odom_frame"]
        self.command_topic = settings["cmd_vel_topic"]
        self.autostart = settings["autostart"]
        self.land = settings["land"]
        self.odometry = self.create_subscription(Odometry, settings["odom_topic"], self.on_odom, qos_profile_sensor_data)
        self.rearm_client = self.create_client(Trigger, settings["rearm_service"])
        self.create_service(Trigger, f"{MISSION}/start", self.on_start)
        self.create_service(Trigger, f"{MISSION}/abort", self.on_abort)
        latest = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        if self.sensor_localization:
            if not self.scanner:
                raise ValueError("Sensor localization requires onboard obstacle avoidance.")
            self.create_subscription(Odometry, "/rackonaut/localization/estimate",
                                     self.scanner.odometry, qos_profile_sensor_data)
            self.create_subscription(String, "/rackonaut/localization/state", self.on_localization, latest)
        self.safety_interlock = settings["safety_interlock"]
        self.safety_at, self.safety_permit = -1e6, False
        self.permit_departure = None
        self.safety_phase, self.safety_zones = "", set()
        self.descents, self.pending_descent = {}, None
        self.safety_alarm, self.safety_recovery = None, {}
        self.adaptive = bool(self.route.retries)
        self.energy_enabled = self.route.crossing is not None
        if self.energy_enabled and (not self.safety_interlock or not self.land):
            raise ValueError("Energy missions must land with the Safety Manager enabled.")
        self.battery, self.battery_at, self.energy_model = {}, -1e6, None
        self.departures = 0
        self.sorties, self.completed, self.interruptions = [], [], []
        self.return_legs, self.resume_legs, self.return_track = [], [], []
        self.return_reason = ""
        self.obstacle_retreat = False
        self.resume_index = None
        self.last_charge_progress = None
        if self.energy_enabled:
            self.create_subscription(String, "/rackonaut/energy/state", self.on_energy, latest)
        if self.adaptive and not self.safety_interlock:
            raise ValueError("Adaptive routes require the Safety Manager.")
        self.adaptive_quality = settings["adaptive_quality"] and self.adaptive
        self.evidence = {}
        if self.adaptive_quality:
            self.create_subscription(String, "/rackonaut/perception/quality_evidence", self.on_quality, 10)
        if self.safety_interlock:
            self.create_subscription(String, "/rackonaut/safety/state", self.on_safety, latest)
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
        self.attempts, self.moves, self.resolved, self.manual_review = [], [], [], {}
        self.retry_number = self.total_retries = 0
        self.adaptive_outcome = ""
        self.attempt_reason = "initial"
        self.attempt_event = self.first_problem = self.retry_deadline = self.pending_retry = None
        self.closeup_requested = self.closeup_confirmed = False
        self.used_views = set()

        self.http = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rackonaut-mission-http")
        self.http_request = self.rearm_request = self.capture_after = None
        self.poll_at = 0.0
        self.recovery = self.flight_enable = None
        if settings["recovery_dir"]:
            if not (self.aerial and self.sensor_localization and self.energy_enabled and self.safety_interlock):
                raise ValueError("Recovery requires aerial sensor localization, Energy and Safety.")
            self.recovery = Recovery(self, settings["recovery_dir"])
            self.flight_enable = self.create_publisher(Bool, "/rackonaut/drone/flight_enabled", 5)
            self.create_subscription(String, "/rackonaut/recovery/operator", self.on_recovery_action, 5)
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
        if self.scanner and not self.sensor_localization:
            self.scanner.odometry(message)

    def on_localization(self, message):
        state = json.loads(message.data)
        if state.get("mode") == "sensor_based":
            self.localization, self.localization_at = state, monotonic()

    def localization_ready(self, now):
        return now - self.localization_at <= .40 and self.localization.get("state") == "TRACKING"

    def on_safety(self, message):
        state = json.loads(message.data)
        if state.get("inspection_id") == self.inspection_id:
            self.safety_at, self.safety_permit = monotonic(), state.get("permit") is True
            self.safety_phase = state.get("phase", "")
            self.safety_zones = set(state.get("required", ()))
            self.permit_departure = state.get("permit_departure")
            self.descents = state.get("aerial", {}).get("descents", {})
            self.safety_alarm, self.safety_recovery = state.get("alarm"), state.get("recovery") or {}

    def on_recovery_action(self, message):
        try:
            action = json.loads(message.data)
        except ValueError:
            return
        if isinstance(action, dict) and action.get("inspection_id") == self.inspection_id:
            self.recovery.action(action.get("action"), action.get("recovery_id"), action.get("proposal"), monotonic())

    def on_energy(self, message):
        self.battery, self.battery_at = json.loads(message.data), monotonic()
        if self.energy_model is None:
            self.energy_model = Model(**self.battery["model"])

    @staticmethod
    def coordinates(pose):
        return pose.x, pose.y, pose.z, pose.yaw

    def energy_fresh(self, now):
        return now - self.battery_at <= .80 and self.battery.get("fresh") is True

    def next_inspection_index(self):
        return next((index for index in range(self.stop_index, len(self.route.waypoints))
                     if self.route.waypoints[index].slot_id), None)

    def required_departure(self, index):
        if self.aerial:
            slot = self.route.waypoints[index]
            legs = [*self.outbound(slot), *self.dock_route(slot)]
            return estimate(self.energy_model, self.coordinates(self.route.pad),
                            [leg.pose for leg in legs], 4.)[0] + self.energy_model.reserve
        return first_requirement(
            self.energy_model, self.coordinates(self.route.pad), self.route.takeoff.z, self.route.crossing,
            self.coordinates(self.route.waypoints[index]), 4.,
        )

    def on_quality(self, message):
        evidence = json.loads(message.data)
        if evidence.get("inspection_id") == self.inspection_id:
            observation_id = evidence["observation_id"]
            if self.evidence.get(observation_id, {}).get("status") != "DAMAGED":
                self.evidence[observation_id] = evidence

    def readiness(self, now):
        if self.safety_interlock and (not self.safety_permit or now - self.safety_at > .45):
            return "Waiting for the safety interlock to confirm reserved, clear zones"
        if self.energy_enabled:
            if self.permit_departure != self.departures + 1 or not set(self.route.zones) <= self.safety_zones:
                return "Waiting for current departure clearance"
            if not self.energy_fresh(now) or not self.battery.get("contact"):
                return "Waiting for fresh battery and confirmed dock contact"
            if self.battery["percent"] < self.required_departure(self.next_inspection_index()):
                return "Insufficient energy to inspect the first remaining location and return"
            if self.departures and self.battery.get("dock") != "READY":
                return "Waiting for confirmed charge readiness"
        if self.pose is None or now - self.odom_at > .65:
            return f"Waiting for fresh odometry in {self.frame}"
        if self.sensor_localization and not self.localization_ready(now):
            return "Waiting for verified sensor localization"
        if self.scanner and self.scanner.current(now) is None:
            return "Waiting for synchronized onboard lidar"
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
        resuming = self.energy_enabled and self.stage == "READY_TO_RESUME"
        if self.stage != "WAITING" and not resuming:
            return f"Mission is {self.stage}. Start a new process with a new inspection ID."
        reason = self.readiness(now)
        if reason:
            return reason
        if self.flight_enable is not None:
            if not self.flight_enable.get_subscription_count():
                return "Waiting for the simulated flight-enable bridge"
            self.set_flight_enabled(True)
        self.command = self.create_publisher(Twist, self.command_topic, 10)
        if self.started is None:
            self.started = now
        if self.energy_enabled:
            self.departures += 1
            self.sorties.append({"departure": self.departures, "start_percent": self.battery["percent"],
                                 "start_sim_time": self.battery["sim_time"], "completed_before": list(self.completed)})
            self.landed = False
        target = replace(self.route.takeoff, phase="VERTICAL_TAKEOFF") if self.aerial else self.route.takeoff
        self.transition("RESUMING" if resuming else target.phase or "TAKEOFF", target, now,
                        "Resuming unfinished inspection" if resuming else "Climbing above the launch pad")
        return ""

    def on_start(self, _request, response):
        reason = self.start(monotonic())
        response.success = not reason
        response.message = reason or f"Started {self.inspection_id}"
        return response

    def on_abort(self, _request, response):
        if self.recovery and self.recovery.phase in RECOVERY_ACTIVE | {"RECOVERY_AUTHORIZED"}:
            self.recovery.finish(monotonic(), RECOVERY_FAILED, "Recovery stopped through the mission Abort service")
            response.success, response.message = True, self.recovery.record["detail"]
            return response
        response.success = self.stage not in TERMINAL
        if response.success:
            self.finish("ABORTED", "Stopped by the operator", monotonic())
        response.message = self.detail
        return response

    def transition(self, stage, target, now, detail):
        self.stage, self.target, self.stage_since, self.detail = stage, target, now, detail
        self.settled_since = None
        self.get_logger().info(f"{stage} {target.slot_id or 'PAD'} | {detail}")

    def send_velocity(self, target=None, scale=1.):
        command = Twist()
        if scale:
            x, y, z, yaw_rate = velocity(target or self.target, self.pose)
            command.linear.x, command.linear.y, command.linear.z = x * scale, y * scale, z * scale
            command.angular.z = yaw_rate
        self.command.publish(command)

    def avoidance_budget(self, position, legs, nominal, margin):
        try:
            back = self.aerial.home(legs[-1], self.route.zones)
        except ValueError:
            return None
        movement, seconds = estimate(self.energy_model, position, legs, 2.)
        movement += self.energy_model.hover * seconds * (1 / DETOUR_SCALE - 1)
        returning = estimate(self.energy_model, legs[-1], [leg.pose for leg in back])[0]
        reserve = self.energy_model.reserve + self.energy_model.hover * 2 + margin * .9
        if not self.energy_fresh(monotonic()) or self.battery["percent"] < movement + returning + reserve:
            return None
        direct = estimate(self.energy_model, position, [nominal])[0]
        alternate = estimate(self.energy_model, position, [*legs, nominal], 2.)[0]
        return round(max(0., alternate - direct), 2)

    def bypass_allowed(self, first, second):
        return any(interval(first, first, bounds) and interval(second, second, bounds)
                   for name, bounds in self.aerial.aisles.items() if name in self.safety_zones)

    def skip_blocked_stop(self, currently, now):
        if self.stage != "TRANSIT" or not self.target.slot_id or self.stop_index + 1 >= len(self.route.waypoints):
            return False
        following = self.route.waypoints[self.stop_index + 1]
        target = self.coordinates(following)
        if (not following.slot_id or not self.bypass_allowed(currently, target)
                or dist(currently[:3], target[:3]) > 3.
                or not self.navigation.confirmed(currently, target, self.bypass_allowed)
                or self.avoidance_budget(currently, [target], target, 0.) is None):
            return False
        self.missed.append(self.target.slot_id)
        self.manual_review[self.target.slot_id] = "The approach remained blocked by a measured obstacle"
        self.stop_index += 1
        self.navigation.set_state("ROUTE_BLOCKED", "Location deferred; next leg is observed and reserved")
        self.next_stop(now)
        return True

    def move_with_avoidance(self, now):
        p, target = self.coordinates(self.pose), self.coordinates(self.target)
        # Land at the intended contact plane; the controller targets slightly
        # lower to settle while the exposed volume above the pad stays checked.
        pad = (hypot(p[0]-self.route.pad.x, p[1]-self.route.pad.y) < .13
               and hypot(target[0]-self.route.pad.x, target[1]-self.route.pad.y) < .02)
        goal = (*target[:2], max(self.route.pad.z, target[2]), target[3]) if pad else target
        may_bypass = self.stage in {"TRANSIT", "AISLE_APPROACH", "RETURN_TO_DOCK"} and self.bypass_allowed(p, goal)
        decision = self.navigation.step(self.scanner.current(now), p, goal, self.stage, self.speed, now,
                                        may_bypass, self.bypass_allowed, self.avoidance_budget, pad)
        if decision.fault:
            self.send_velocity(scale=0.)
            if (self.navigation.cloud is None or
                    not (self.skip_blocked_stop(p, now) or self.try_verified_retreat(p, now))):
                self.finish("ABORTED", decision.fault, now)
            return
        if decision.advance:
            self.send_velocity(scale=decision.scale)
            self.advance(now)
        else:
            if self.stage in {"TRANSIT", "AISLE_APPROACH", "RETURN_TO_DOCK"}:
                # Avoidance has its own bounded wait and maneuver deadlines.
                self.stage_since = now
            self.settled_since = None
            if decision.target:
                self.send_velocity(Target(*decision.target), decision.scale)
            else:
                self.send_velocity(scale=0.)

    def try_verified_retreat(self, position, now):
        if self.obstacle_retreat or self.stage in {"RETURN_TO_DOCK", "DOCKING", "LAND"} or self.speed > .09:
            return False
        try:
            route = self.dock_route(self.pose)
        except ValueError:
            return False
        cloud = self.navigation.cloud
        points = [leg.pose for leg in route]
        if not points or any(dist(p[:3], cloud.origin) + .50 >= MAX_RANGE for p in points):
            return False
        for index, (first, second) in enumerate(zip((position, *points), points)):
            if not sweep(cloud, first, second, dist(first[:3], second[:3]), pad=index == len(points)-1).confirmed:
                return False
        if self.battery["percent"] < estimate(self.energy_model, position, points)[0] + self.energy_model.reserve:
            return False
        self.obstacle_retreat = True
        self.return_reason = "Route blocked; returning via a measured path for operator review"
        self.navigation.set_state("ROUTE_BLOCKED", self.return_reason)
        self.follow_return(now, route)
        return True

    def stable(self, now, duration=.45, touchdown=False):
        p, goal = self.pose, self.target
        horizontal = hypot(p.x - goal.x, p.y - goal.y)
        altitude = p.z <= self.route.pad.z + .018 if touchdown else abs(p.z - goal.z) <= .06
        if touchdown and self.sensor_localization:
            altitude = self.battery.get("contact") is True
        if horizontal <= .065 and altitude and abs(heading_error(goal.yaw, p.yaw)) <= .055 and self.speed <= .11:
            if self.settled_since is None:
                self.settled_since = now
            return now - self.settled_since >= duration
        self.settled_since = None
        return False

    def next_stop(self, now):
        if self.stop_index == len(self.route.waypoints):
            if self.aerial:
                self.transition("LAND", replace(self.route.pad, z=0.), now, "Descending vertically into the technical dock")
                return
            self.transition("RETURN", self.route.takeoff, now, "Returning along the clear aisle to the pad")
            return
        stop = self.route.waypoints[self.stop_index]
        if stop.slot_id:
            self.transition("TRANSIT", replace(stop, yaw=self.target.yaw), now, "Flying to the inspection viewpoint")
        elif stop.phase:
            self.follow_leg(stop, stop.phase, now)
        else:
            self.transition("CORRIDOR", stop, now, "Following the clear transfer corridor")

    def follow_leg(self, target, stage, now):
        if target.phase == "AISLE_DESCENT":
            self.pending_descent = target, stage
            self.transition("WAITING_FOR_AISLE_CLEARANCE", self.target, now,
                            f"Holding over descent {target.gate} for fresh Safety clearance")
        else:
            self.transition(stage, target, now, "Following the reserved aerial corridor")

    def begin_scan(self, now):
        slot = self.target.slot_id
        if slot not in self.visits:
            self.visits.append(slot)
        if self.adaptive:
            prior = [attempt for attempt in self.attempts if attempt["slot_id"] == slot] if self.energy_enabled else []
            self.retry_number = min(len(prior), MAX_RETRIES)
            self.first_problem = self.retry_deadline = self.pending_retry = None
            self.closeup_requested = self.closeup_confirmed = False
            self.used_views.clear()
            self.adaptive_outcome = ""
            self.begin_adaptive_scan(now, "initial")
            return
        self.transition("INSPECT", self.target, now, "Waiting for a fresh camera observation in the API")
        self.capture_after = datetime.now(timezone.utc)
        self.rearm_request = self.rearm_client.call_async(Trigger.Request())
        self.poll_at = now

    def capture(self, now):
        if self.rearm_request is None or (self.rearm_request.done() and self.rearm_request.result().success):
            if self.http_request is not None and self.http_request.done():
                events, problem = self.http_request.result()
                self.http_request = None
                if problem:
                    self.detail = problem
                elif not self.adaptive:
                    self.detail = "Waiting for a fresh camera observation in the API"
                seen = {event["observation_id"] for event in self.confirmed.values()}
                event = current_observation(events, self.inspection_id, self.target.slot_id, self.capture_after, seen)
                if event is not None:
                    self.confirmed[self.target.slot_id] = event
                    self.get_logger().info(f"CONFIRMED {self.target.slot_id} {event['occupancy']} "
                                           f"{event.get('pallet_id') or '-'} {event['observation_id']}")
                    return event
            if self.http_request is None and now >= self.poll_at:
                self.http_request = self.http.submit(fetch_observations, self.backend, self.inspection_id)
                self.poll_at = now + .45
        return None

    def scan(self, now):
        slot = self.target.slot_id
        if slot in self.confirmed or self.capture(now) is not None:
            if now - self.stage_since >= self.scan_hold:
                self.end_scan(now)
            return
        if now - self.stage_since >= self.inspection_timeout:
            self.missed.append(slot)
            self.get_logger().warning(f"MISSED {slot} | No fresh API confirmation within the hold")
            self.end_scan(now)

    def begin_adaptive_scan(self, now, reason):
        self.attempt_reason = reason
        self.attempt_event = None
        stage = {"initial": "INSPECT", "damage": "QUALITY_CLOSEUP"}.get(reason, "REINSPECT")
        detail = RETRY_TEXT.get(reason, "Inspecting from the reference viewpoint")
        self.capture_after = datetime.now(timezone.utc)
        self.poll_at = now
        self.transition(stage, self.target, now, detail)
        self.publish_state(now)

    def scan_adaptive(self, now):
        if self.attempt_event is None:
            self.attempt_event = self.capture(now)
        event = self.attempt_event
        photo = self.evidence.get(event["observation_id"]) if event else None
        elapsed = now - self.stage_since
        budget_low = self.retry_deadline is not None and now >= self.retry_deadline - RETURN_MARGIN
        if not budget_low:
            if event is None and elapsed < self.inspection_timeout:
                return
            if event and elapsed < self.scan_hold:
                return
            if (self.adaptive_quality and event and event["occupancy"] == "occupied"
                    and not photo and elapsed < QUALITY_SECONDS):
                return
        self.evaluate_attempt(now, event, photo)

    def evaluate_attempt(self, now, event, photo):
        slot = self.target.slot_id
        issue = next_issue(event, photo, self.closeup_requested)
        confirmed_closeup = self.attempt_reason == "damage" and photo and photo["status"] == "DAMAGED"
        self.closeup_confirmed = self.closeup_confirmed or bool(confirmed_closeup)
        if not self.retry_number:
            self.first_problem = reading_issue(event)
        self.adaptive_outcome = (RETRY_TEXT[issue] if issue else "Additional damage evidence saved"
                                 if confirmed_closeup else "Reading confirmed")
        if self.retry_number and self.first_problem and reading_issue(event) is None and slot not in self.resolved:
            self.resolved.append(slot)
            self.adaptive_outcome = ("Label recovered successfully" if event["label_status"] == "readable"
                                     else "Occupancy confirmed on reinspection")
        self.attempts.append({
            "slot_id": slot, "attempt": sum(row["slot_id"] == slot for row in self.attempts) + 1,
            "reason": self.attempt_reason,
            "issue": issue, "observation_id": event["observation_id"] if event else None,
            "quality_id": photo["quality_id"] if photo else None,
            "reading": [event["occupancy"], event["label_status"], event["pallet_id"]] if event else None,
            "outcome": self.adaptive_outcome,
        })
        envelope = self.route.retries[slot]
        retry = first_unused(envelope.views, issue, self.used_views)
        if issue and retry and self.retry_number < MAX_RETRIES and (
                self.retry_deadline is None or now + 10 < self.retry_deadline):
            self.pending_retry = issue, retry
            if self.retry_deadline is None:
                self.retry_deadline = now + RETRY_SECONDS
            if self.retry_number:
                self.move_adaptive("RECENTER", self.route.waypoints[self.stop_index], now, RETRY_TEXT[issue])
            else:
                self.start_retry(now)
            return
        if issue or (self.closeup_requested and not self.closeup_confirmed):
            self.manual_review[slot] = issue or "damage_closeup_unconfirmed"
            self.adaptive_outcome = f"Manual verification required for {slot}"
            self.attempts[-1]["outcome"] = self.adaptive_outcome
        if slot not in self.confirmed:
            self.missed.append(slot)
        if self.retry_number:
            self.move_adaptive("RECENTER", self.route.waypoints[self.stop_index], now, self.adaptive_outcome)
        else:
            self.end_scan(now)

    def start_retry(self, now):
        reason, pose = self.pending_retry
        self.pending_retry = None
        self.total_retries += 1
        self.retry_number += 1
        self.attempt_reason = reason
        self.closeup_requested |= reason == "damage"
        self.used_views.add(pose)
        self.move_adaptive("REPOSITION", pose, now, RETRY_TEXT[reason])

    def move_adaptive(self, stage, target, now, detail):
        zone = self.route.retries[target.slot_id].zone
        if self.safety_phase != "RESERVED" or zone not in self.safety_zones:
            self.finish("ABORTED", "Adaptive viewpoint lacks an active safety reservation", now)
            return
        self.moves.append({"slot_id": target.slot_id, "attempt": self.retry_number + 1,
                           "stage": stage, "from": [self.pose.x, self.pose.y, self.pose.z],
                           "target": [target.x, target.y, target.z], "actual": None})
        self.transition(stage, target, now, detail)
        self.publish_state(now)

    def end_scan(self, now):
        if self.rearm_request is not None and not self.rearm_request.done():
            self.rearm_client.remove_pending_request(self.rearm_request)
        self.rearm_request = None
        # A previous GET may still be running. Keep one worker/request, and
        # apply the next slot's own UTC cutoff before accepting any event.
        if self.energy_enabled:
            self.completed.append(self.target.slot_id)
        self.stop_index += 1
        if self.energy_enabled and self.energy_return_needed():
            self.begin_energy_return(now)
            return
        self.next_stop(now)

    def set_flight_enabled(self, enabled):
        if self.flight_enable is not None:
            self.flight_enable.publish(Bool(data=enabled))

    def stop_motion(self, competing=False):
        if self.command is not None:
            if not competing and self.count_publishers(self.command_topic) <= 1:
                self.command.publish(Twist())
                self.command.wait_for_all_acked(Duration(seconds=.18))
            self.destroy_publisher(self.command)
            self.command = None

    def dock_route(self, pose):
        if self.aerial:
            return self.aerial.home(self.coordinates(pose), self.route.zones)
        return [Leg(point, "") for point in dock_path(self.coordinates(pose), self.coordinates(self.route.pad),
                                                     self.route.takeoff.z, self.route.crossing)]

    def outbound(self, slot):
        if self.aerial:
            return self.aerial.sortie(self.coordinates(slot), slot.slot_id[0])
        return [Leg(point, "") for point in sortie_path(self.coordinates(self.route.pad), self.route.takeoff.z,
                                                       self.route.crossing, self.coordinates(slot))]

    def return_cost(self, pose):
        if dist(self.coordinates(pose)[:3], self.coordinates(self.route.pad)[:3]) < .08:
            return 0.
        try:
            return estimate(self.energy_model, self.coordinates(pose), [leg.pose for leg in self.dock_route(pose)])[0]
        except ValueError:
            return float("inf")

    def aerial_remaining_cost(self, remaining, return_percent):
        if self.stage in TERMINAL:
            return 0. if self.landed else None
        if self.stage == "LAND" or self.obstacle_retreat:
            return return_percent
        pad = self.coordinates(self.route.pad)
        origin = self.coordinates(self.pose)
        return_to_charge = 0.
        if self.stage in DOCK_WAIT | {"RETURN_TO_DOCK", "DOCKING"}:
            if return_percent is None:
                return None
            return_to_charge = return_percent
            slot = self.route.waypoints[self.resume_index]
            legs = [leg.pose for leg in self.outbound(slot)]
            waypoints = self.route.waypoints[self.resume_index + 1:]
            origin = pad
        else:
            waypoints = self.route.waypoints[self.stop_index:]
            resuming = self.stage == "RESUMING" or (
                self.pending_descent and self.pending_descent[1] == "RESUMING")
            legs = [self.coordinates(point) for point in (self.target, *self.resume_legs)] if resuming else []
            if self.stage in {"WAITING", "VERTICAL_TAKEOFF"}:
                legs.append(self.coordinates(self.route.takeoff))
            if resuming and self.pending_descent:
                legs.insert(1, self.coordinates(self.pending_descent[0]))
            if not waypoints and not legs:
                return return_percent
        return return_to_charge + estimate(self.energy_model, origin,
                                           [*legs, *(self.coordinates(p) for p in waypoints), pad],
                                           len(remaining) * 3.)[0]

    def energy_return_needed(self):
        index = self.next_inspection_index()
        if index is None or not self.energy_model:
            return False
        legs = self.route.waypoints[self.stop_index:index + 1]
        next_cost, _ = estimate(self.energy_model, self.coordinates(self.pose),
                                [self.coordinates(pose) for pose in legs], 4.)
        return self.battery["percent"] < next_cost + self.return_cost(legs[-1]) + self.energy_model.reserve

    def begin_energy_return(self, now):
        self.resume_index = self.next_inspection_index()
        if self.resume_index is None:
            return
        if self.departures > len(self.route.stops):
            self.finish("ABORTED", "Energy model cannot advance with a full charge", now)
            return
        if self.target.slot_id and self.target.slot_id not in self.completed:
            self.interruptions.append({"slot": self.target.slot_id, "stage": self.stage,
                                       "sim_time": self.battery["sim_time"]})
        self.return_reason = "Low battery — returning to charging station"
        try:
            route = self.dock_route(self.pose)
        except ValueError:
            self.finish("ABORTED", "No connected aerial return from current odometry", now)
            return
        self.follow_return(now, route)

    def follow_return(self, now, route):
        self.return_track = [list(self.coordinates(self.pose)[:3]), *(list(leg.pose[:3]) for leg in route)]
        self.return_legs = [Target(*leg.pose, phase=leg.phase, gate=leg.gate) for leg in route[:-1]]
        self.pending_descent = None
        if self.return_legs:
            self.transition("RETURN_TO_DOCK", self.return_legs.pop(0), now, self.return_reason)
        else:
            self.transition("DOCKING", replace(self.route.pad, z=0.), now, "Landing in the technical dock")

    def close_sortie(self, result):
        self.sorties[-1].update({"result": result, "end_percent": self.battery.get("percent"),
                                 "end_sim_time": self.battery.get("sim_time"),
                                 "completed_after": list(self.completed)})

    def advance_energy_motion(self, now):
        if self.stage == "RETURN_TO_DOCK":
            if self.return_legs:
                self.transition("RETURN_TO_DOCK", self.return_legs.pop(0), now, self.return_reason)
            else:
                touchdown = replace(self.route.pad, z=max(0., self.route.pad.z - .05))
                self.transition("DOCKING", touchdown, now, "Aligning and landing on the dock")
        elif self.stage == "DOCKING":
            if self.battery.get("contact"):
                if self.obstacle_retreat:
                    pending = [slot.slot_id for slot in self.route.stops if slot.slot_id not in self.completed]
                    self.missed = list(dict.fromkeys([*self.missed, *pending]))
                    self.manual_review.update({slot: "Flight path blocked by an obstacle" for slot in pending})
                    self.landed = True
                    self.finish("COMPLETE_WITH_MISSES", "Returned to dock; remaining locations need operator review", now)
                    return
                self.stop_motion()
                self.landed = True
                self.close_sortie("DOCKED_FOR_CHARGE")
                self.stop_index = self.resume_index
                self.last_charge_progress = now, self.battery["percent"]
                self.transition("CHARGING", self.route.pad, now, "Docking confirmed — charging")
        elif self.resume_legs:
            leg = self.resume_legs.pop(0)
            if self.aerial:
                self.follow_leg(leg, "RESUMING", now)
            else:
                self.transition("RESUMING", leg, now, "Resuming through the transfer corridor")
        else:
            self.next_stop(now)

    def dock_tick(self, now):
        if not self.battery.get("contact"):
            self.finish("ABORTED", "Charging contact was lost", now)
            return
        if self.stage == "CHARGING":
            needed = self.required_departure(self.resume_index)
            target = max(needed, self.energy_model.ready)
            if target > 100.:
                self.finish("ABORTED", "A full battery cannot cover the next stop and safe return", now)
                return
            if self.battery["percent"] >= target and self.battery.get("dock") == "READY":
                route = self.outbound(self.route.waypoints[self.resume_index])
                self.resume_legs = [Target(*leg.pose, phase=leg.phase, gate=leg.gate) for leg in route[1:-1]]
                self.sorties[-1]["charged_percent"] = self.battery["percent"]
                self.sorties[-1]["charge_end_sim_time"] = self.battery["sim_time"]
                self.transition("READY_TO_RESUME", self.route.pad, now, "Battery ready — requesting departure clearance")
                return
            last, level = self.last_charge_progress
            if self.battery["percent"] > level:
                self.last_charge_progress = now, self.battery["percent"]
            elif now - last > 12.:
                self.finish("ABORTED", "Dock reported no charging progress", now)
        elif now - self.stage_since > 16.:
            self.finish("ABORTED", "Fresh departure clearance was not granted", now)
        else:
            self.start(now)

    def energy_guard(self, now):
        if not self.energy_enabled or self.stage in TERMINAL | {"WAITING"}:
            return False
        if now - self.safety_at > .65 or self.safety_phase != "RESERVED" or not set(self.route.zones) <= self.safety_zones:
            self.finish("ABORTED", "Safety clearance lost; automatic restart disabled", now)
            return True
        if self.sensor_localization and not self.localization_ready(now):
            self.finish("ABORTED", "LOCALIZATION_LOST: Sensor position is no longer reliable", now)
            return True
        if not self.energy_fresh(now) or now - self.odom_at > .65:
            self.finish("ABORTED", "Energy or odometry telemetry stopped advancing", now)
            return True
        if self.stage in DOCK_WAIT:
            self.dock_tick(now)
            return True
        if self.battery["percent"] <= 0.5:
            self.finish("ABORTED", "Battery exhausted; operator recovery required", now)
            return True
        if (self.stage not in {"RETURN_TO_DOCK", "DOCKING", "RETURN", "LAND"}
                and self.next_inspection_index() is not None
                and self.battery["percent"] <= self.return_cost(self.pose) + self.energy_model.reserve):
            self.begin_energy_return(now)
            return True
        return False

    def finish(self, result, detail, now, competing=False):
        if self.navigation and result == "ABORTED" and self.navigation.mode not in {"FAULT", "RECOVERY_REQUIRED"}:
            self.navigation.set_state("ABORTED", detail)
        if result in {"COMPLETE", "COMPLETE_WITH_MISSES"} and self.landed and self.battery.get("contact") is True:
            self.set_flight_enabled(False)
        self.stop_motion(competing)
        if self.energy_enabled and self.sorties and "end_percent" not in self.sorties[-1]:
            self.close_sortie(result)
        if self.recovery and (result == "ABORTED" or not self.landed):
            self.recovery.stopped(now, detail, self.stage)
        self.ended = now
        self.transition(result, self.target, now, detail)
        self.publish_state(now)

    def advance(self, now):
        if self.stage == "WAITING_FOR_AISLE_CLEARANCE":
            target, stage = self.pending_descent
            if now - self.stage_since >= .40 and now - self.safety_at <= .45 and self.descents.get(target.gate, {}).get("cleared"):
                self.pending_descent = None
                self.transition(stage, target, now, f"Descending through reserved gate {target.gate}")
            elif now - self.stage_since > 8.:
                self.finish("ABORTED", f"Descent {target.gate} clearance timed out", now)
            return
        if self.adaptive and self.stage in {"REPOSITION", "RECENTER", "REINSPECT", "QUALITY_CLOSEUP"}:
            if self.stage in {"REINSPECT", "QUALITY_CLOSEUP"}:
                self.scan_adaptive(now)
            elif self.stable(now, duration=.35):
                self.moves[-1]["actual"] = [self.pose.x, self.pose.y, self.pose.z]
                if self.stage == "REPOSITION":
                    self.begin_adaptive_scan(now, self.attempt_reason)
                elif self.pending_retry:
                    self.start_retry(now)
                else:
                    self.end_scan(now)
            return
        if self.stage == "INSPECT":
            if self.adaptive:
                self.scan_adaptive(now)
            else:
                self.scan(now)
            return
        if now - self.stage_since >= self.travel_timeout:
            self.finish("ABORTED", f"Motion timed out at {self.stage}", now)
            return
        if not self.stable(now, duration=.65 if self.stage == "ALIGN" else .45,
                           touchdown=self.stage in {"LAND", "DOCKING"}):
            return
        if self.stage in {"TAKEOFF", "VERTICAL_TAKEOFF"}:
            self.next_stop(now)
        elif self.stage in {"RETURN_TO_DOCK", "DOCKING", "RESUMING"}:
            self.advance_energy_motion(now)
        elif self.stage in AERIAL_MOTION | {"CORRIDOR"}:
            self.stop_index += 1
            self.next_stop(now)
        elif self.stage == "TRANSIT":
            self.transition("ALIGN", self.route.waypoints[self.stop_index], now, "Turning toward the rack and settling")
        elif self.stage == "ALIGN":
            self.begin_scan(now)
        elif self.stage == "RETURN" and self.land:
            touchdown = replace(self.route.pad, z=max(0., self.route.pad.z - .05))
            self.transition("LAND", touchdown, now, "Descending onto the launch pad")
        elif self.energy_enabled and self.stage == "LAND" and not self.battery.get("contact"):
            return
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
        if self.recovery and self.stage in TERMINAL:
            self.recovery.tick(now)
            if now-self.status_at >= .20:
                self.publish_state(now)
            return
        held_for_energy = self.energy_guard(now)
        if self.command is not None and not held_for_energy:
            if self.count_publishers(self.command_topic) > 1:
                self.finish("ABORTED", "Another publisher claimed the command topic", now, competing=True)
            elif self.safety_interlock and now - self.safety_at > .65:
                self.get_logger().warning(
                    f"Safety state for {self.inspection_id} last received {now - self.safety_at:.3f}s ago "
                    f"during {self.stage}"
                )
                self.finish("ABORTED", "Safety Manager heartbeat stopped", now)
            elif now - self.odom_at > .65:
                self.finish("ABORTED", "Odometry stopped advancing", now)
            elif self.adaptive and self.safety_phase != "RESERVED":
                self.finish("ABORTED", "Safety Manager revoked the active reservation", now)
            elif self.aerial and not self.aerial.allows(self.coordinates(self.pose),
                                                       self.coordinates(self.target), self.route.zones):
                self.finish("ABORTED", "Odometry or the active segment left the reserved aerial envelope", now)
            elif self.adaptive and self.stage in {"REPOSITION", "RECENTER", "REINSPECT", "QUALITY_CLOSEUP"} and (
                    now >= self.retry_deadline or self.target.slot_id[0] not in self.safety_zones
                    or not self.pose.inside(self.route.retries[self.target.slot_id].bounds, margin=.10)):
                self.finish("ABORTED", "Adaptive motion exceeded its time or reserved envelope", now)
            else:
                if not self.track.poses or now - self.track_at >= .20:
                    self.track.poses.append(stamped_pose(self.pose, self.frame, self.odom_stamp))
                    self.track.header.stamp = self.odom_stamp
                    self.track_at = now
                if self.navigation:
                    self.move_with_avoidance(now)
                else:
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
        if self.aerial:
            phase, gate = self.stage, self.target.gate
            if self.stage == "WAITING_FOR_AISLE_CLEARANCE":
                gate = self.pending_descent[0].gate
            elif self.stage in {"RETURN_TO_DOCK", "RESUMING"}:
                phase = self.target.phase or self.stage
            elif self.stage in {"INSPECT", "REINSPECT", "QUALITY_CLOSEUP"}:
                phase = "INSPECTION"
            elif self.stage == "LAND":
                phase = "DOCKING"
            status.update(flight_phase=phase, descent_gate=gate)
        if self.navigation:
            status["avoidance"] = avoidance = self.navigation.snapshot(now)
            if avoidance["scan_age_ms"] is None and self.scanner.cloud:
                avoidance["scan_age_ms"] = round((now-self.scanner.cloud.received)*1000)
        if self.recovery and self.recovery.stop:
            status["recovery"] = self.recovery.snapshot()
        if self.sensor_localization:
            status["localization"] = self.localization.get("state", "DEGRADED")
        if self.adaptive:
            status["adaptive"] = {"attempt": self.retry_number + 1, "reason": self.attempt_reason,
                                  "attempts": self.attempts, "moves": self.moves, "retries": self.total_retries,
                                  "resolved": self.resolved, "manual_review": self.manual_review,
                                  "outcome": self.adaptive_outcome}
        if self.energy_enabled:
            remaining = [slot.slot_id for slot in self.route.stops if slot.slot_id not in self.completed]
            return_percent = required = None
            if self.pose and self.energy_model:
                predicted_return = self.return_cost(self.pose)
                return_percent = round(predicted_return, 2) if isfinite(predicted_return) else None
                if self.aerial:
                    cost = self.aerial_remaining_cost(remaining, predicted_return if isfinite(predicted_return) else None)
                else:
                    poses = [self.coordinates(point) for point in self.route.waypoints[self.stop_index:]]
                    dock = [self.coordinates(self.route.takeoff), self.coordinates(self.route.pad)]
                    if self.stage in DOCK_WAIT and self.resume_index is not None:
                        slot = self.route.waypoints[self.resume_index]
                        poses = [*(leg.pose for leg in self.outbound(slot)),
                                 *(self.coordinates(point) for point in self.route.waypoints[self.resume_index+1:])]
                    cost = estimate(self.energy_model, self.coordinates(self.pose), [*poses, *dock],
                                    len(remaining) * 3.)[0]
                required = round(cost, 2) if cost is not None else None
            status["energy"] = {
                "departures": self.departures, "sorties": self.sorties, "completed": self.completed,
                "remaining": remaining, "interrupted": self.interruptions,
                "return_reason": self.return_reason, "return_percent": return_percent,
                "required_percent": required, "reserve_percent": self.energy_model.reserve if self.energy_model else None,
                "return_path": self.return_track if self.stage in {"RETURN_TO_DOCK", "DOCKING"} else [],
            }
        self.status_pub.publish(String(data=json.dumps(status, separators=(",", ":"))))
        if self.track.poses:
            self.path_pub.publish(self.track)
        self.markers_pub.publish(make_markers(self.route, self.pose, self.frame, status))
        self.status_at = now

    def close(self):
        if self.recovery and self.recovery.phase in RECOVERY_ACTIVE | {"RECOVERY_AUTHORIZED"}:
            self.recovery.finish(monotonic(), RECOVERY_FAILED, "Mission controller stopped")
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
