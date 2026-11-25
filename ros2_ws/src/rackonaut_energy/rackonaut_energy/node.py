"""Publish one persistent simulated battery for the lifetime of the simulator."""

import json
from dataclasses import asdict
from math import atan2, hypot, isfinite, nan, radians
from pathlib import Path
from time import monotonic

import rclpy
from ament_index_python.packages import get_package_share_path
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from ros_gz_interfaces.msg import Contacts
from sensor_msgs.msg import BatteryState
from std_msgs.msg import String

from .model import Model, contact


STATE = "/rackonaut/energy/state"
BATTERY = "/rackonaut/drone/battery"
ODOM_TIMEOUT = .65
APPROACH = {"RETURN", "RETURN_TO_DOCK", "DOCKING", "LAND", "RETURN_TRANSIT"}
CHARGE_ALLOWED = {"DOCKING", "CHARGING", "READY_TO_RESUME", "COMPLETE", "COMPLETE_WITH_MISSES"}


class Energy(Node):
    def __init__(self):
        super().__init__("rackonaut_energy")
        model = {name: self.declare_parameter(name, value).value for name, value in asdict(Model()).items()}
        self.model = Model(**model)
        self.level = self.declare_parameter("initial_percent", 64.0).value
        if not 0 <= self.level <= 100:
            raise ValueError("initial_percent must be within 0–100.")
        self.events_file = self.declare_parameter("events_file", "").value
        self.aerial = self.declare_parameter("aerial", False).value
        self.sensor_localization = self.declare_parameter("sensor_localization", False).value
        layout_name = "aerial_layout.json" if self.aerial else "control_layout.json"
        layout = get_package_share_path("rackonaut_warehouse") / "config" / layout_name
        pad = json.loads(layout.read_text())["pad"]
        self.dock = pad["x"], pad["y"], pad["z"], radians(pad["yaw_deg"])
        self.mission = {}
        self.last_at = -1e6
        self.stamp = None
        self.stamp_msg = None
        self.contact_since = None
        self.cycles = 0
        self.cycle_started = False
        self.dock_state = "FAULT"
        self.contact_verified = False
        self.model_mode = "idle"
        self.pad_contact_at = -1e6
        self.pad_contact_stamp = -1.
        self.pad_touched = False
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.status_pub = self.create_publisher(String, STATE, latched)
        self.light_pub = self.create_publisher(String, "/rackonaut/energy/dock_light", 5)
        self.battery_pub = self.create_publisher(BatteryState, BATTERY, 5)
        self.create_subscription(Odometry, "/rackonaut/drone/odom", self.on_odometry, qos_profile_sensor_data)
        self.create_subscription(String, "/rackonaut/mission/status", self.on_mission, latched)
        if self.sensor_localization:
            self.create_subscription(Contacts, "/rackonaut/dock/contacts", self.on_pad_contact, qos_profile_sensor_data)
        self.create_timer(.20, self.publish_status)

    def on_mission(self, message):
        self.mission = json.loads(message.data)

    def on_pad_contact(self, message):
        stamp = message.header.stamp.sec + message.header.stamp.nanosec * 1.e-9
        if stamp <= self.pad_contact_stamp:
            return
        self.pad_contact_stamp, self.pad_contact_at = stamp, monotonic()
        pair = {"rackonaut_dock::body::dock_contact_surface_collision",
                "rackonaut_reference_drone::base_link::body_collision"}
        self.pad_touched = any({item.collision1.name, item.collision2.name} == pair for item in message.contacts)

    def physical_contact(self):
        return self.pad_touched and monotonic() - self.pad_contact_at <= .40

    def on_odometry(self, message):
        if (message.header.frame_id, message.child_frame_id) != ("rackonaut_odom", "rackonaut_base_link"):
            return
        p, q = message.pose.pose.position, message.pose.pose.orientation
        velocity, angular = message.twist.twist.linear, message.twist.twist.angular
        vx, vy, vz = velocity.x, velocity.y, velocity.z
        if not all(isfinite(v) for v in (p.x, p.y, p.z, q.x, q.y, q.z, q.w, vx, vy, vz,
                                        angular.x, angular.y, angular.z)):
            return
        msg_stamp = message.header.stamp
        stamp = msg_stamp.sec + 1e-9 * msg_stamp.nanosec
        dt = stamp - self.stamp if self.stamp is not None else 0.
        if dt < 0 or (dt == 0 and self.stamp is not None):
            return
        if dt > .30:
            self.contact_since = None
            dt = 0.
        self.stamp, self.stamp_msg, self.last_at = stamp, msg_stamp, monotonic()
        heading = atan2(2 * (q.w*q.z + q.x*q.y), 1 - 2 * (q.y*q.y + q.z*q.z))
        pose = p.x, p.y, p.z, heading
        speed, rotation = hypot(vx, vy, vz), hypot(angular.x, angular.y, angular.z)
        stage = self.mission.get("stage")
        if stage not in CHARGE_ALLOWED:
            self.cycle_started = False
        if self.sensor_localization:
            # The switch provides touchdown. Estimation supplies alignment and motion.
            touching = (self.physical_contact() and abs(p.z - self.dock[2]) <= .085
                        and contact((p.x, p.y, self.dock[2], heading), self.dock, speed, rotation))
        else:
            touching = contact(pose, self.dock, speed, rotation)
        if not touching:
            self.contact_since = None
            self.cycle_started = False
        elif self.contact_since is None:
            self.contact_since = stamp
        duration = stamp - self.contact_since if self.contact_since is not None else 0.
        self.contact_verified = touching and duration >= .65
        airborne = p.z > self.dock[2] + .06
        self.model_mode = "flight" if airborne else "idle"
        self.dock_state = "APPROACHING" if stage in APPROACH else "AVAILABLE"
        if self.contact_verified and stage in CHARGE_ALLOWED:
            self.dock_state = "DOCKED"
            if duration >= 1.45 and self.level < 100.:
                before = self.level
                self.level = min(100., self.level + self.model.charge * dt)
                self.model_mode = "charging"
                self.cycle_started |= self.level > before and before < self.model.ready
                if self.cycle_started and before < self.model.ready <= self.level:
                    self.cycles += 1
                    self.cycle_started = False
                    self.log_cycle()
                self.dock_state = "READY" if self.level >= self.model.ready else "CHARGING"
                return
            if self.level >= self.model.ready:
                self.dock_state = "READY"
                return
        self.level = max(0., self.level - self.model.draw(vx, vy, vz, airborne)*dt)

    def log_cycle(self):
        if self.events_file:
            path = Path(self.events_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"cycle": self.cycles, "sim_time": round(self.stamp, 3),
                                         "inspection_id": self.mission.get("inspection_id"),
                                         "reached_percent": round(self.level, 2)}) + "\n")

    def publish_status(self):
        fresh = monotonic() - self.last_at <= ODOM_TIMEOUT
        contact_live = not self.sensor_localization or self.physical_contact()
        dock = self.dock_state if fresh and (contact_live or not self.contact_verified) else "FAULT"
        charging = fresh and contact_live and self.model_mode == "charging"
        self.status_pub.publish(String(data=json.dumps({
            "simulated": True, "fresh": fresh, "percent": round(self.level, 3),
            "dock": dock, "contact": fresh and self.contact_verified and contact_live, "charging": charging,
            "cycles": self.cycles, "sim_time": self.stamp, "model": asdict(self.model),
            "profile": "protected_aerial_demo" if self.aerial else "reference_demo",
            **({"contact_source": "gazebo_dock_switch", "switch_engaged": contact_live}
               if self.sensor_localization else {}),
        }, separators=(",", ":"))))
        self.light_pub.publish(String(data=dock))
        if not fresh:
            return
        status = (BatteryState.POWER_SUPPLY_STATUS_CHARGING if charging else
                  BatteryState.POWER_SUPPLY_STATUS_FULL if self.level >= 100. else
                  BatteryState.POWER_SUPPLY_STATUS_DISCHARGING)
        battery = BatteryState(
            percentage=self.level / 100., power_supply_status=status, present=True,
            voltage=nan, temperature=nan, current=nan, charge=nan, capacity=nan, design_capacity=nan,
        )
        battery.header.stamp = self.stamp_msg
        battery.header.frame_id = "rackonaut_base_link"
        self.battery_pub.publish(battery)


def main():
    rclpy.init()
    node = Energy()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
