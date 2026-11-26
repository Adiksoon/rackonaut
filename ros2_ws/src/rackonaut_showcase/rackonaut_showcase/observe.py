"""Subscribe to mission telemetry and publish engineering displays only."""

from functools import partial
import json
from math import hypot, isfinite, nan
from pathlib import Path
from time import monotonic

from ament_index_python.packages import get_package_share_path
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from std_msgs.msg import Float64MultiArray, MultiArrayDimension, String
from visualization_msgs.msg import MarkerArray

from .markers import GOLD, CYAN, WHITE, aircraft, infrastructure, label, line, navigation, recovery, reset, safety

PREFIX = "/rackonaut/engineering/"
GROUPS = {
    "flight": ("x_m", "y_m", "z_m", "speed_mps", "angular_rps", "command_speed_mps", "command_angular_rps"),
    "localization": ("fit_rms_m", "sigma_max_m", "processing_ms", "scan_hz_wall", "scan_age_ms", "imu_age_ms",
                     "overlap", "map_cells"),
    "energy": ("battery_percent", "return_percent", "reserve_percent", "charging"),
    "avoidance": ("obstacle_m", "verified_m", "extra_path_m", "braking"),
    "validation": ("position_error_m", "rmse_m", "max_m", "orientation_rmse_deg"),
}


class Observe(Node):
    def __init__(self):
        super().__init__("rackonaut_engineering")
        trace = self.declare_parameter("trace_file", "").value
        self.trace = None
        if trace:
            path = Path(trace)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.trace = path.open("w", encoding="utf-8", buffering=1)
        self.started = monotonic()
        self.cache = {}
        config = get_package_share_path("rackonaut_warehouse") / "config"
        read = lambda name: json.loads((config / f"{name}.json").read_text())
        self.scanners = read("laser_fields")
        durable = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.markers = {ws: self.create_publisher(MarkerArray, PREFIX+ws, durable)
                        for ws in ("reference", "aircraft", "navigation", "safety", "recovery", "validation")}
        self.markers["reference"].publish(infrastructure(read("aerial_layout"), read("control_layout")))
        self.markers["aircraft"].publish(aircraft())
        self.telemetry = {group: self.create_publisher(Float64MultiArray, PREFIX+"telemetry/"+group, 5)
                          for group in GROUPS}
        subscriptions = {
            "mission": "/rackonaut/mission/status",
            "localization": "/rackonaut/localization/state",
            "energy": "/rackonaut/energy/state",
            "safety": "/rackonaut/safety/state",
            "validation": "/rackonaut/localization/validation",
        }
        for name, topic in subscriptions.items():
            self.create_subscription(String, topic, partial(self.remember_json, name), durable)
        self.create_subscription(Odometry, "/rackonaut/drone/odom", partial(self.remember, "odom"), qos_profile_sensor_data)
        self.create_subscription(Twist, "/rackonaut/drone/cmd_vel", partial(self.remember, "command"), qos_profile_sensor_data)
        self.create_timer(.30, self.update)

    def remember_json(self, name, message):
        self.remember(name, json.loads(message.data))

    def remember(self, name, value):
        self.cache[name] = monotonic(), value

    def received(self, name, now, limit=1.2, default=None):
        at, value = self.cache.get(name, (-1e6, default))
        return value if now-at < limit else default

    def update(self):
        now = monotonic()
        mission = self.received("mission", now, default={})
        local = self.received("localization", now, default={})
        power = self.received("energy", now, default={})
        safe = self.received("safety", now, default={})
        validation = self.received("validation", now, limit=2., default={})
        avoid = mission.get("avoidance") or {}
        return_state = mission.get("recovery") or {}
        odom = self.received("odom", now)
        cmd = self.received("command", now, .55)
        sim_time = None
        flight = [None]*7
        if odom:
            p, v = odom.pose.pose.position, odom.twist.twist
            flight[:5] = [p.x, p.y, p.z, hypot(v.linear.x, v.linear.y, v.linear.z),
                          hypot(v.angular.x, v.angular.y, v.angular.z)]
            stamp = odom.header.stamp
            sim_time = stamp.sec + stamp.nanosec * 1e-9
        if cmd:
            flight[5:] = [hypot(cmd.linear.x, cmd.linear.y, cmd.linear.z),
                          hypot(cmd.angular.x, cmd.angular.y, cmd.angular.z)]
        plan_energy = mission.get("energy") or {}
        forecast = return_state.get("return_cost")
        rows = {
            "flight": flight,
            "localization": [local.get("rms"), max(local.get("sigma") or [nan]), local.get("processing_ms"),
                             *(local.get(key) for key in ("update_hz", "scan_age_ms", "imu_age_ms", "overlap", "map_voxels"))],
            "energy": [power.get("percent"), forecast if forecast is not None else plan_energy.get("return_percent"),
                       (power.get("model") or {}).get("reserve"), power.get("charging")],
            "avoidance": [*(avoid.get(key) for key in ("obstacle_distance", "verified_distance", "extra_distance")),
                          avoid.get("state") == "BRAKING" if avoid else None],
            "validation": [validation.get(key) for key in ("position_error", "rmse", "max", "orientation_rms_deg")],
        }
        for group, values in rows.items():
            data = [float(v) if v is not None else nan for v in values]
            msg = Float64MultiArray(data=data)
            msg.layout.dim = [MultiArrayDimension(label=", ".join(GROUPS[group]), size=len(data), stride=len(data))]
            self.telemetry[group].publish(msg)
        self.markers["navigation"].publish(navigation(mission))
        self.markers["safety"].publish(safety(safe, self.scanners))
        self.markers["recovery"].publish(recovery(return_state))
        if validation and (reference := validation.get("trajectory")) and (estimate := local.get("trajectory")):
            items = [line("Sensor scan estimate", 0, estimate, .11, CYAN),
                     line("Gazebo reference · validation only", 0, reference, .065, GOLD),
                     label("Independent validation", 0, (9., 9., 7.8),
                           f"SENSOR ESTIMATE / GAZEBO VALIDATION ONLY\nRMSE {validation['rmse']*100:.2f} cm · "
                           f"MAX {validation['max']*100:.2f} cm · {validation['orientation_rms_deg']:.3f}° orientation RMS",
                           WHITE, .45)]
            self.markers["validation"].publish(reset(items))
        else:
            self.markers["validation"].publish(reset([]))
        if self.trace:
            self.trace.write(json.dumps({
                "wall": round(now-self.started, 4), "simulation_time": sim_time,
                "mission": mission.get("flight_phase", mission.get("stage")), "inspection_id": mission.get("inspection_id"),
                "avoidance_state": avoid.get("state"), "safety": safe.get("phase"),
                "recovery": return_state.get("phase"),
                **{key: {field: value if value is not None and isfinite(value) else None
                         for field, value in zip(GROUPS[key], row)} for key, row in rows.items()},
                "localization_state": local.get("state"),
                "sensor_mode": safe.get("sensor_mode"), "dock_contact": power.get("contact"),
                "safety_scan_age_ms": {name: scan.get("age_ms") for name, scan in safe.get("scans", {}).items()},
                "safety_zones": {key: {"state": value.get("state"), "sensor": value.get("sensor")}
                                 for key, value in safe.get("zones", {}).items()},
            }, separators=(",", ":")) + "\n")


def main():
    rclpy.init()
    node = Observe()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        if node.trace:
            node.trace.close()
        node.destroy_node()
        rclpy.try_shutdown()
