#!/usr/bin/python3
"""Collect evidence from an isolated X3 simulator; do not run another Twist publisher."""
import argparse
from collections import deque
import json
from math import atan2, cos, hypot, sin
from pathlib import Path
from time import monotonic, sleep

import cv2
from cv_bridge import CvBridge
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import CameraInfo, Image
from tf2_msgs.msg import TFMessage

BASE = "rackonaut_base_link"
ODOM_FRAME = "rackonaut_odom"
OPTICAL = "rackonaut_camera_optical_frame"
CMD = "/rackonaut/drone/cmd_vel"


def seconds(stamp):
    return stamp.sec + stamp.nanosec / 1e9


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


class Probe(Node):
    def __init__(self):
        super().__init__("rackonaut_x3_probe")
        self.images, self.infos = deque(maxlen=40), deque(maxlen=40)
        self.odometry, self.dynamic_tf = deque(maxlen=100), deque(maxlen=100)
        self.static_tf = []
        self.guarded_command = None
        self.clock = 0.0
        self.bridge = CvBridge()
        self.command = self.create_publisher(Twist, CMD, 10)
        self.create_subscription(Image, "/rackonaut/camera/image_raw", self.images.append, qos_profile_sensor_data)
        self.create_subscription(CameraInfo, "/rackonaut/camera/camera_info", self.infos.append, qos_profile_sensor_data)
        self.create_subscription(Odometry, "/rackonaut/drone/odom", self.odometry.append, qos_profile_sensor_data)
        self.create_subscription(Clock, "/clock", self.on_clock, qos_profile_sensor_data)
        self.create_subscription(TFMessage, "/tf", self.on_dynamic_tf, 10)
        self.create_subscription(TFMessage, "/tf_static", self.on_static_tf,
                                 QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.create_subscription(Twist, "/rackonaut_drone/controller/cmd_vel", self.on_guarded_command, 10)

    def on_clock(self, message):
        self.clock = seconds(message.clock)

    def on_dynamic_tf(self, message):
        self.dynamic_tf.extend(message.transforms)

    def on_static_tf(self, message):
        self.static_tf.extend(message.transforms)

    def on_guarded_command(self, message):
        self.guarded_command = message

    def wait(self, predicate, description, timeout=20, command=None):
        end = monotonic() + timeout
        next_command = 0.0
        while monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.015)
            now = monotonic()
            if command and now >= next_command:
                self.command.publish(command())
                next_command = now + 0.10
            if predicate():
                return
        raise RuntimeError(f"Timed out waiting for {description}")

    @property
    def pose(self):
        return self.odometry[-1].pose.pose

    @property
    def speed(self):
        v = self.odometry[-1].twist.twist.linear
        return hypot(v.x, v.y, v.z)

    def pair(self, after=0):
        infos = {(item.header.stamp.sec, item.header.stamp.nanosec): item for item in self.infos}
        for image in reversed(self.images):
            stamp = image.header.stamp
            info = infos.get((stamp.sec, stamp.nanosec))
            if (seconds(stamp) > after and info and info.header == image.header
                    and image.header.frame_id == OPTICAL and image.encoding in ("rgb8", "bgr8")
                    and (info.width, info.height) == (image.width, image.height) and info.k[0] > 0 and info.k[4] > 0):
                return image, info
        return None

    def dynamic_pair(self):
        odom_by_stamp = {(item.header.stamp.sec, item.header.stamp.nanosec): item for item in self.odometry}
        for transform in reversed(self.dynamic_tf):
            stamp = transform.header.stamp
            odom = odom_by_stamp.get((stamp.sec, stamp.nanosec))
            if (odom and transform.header.frame_id == odom.header.frame_id == ODOM_FRAME
                    and transform.child_frame_id == odom.child_frame_id == BASE):
                t, p = transform.transform.translation, odom.pose.pose.position
                if hypot(t.x - p.x, t.y - p.y, t.z - p.z) < 1e-5:
                    return True
        return False

    def interface_evidence(self, output):
        def ready():
            return (self.clock > 0 and self.pair() and self.dynamic_pair()
                    and any(t.header.frame_id == BASE and t.child_frame_id == OPTICAL for t in self.static_tf)
                    and self.command.get_subscription_count())

        self.wait(ready, "live camera, transform, odometry and command subscriber")
        owners = {}
        for topic in ("/clock", "/tf", "/tf_static", "/rackonaut/camera/image_raw",
                      "/rackonaut/camera/camera_info", "/rackonaut/drone/odom", CMD):
            publishers = self.get_publishers_info_by_topic(topic)
            check(len(publishers) == 1, f"{topic} has {len(publishers)} publishers in the isolated test domain")
            owner = publishers[0]
            owners[topic] = {"node": owner.node_name, "reliability": owner.qos_profile.reliability.name}
        image, info = self.pair()
        frame = self.bridge.imgmsg_to_cv2(image, desired_encoding="bgr8")
        check(frame.std() > 1 and cv2.imwrite(str(output / "x3-reference.png"), frame), "Invalid RGB frame")
        return {"camera": {"width": image.width, "height": image.height, "encoding": image.encoding,
                           "frame": image.header.frame_id, "stamp_s": seconds(image.header.stamp),
                           "fx": info.k[0], "fy": info.k[4]},
                "dynamic_tf_matches_odometry": True, "publishers": owners}

    def stop(self):
        self.command.publish(Twist())
        after = self.clock
        self.wait(lambda: self.clock - after >= 1 and self.speed < 0.10, "hover after zero", timeout=10,
                  command=Twist)

    def movement_evidence(self):
        origin = self.pose.position
        up = Twist()
        up.linear.z = 0.25
        self.wait(lambda: self.pose.position.z - origin.z >= 0.17, "positive Z motion", timeout=10, command=lambda: up)
        climb = self.pose.position.z - origin.z
        self.stop()

        def heading():
            q = self.pose.orientation
            return atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))

        initial_yaw = heading()
        turn = Twist()
        turn.angular.z = 0.35
        self.wait(lambda: heading() - initial_yaw >= 0.3, "positive yaw", timeout=10, command=lambda: turn)
        self.stop()
        yaw = heading()
        start = self.pose.position
        forward = Twist()
        forward.linear.x = 0.25

        def displacement():
            current = self.pose.position
            return current.x - start.x, current.y - start.y

        self.wait(lambda: hypot(*displacement()) >= 0.18, "body-forward motion", timeout=10, command=lambda: forward)
        dx, dy = displacement()
        along, across = dx * cos(yaw) + dy * sin(yaw), -dx * sin(yaw) + dy * cos(yaw)
        check(along >= 0.14 and abs(across) < 0.08, "Motion did not follow the rotated body +X axis")
        last_input = monotonic()
        self.wait(lambda: self.guarded_command is not None and self.guarded_command.linear.x == 0,
                  "watchdog zero after missing commands", timeout=1)
        watchdog_elapsed = monotonic() - last_input
        self.wait(lambda: self.speed < 0.10, "physical hover after command timeout", timeout=10)
        return {"climb_m": climb, "yaw_rad": yaw - initial_yaw, "body_forward_m": along,
                "cross_track_m": across, "watchdog_zero_s_after_publish_ceased": watchdog_elapsed,
                "hover_speed_m_s": self.speed}

    def warehouse_evidence(self, output):
        labels = []
        dictionary = cv2.aruco.Dictionary_get(cv2.aruco.DICT_4X4_50)
        for height, marker in ((0.76, 0), (2.70, 1)):
            def position_command():
                command = Twist()
                command.linear.z = max(-0.35, min(0.35, (height - self.pose.position.z) * 1.2))
                return command

            self.wait(lambda: abs(height - self.pose.position.z) < 0.055,
                      f"shelf height {height:.2f} m", timeout=35, command=position_command)
            self.stop()
            after = self.clock
            self.wait(lambda: self.pair(after), "a camera pair after settling", timeout=8)
            image, _ = self.pair(after)
            frame = self.bridge.imgmsg_to_cv2(image, desired_encoding="bgr8")
            _, markers, _ = cv2.aruco.detectMarkers(frame, dictionary)
            decoded = markers.flatten().tolist() if markers is not None else []
            check(marker in decoded, f"Expected ArUco {marker} at {height:.2f} m; decoded {decoded}")
            check(cv2.imwrite(str(output / f"x3-shelf-marker-{marker}.png"), frame), "Cannot save shelf image")
            labels.append({"marker": marker, "detected_markers": decoded,
                           "height_m": self.pose.position.z, "stamp_s": seconds(image.header.stamp)})
            # Leave the target stable long enough for the running perception node.
            settled = self.clock
            self.wait(lambda: self.clock - settled >= 2.5, "stable perception interval", timeout=10, command=Twist)
        return labels


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    p.add_argument("--warehouse", action="store_true", help="expect the documented warehouse spawn pose")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rclpy.init(args=[])
    probe = Probe()
    try:
        result = probe.interface_evidence(args.output)
        if args.warehouse:
            result["warehouse"] = probe.warehouse_evidence(args.output)
        else:
            result["motion"] = probe.movement_evidence()
        (args.output / "probe.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    finally:
        try:
            for _ in range(3):
                probe.command.publish(Twist())
                sleep(0.1)
        finally:
            probe.destroy_node()
            rclpy.try_shutdown()


if __name__ == "__main__":
    main()
