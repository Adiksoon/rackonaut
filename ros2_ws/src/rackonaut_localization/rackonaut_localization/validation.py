"""Read both poses for time-aligned diagnostics. No output feeds the estimator."""

import json
from collections import deque
from pathlib import Path

import numpy as np
import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from scipy.spatial.transform import Rotation
from std_msgs.msg import String

from rackonaut_avoidance.sensor import stamp
from .node import ESTIMATE, rounded

REFERENCE = "/rackonaut/validation/ground_truth"
VALIDATION = "/rackonaut/localization/validation"


def pose(message):
    p, q = message.pose.pose.position, message.pose.pose.orientation
    return stamp(message), np.array([p.x, p.y, p.z]), Rotation.from_quat([q.x, q.y, q.z, q.w])


class Validation(Node):
    def __init__(self):
        super().__init__("rackonaut_localization_validation")
        self.directory = Path(self.declare_parameter("data_dir", "control").value)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.records = (self.directory / "localization-validation.jsonl").open("a", buffering=1)
        self.truth = deque(maxlen=100)
        self.pending = deque(maxlen=16)
        self.rows = deque(maxlen=10000)
        self.trajectory = deque(maxlen=1800)
        self.create_subscription(Odometry, REFERENCE, self.on_truth, qos_profile_sensor_data)
        self.create_subscription(Odometry, ESTIMATE, self.on_estimate, qos_profile_sensor_data)
        self.pub = self.create_publisher(String, VALIDATION, QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.create_timer(.10, self.align)
        self.create_timer(.65, self.publish)

    def on_truth(self, message):
        item = pose(message)
        if not self.truth or item[0] > self.truth[-1][0]:
            self.truth.append(item)
            if not self.trajectory or np.linalg.norm(item[1] - self.trajectory[-1]) > .13:
                self.trajectory.append(item[1])

    def on_estimate(self, message):
        self.pending.append(pose(message))

    def align(self):
        if len(self.truth) < 2:
            return
        truth = list(self.truth)
        while self.pending and self.pending[0][0] <= truth[-1][0]:
            time, xyz, attitude = self.pending.popleft()
            interval = next(((a, b) for a, b in zip(truth, truth[1:]) if a[0] <= time <= b[0]), None)
            if interval is None:
                continue
            (t0, p0, q0), (t1, p1, q1) = interval
            if t1-t0 > .12:
                continue
            alpha = (time-t0)/(t1-t0)
            actual = p0 + alpha*(p1-p0)
            reference_attitude = q0 * Rotation.from_rotvec((q0.inv()*q1).as_rotvec()*alpha)
            error = xyz - actual
            angle = float(np.degrees((reference_attitude.inv()*attitude).magnitude()))
            row = {"sim_time": round(time, 4), "estimate": rounded(xyz, 5), "reference": rounded(actual, 5),
                   "error_xyz": rounded(error, 5), "angle_deg": round(angle, 4)}
            self.rows.append(row)
            self.records.write(json.dumps(row, separators=(",", ":"))+"\n")

    def publish(self):
        if not self.rows:
            return
        errors = np.asarray([row["error_xyz"] for row in self.rows])
        distances = np.linalg.norm(errors, axis=1)
        values = {"samples": len(errors), "rmse_xyz": rounded(np.sqrt(np.mean(errors**2, axis=0)), 4),
                  "rmse": round(float(np.sqrt(np.mean(distances**2))), 4),
                  "max": round(float(distances.max()), 4), "p95": round(float(np.percentile(distances, 95)), 4),
                  "orientation_rms_deg": round(float(np.sqrt(np.mean([row["angle_deg"]**2 for row in self.rows]))), 3),
                  "position_error": round(float(distances[-1]), 4),
                  "trajectory": [rounded(p) for p in self.trajectory]}
        self.pub.publish(String(data=json.dumps(values, separators=(",", ":"))))


def main():
    rclpy.init()
    node = Validation()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.records.close()
        node.destroy_node()
        rclpy.try_shutdown()
