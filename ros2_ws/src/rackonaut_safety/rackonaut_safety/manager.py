"""Reserve monitored space and use the existing ROS abort service on intrusion."""

import json
import re
from collections import deque
from datetime import datetime, timezone
from functools import partial
from math import hypot, isfinite
from pathlib import Path
from time import monotonic, monotonic_ns

import rclpy
from ament_index_python.packages import get_package_share_path
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from std_srvs.srv import Trigger
from rackonaut_energy.aerial import Network
from tf2_msgs.msg import TFMessage

from .geometry import overlaps, route_zones
from .laser import LaserPresence

SAFETY = "/rackonaut/safety"
TERMINAL = {"COMPLETE", "COMPLETE_WITH_MISSES", "ABORTED"}
LABELS = {"A": "Aisle A", "B": "Aisle B", "T": "Transfer corridor & pad", "D": "Technical dock and shaft"}
PREPARE_SECONDS = 3.
CLEAR_SECONDS = .8
PRESENCE_TIMEOUT = .75
SIGNAL_TIMEOUT = 1.1
ODOM_TIMEOUT = .65


class Manager(Node):
    def __init__(self):
        super().__init__("rackonaut_safety")
        config = get_package_share_path("rackonaut_warehouse") / "config"
        self.fields = json.loads((config / "safety_fields.json").read_text())
        self.pad = json.loads((config / "control_layout.json").read_text())["pad"]
        self.aerial = None
        if self.declare_parameter("aerial", False).value:
            profile = json.loads((config / "aerial_layout.json").read_text())
            self.aerial = Network(profile)
            self.pad = profile["pad"]
        self.recovery_enabled = self.declare_parameter("autonomous_recovery", False).value
        self.recovery_id, self.recovery_revocation = None, None
        self.energy, self.energy_at = {}, -1e6
        self.sensor_mode = self.declare_parameter("sensor_mode", "virtual").value
        if self.sensor_mode not in {"virtual", "laser"}:
            raise ValueError("Safety sensor mode must be virtual or laser.")
        self.laser = None
        if self.sensor_mode == "laser":
            scanner_config = json.loads((config / "laser_fields.json").read_text())
            if scanner_config.keys() != self.fields.keys():
                raise ValueError("Laser calibration must include each reserved zone.")
            self.laser = LaserPresence(scanner_config, PRESENCE_TIMEOUT)
        if self.aerial:
            self.fields["D"] = profile["technical"]
        log = self.declare_parameter("events_file", "safety-events.jsonl").value
        self.log = Path(log)
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.events = deque(maxlen=30)
        if self.log.is_file():
            self.events.extendleft(json.loads(line) for line in self.log.read_text().splitlines()[-30:])
        self.worker = self.worker_stamp = self.odom = self.odom_stamp = None
        self.worker_at = self.odom_at = self.light_at = self.mission_at = -1e6
        self.light_state = {}
        self.clear_since = {}
        self.mission = {}
        self.run = None
        self.required = []
        self.phase = "AVAILABLE"
        self.message = "Waiting for presence, odometry and signals."
        self.alarm = None
        self.reserved_at = self.prepared_at = self.next_abort = 0.
        self.permit_issued = self.airborne = self.abort_logged = False
        self.energy_permits = set()
        self.abort_future = None
        self.occupied_since = {}
        self.recent_requests = deque(maxlen=20)
        reliable = QoSProfile(depth=5)
        latest = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(String, SAFETY + "/request", self.request, reliable)
        self.create_subscription(String, SAFETY + "/signals_applied", self.on_lights, reliable)
        self.create_subscription(String, "/rackonaut/mission/status", self.on_mission, latest)
        if self.recovery_enabled:
            self.create_subscription(String, "/rackonaut/energy/state", self.on_energy, latest)
        if self.laser:
            for zone, scanner in self.laser.configs.items():
                self.create_subscription(LaserScan, scanner["topic"], partial(self.on_laser, zone), qos_profile_sensor_data)
        if not self.laser or self.aerial:
            self.create_subscription(TFMessage, SAFETY + "/worker_pose", self.on_presence, qos_profile_sensor_data)
        self.create_subscription(Odometry, "/rackonaut/drone/odom", self.on_odometry, qos_profile_sensor_data)
        self.state = self.create_publisher(String, SAFETY + "/state", latest)
        self.signals = self.create_publisher(String, SAFETY + "/signals", reliable)
        self.abort = self.create_client(Trigger, "/rackonaut/mission/abort")
        self.create_timer(.05, self.tick)

    def event(self, kind, description, zones=(), **details):
        entry = {"time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                 "monotonic_ns": monotonic_ns(), "inspection_id": self.run, "event": kind,
                 "zones": list(zones), "message": description, **details}
        self.events.appendleft(entry)
        with self.log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, separators=(",", ":")) + "\n")
        self.get_logger().info(f"{kind} {self.run or '-'} {','.join(zones)} | {description}")
        return entry

    def on_presence(self, message):
        if len(message.transforms) != 1:
            return
        transform = message.transforms[0]
        if transform.child_frame_id != "safety_worker":
            return
        stamp = (transform.header.stamp.sec, transform.header.stamp.nanosec)
        xyz = transform.transform.translation
        if (self.worker_stamp is not None and stamp <= self.worker_stamp
                or not all(isfinite(value) for value in (xyz.x, xyz.y, xyz.z))):
            return
        self.worker_stamp, self.worker_at = stamp, monotonic()
        self.worker = (xyz.x, xyz.y, xyz.z)
        occupied = self.occupied(self.worker_at)
        now_ns = monotonic_ns()
        self.occupied_since = {zone: self.occupied_since.get(zone, now_ns) for zone in occupied
                               if not self.laser or zone == "D"}

    def on_odometry(self, message):
        stamp = message.header.stamp
        stamp = (stamp.sec, stamp.nanosec)
        p, v = message.pose.pose.position, message.twist.twist.linear
        if (message.header.frame_id != "rackonaut_odom"
                or self.odom_stamp is not None and stamp <= self.odom_stamp
                or not all(isfinite(value) for value in (p.x, p.y, p.z, v.x, v.y, v.z))):
            return
        self.odom, self.odom_at, self.odom_stamp = (p.x, p.y, p.z, hypot(v.x, v.y, v.z)), monotonic(), stamp

    def on_laser(self, zone, message):
        self.laser.accept(zone, message, monotonic(), monotonic_ns)

    def on_lights(self, message):
        pairs = [item.split("=") for item in message.data.split()]
        if len(pairs) == len(self.fields) and all(len(pair) == 2 for pair in pairs):
            applied = dict(pairs)
            if applied.keys() == self.fields.keys():
                self.light_state, self.light_at = applied, monotonic()

    def on_energy(self, message):
        self.energy, self.energy_at = json.loads(message.data), monotonic()

    def on_mission(self, message):
        status = json.loads(message.data)
        if self.run and status.get("inspection_id") == self.run:
            self.mission, self.mission_at = status, monotonic()

    def occupied(self, now):
        detected = self.laser.occupied(now) if self.laser else []
        if now - self.worker_at > PRESENCE_TIMEOUT:
            return detected
        return [*detected, *(zone for zone, bounds in self.fields.items()
                            if (not self.laser or zone == "D") and overlaps(self.worker, bounds, margin=.28))]

    def sensor_health(self, zone, now):
        if self.laser and zone != "D":
            return self.laser.health(zone, now)
        if self.worker is None:
            return "UNKNOWN"
        return "FRESH" if now - self.worker_at <= PRESENCE_TIMEOUT else "STALE"

    def at_pad(self, now):
        if now - self.odom_at > ODOM_TIMEOUT:
            return False
        x, y, z, speed = self.odom
        return hypot(x - self.pad["x"], y - self.pad["y"]) <= .28 and abs(z - self.pad["z"]) <= .12 and speed <= .12

    def blockers(self, now):
        failed = [zone for zone in self.required if self.sensor_health(zone, now) != "FRESH"]
        if failed:
            reason = ("Safety data is stale or unknown: " + ", ".join(LABELS[key] for key in failed) + "."
                      if self.aerial else "Laser scan is stale or unknown: " + ", ".join(LABELS[key] for key in failed) + "."
                      if self.laser else "Presence sensor is stale or unknown.")
            return reason, failed, "sensor_fault"
        occupied = [zone for zone in self.required if zone in self.occupied(now)]
        if occupied:
            return "Zone occupied: " + ", ".join(LABELS[key] for key in occupied) + ".", occupied, "intrusion"
        if now - self.odom_at > ODOM_TIMEOUT:
            return "Drone odometry is stale or unknown.", self.required, "odometry_fault"
        if now - self.light_at > SIGNAL_TIMEOUT:
            return "Signal controller is unavailable.", self.required, "signal_fault"
        return "", [], ""

    def request(self, message):
        try:
            payload = json.loads(message.data)
            run = payload["inspection_id"]
            if not re.fullmatch(r"INS-CONTROL-[A-Z0-9-]{1,45}", run):
                return
            required = self.aerial.required(payload["points"]) if self.aerial else route_zones(payload["points"], self.fields)
        except (KeyError, TypeError, ValueError):
            return
        if run in self.recent_requests or self.phase in {"PREPARING", "RESERVED", "RECOVERY"}:
            return
        self.recovery_id, self.recovery_revocation = None, None
        self.recent_requests.append(run)
        self.run, self.required = run, required
        self.mission, self.mission_at = {}, -1e6
        self.alarm, self.abort_future = None, None
        self.permit_issued = self.airborne = self.abort_logged = False
        self.energy_permits.clear()
        now = monotonic()
        reason, zones, _ = self.blockers(now)
        if reason or not self.at_pad(now):
            self.reject(reason or "Drone must be stopped on the launch pad.", zones or required)
        else:
            self.phase, self.prepared_at = "PREPARING", now
            self.message = "Warning active. Verifying clear zones."
            self.event("preparing", self.message, required)

    def reject(self, reason, zones):
        self.phase, self.message = "REJECTED", reason
        self.event("start_blocked", reason, zones)

    def recover(self, reason, zones, kind):
        self.phase = "RECOVERY"
        self.message = "Operator recovery required. Access remains restricted."
        details = {}
        if kind == "intrusion":
            presence = [self.occupied_since[key] for key in zones if key in self.occupied_since]
            if presence:
                details["presence_sample_ns"] = min(presence)
            if self.laser:
                hits = [reading.occupied_since_ns for key, reading in self.laser.readings.items()
                        if key in zones and reading.occupied_since_ns is not None]
                if hits:
                    details["laser_detection_ns"] = min(hits)
        self.alarm = self.event(kind, reason, zones, **details)
        self.next_abort = 0.

    def release(self, message):
        self.phase, self.message = "RELEASED", message
        self.event("released", message, self.required)

    def supervise(self, now):
        if self.phase not in {"PREPARING", "RESERVED", "RECOVERY"}:
            return
        stage = self.mission.get("stage")
        if self.phase != "RECOVERY":
            if stage and stage not in TERMINAL | {"WAITING"}:
                if not self.airborne:
                    self.event("flight_started", "Mission Manager started the flight.", self.required)
                self.airborne = True
            if stage == "ABORTED":
                if not self.airborne and self.at_pad(now) and not self.permit_issued:
                    self.release("Preparation cancelled on the launch pad.")
                else:
                    self.recover("Mission aborted. Verify and recover the drone.", self.required, "mission_aborted")
                return
            if stage in {"COMPLETE", "COMPLETE_WITH_MISSES"}:
                if self.mission.get("landed") and self.at_pad(now):
                    self.release("Inspection completed and touchdown confirmed.")
                elif not self.mission.get("landed") or now - self.odom_at > ODOM_TIMEOUT:
                    self.recover("Mission ended without verified touchdown.", self.required, "touchdown_unknown")
                return
            problem, zones, kind = self.blockers(now)
            if not problem and self.airborne and now - self.mission_at > 1.1:
                problem, zones, kind = "Mission status stopped arriving.", self.required, "mission_fault"
            if problem:
                if self.airborne or self.permit_issued or not self.at_pad(now):
                    self.recover(problem, zones, kind)
                else:
                    self.reject(problem, zones)
                return
            if self.phase == "PREPARING" and now - self.prepared_at >= PREPARE_SECONDS:
                if all(now - self.clear_since[key] >= CLEAR_SECONDS for key in self.required):
                    self.phase, self.reserved_at = "RESERVED", now
                    self.message = "Reserved for drone inspection."
                    self.event("reserved", self.message, self.required)
            if self.phase == "RESERVED" and not self.permit_issued and now - self.reserved_at > 4.:
                self.reject("Red signals or the mission worker could not be verified.", self.required)
            if self.phase in {"PREPARING", "RESERVED"} and not self.airborne and now - self.prepared_at > 16.:
                if self.permit_issued:
                    self.recover("Reserved flight did not start as expected.", self.required, "mission_fault")
                else:
                    self.reject("The mission worker did not become ready.", self.required)
            return

        if stage == "ABORTED":
            if not self.abort_logged:
                self.abort_logged = True
                self.event("abort_confirmed", "Mission Manager confirmed Abort.", self.alarm["zones"],
                           triggering_event_ns=self.alarm["monotonic_ns"])
            return
        if stage in TERMINAL or now < self.next_abort:
            return
        if self.abort_future and not self.abort_future.done():
            return
        if self.abort.service_is_ready():
            self.abort_future = self.abort.call_async(Trigger.Request())
            if not self.next_abort:
                self.event("abort_dispatched", "Called the existing mission Abort service.", self.alarm["zones"],
                           triggering_event_ns=self.alarm["monotonic_ns"])
        self.next_abort = now + .3

    def recovery_permit(self, now, health, present, lights):
        proposal = self.mission.get("recovery") or {}
        fresh = self.phase == "RECOVERY" and now-self.mission_at < .65
        sensors = fresh and all(health[key] == "FRESH" for key in self.required)
        clear = sensors and all(key not in present and now-self.clear_since[key] >= CLEAR_SECONDS
                                for key in self.required)
        red = fresh and lights and all(self.light_state.get(key) == "RESERVED" for key in self.required)
        state = {"permit": None, "sensors_fresh": sensors, "fields_clear": clear, "signals_confirmed": red,
                 "revoked": self.recovery_revocation}
        if self.phase != "RECOVERY":
            return state
        requested = proposal.get("recovery_id")
        valid_id = isinstance(requested, str) and re.fullmatch(r"REC-[A-F0-9]{12}", requested)
        match = (valid_id and proposal.get("inspection_id") == self.run
                 and proposal.get("required_zones") == sorted(self.required))
        phase = proposal.get("phase")
        if (match and phase == "RECOVERY_COMPLETE" and requested == self.recovery_id
                and not self.recovery_revocation and fresh and self.at_pad(now)
                and now-self.energy_at <= .65 and self.energy.get("fresh") is True
                and self.energy.get("contact_source") == "gazebo_dock_switch"
                and self.energy.get("switch_engaged") is True and self.energy.get("contact") is True):
            self.release("Recovery completed and physical dock contact confirmed.")
            return state
        problem, _, _ = self.blockers(now)
        authorized = (match and proposal.get("permit_request") is True and bool(proposal.get("authorized_at"))
                      and phase in {"RECOVERY_AUTHORIZED", "RETURNING_TO_DOCK", "EMERGENCY_DOCKING"})
        eligible = fresh and clear and red and not problem and self.mission.get("stage") in TERMINAL
        if self.recovery_id is not None and not self.recovery_revocation and phase != "RECOVERY_COMPLETE" and (
                not eligible or not authorized or requested != self.recovery_id):
            self.recovery_revocation = problem or "Recovery conditions or controller heartbeat changed."
            self.event("recovery_revoked", self.recovery_revocation, self.required, recovery_id=self.recovery_id)
        if authorized and eligible and self.recovery_id != requested and phase == "RECOVERY_AUTHORIZED":
            self.recovery_id, self.recovery_revocation = requested, None
            self.event("recovery_permitted", "Approved recovery verified against reserved zones and red signals.",
                       self.required, recovery_id=requested)
        if authorized and eligible and requested == self.recovery_id and not self.recovery_revocation:
            state["permit"] = requested
        state["revoked"] = self.recovery_revocation if requested == self.recovery_id else None
        return state

    def visual_state(self, key, verified, recovery_clear=False):
        if key not in self.required or self.phase not in {"PREPARING", "RESERVED", "RECOVERY"}:
            return "OPEN" if verified else "FAULT"
        if self.phase == "PREPARING":
            return "PREPARING"
        if self.phase == "RECOVERY" and key in self.alarm["zones"] and not recovery_clear:
            return "INTRUSION" if self.alarm["event"] == "intrusion" else "FAULT"
        return "RESERVED"

    def tick(self):
        now = monotonic()
        present = self.occupied(now)
        health = {key: self.sensor_health(key, now) for key in self.fields}
        for key in self.fields:
            self.clear_since.setdefault(key, now)
            if health[key] != "FRESH" or key in present:
                self.clear_since[key] = now
        self.supervise(now)
        lights = now - self.light_at <= SIGNAL_TIMEOUT
        verified = lights and now - self.odom_at <= ODOM_TIMEOUT
        preventing = set(present) | {key for key in health if health[key] != "FRESH"}
        proposal = self.mission.get("recovery") or {}
        recovered_signal = (self.recovery_enabled and proposal.get("recovery_id") and verified
                            and now-self.mission_at < .65 and proposal.get("phase") != "RECOVERY_FAILED")
        recovery_state = self.recovery_permit(now, health, present, lights) if self.recovery_enabled else None
        phases = {key: self.visual_state(key, verified and health[key] == "FRESH",
                                        recovered_signal and key not in preventing) for key in self.fields}
        if self.recovery_enabled and self.phase == "RECOVERY" and proposal.get("recovery_id"):
            for key in self.required:
                if key in preventing:
                    phases[key] = "INTRUSION" if key in present else "FAULT"
        self.signals.publish(String(data=" ".join(f"{key}={value}" for key, value in phases.items())))
        stage = self.mission.get("stage")
        energy = self.mission.get("energy")
        departure = energy["departures"] + 1 if energy else None
        awaiting_departure = stage == "WAITING" or (energy is not None and stage == "READY_TO_RESUME"
                                                     and self.mission.get("landed") is True)
        clear_now = all(health[key] == "FRESH" and key not in present for key in self.required)
        permit = (self.phase == "RESERVED" and awaiting_departure
                  and now - self.mission_at < .7 and self.at_pad(now) and lights
                  and now - self.reserved_at >= .18
                  and clear_now
                  and all(self.light_state.get(key) == "RESERVED" for key in self.required))
        if permit and (not self.permit_issued or (energy and departure not in self.energy_permits)):
            self.permit_issued = True
            if energy:
                self.energy_permits.add(departure)
            details = {"departure": departure} if energy else {}
            self.event("start_permitted", "Reserved red signals accepted by Gazebo. Start permitted.", self.required, **details)
        busy = self.phase in {"PREPARING", "RESERVED", "RECOVERY"}
        sensor = next((problem for problem in ("UNKNOWN", "STALE") if problem in health.values()), "FRESH")
        snapshot = {
            "inspection_id": self.run, "phase": self.phase, "permit": permit,
            "permit_departure": departure if permit else None,
            "sensor": sensor, "sensor_mode": self.sensor_mode,
            "signals_online": lights, "at_pad": self.at_pad(now),
            "required": self.required if busy else [], "message": self.message, "alarm": self.alarm,
            "countdown": round(max(0., PREPARE_SECONDS - (now - self.prepared_at)), 1) if self.phase == "PREPARING" else 0,
            "zones": {key: {"label": LABELS[key], "state": value, "bounds": self.fields[key],
                            "sensor": health[key], "occupied": key in present if health[key] == "FRESH" else None,
                            "signals_acknowledged": lights and self.light_state.get(key) == value}
                      for key, value in phases.items()},
            "events": list(self.events),
        }
        if self.recovery_enabled:
            snapshot["recovery"] = recovery_state
        if self.laser:
            snapshot["scans"] = dict(self.laser.map_data(now))
        if self.aerial:
            snapshot["aerial"] = {
                "technical_sensor": "virtual_worker_pose",
                "worker": self.worker if now - self.worker_at <= PRESENCE_TIMEOUT else None,
                "descents": {
                    zone: {"bounds": bounds, "source": "aisle_lidar" if self.laser else "virtual_worker_pose",
                           "cleared": self.phase == "RESERVED" and zone in self.required and health[zone] == "FRESH"
                           and zone not in present and now - self.clear_since[zone] >= CLEAR_SECONDS
                           and lights and self.light_state.get(zone) == "RESERVED"}
                    for zone, bounds in self.aerial.gates.items()
                },
            }
        self.state.publish(String(data=json.dumps(snapshot, separators=(",", ":"))))


def main():
    rclpy.init()
    try:
        rclpy.spin(Manager())
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
