#!/usr/bin/python3
"""Exercise local ROS transport and the reference simulator through their public topics."""
import argparse
from collections import deque
import time

import cv2
from cv_bridge import CvBridge
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import CameraInfo, Image


class Probe(Node):
    def __init__(self, reference):
        super().__init__("rackonaut_reference_probe")
        self.images = deque(maxlen=16)
        self.calibrations = deque(maxlen=16)
        self.odometry = None
        self.first_clock = None
        self.last_clock = None
        self.commands = None
        self.create_subscription(Image, "/rackonaut/camera/image_raw", self.images.append, qos_profile_sensor_data)
        self.create_subscription(
            CameraInfo, "/rackonaut/camera/camera_info", self.calibrations.append, qos_profile_sensor_data
        )
        if reference:
            self.create_subscription(Odometry, "/rackonaut/drone/odom", self.on_odom, qos_profile_sensor_data)
            self.create_subscription(Clock, "/clock", self.on_clock, qos_profile_sensor_data)
            self.commands = self.create_publisher(Twist, "/rackonaut/drone/cmd_vel", 10)

    def on_odom(self, message):
        self.odometry = message

    def on_clock(self, message):
        stamp = (message.clock.sec, message.clock.nanosec)
        if self.first_clock is None:
            self.first_clock = stamp
        self.last_clock = stamp

    def sample(self):
        for image in reversed(self.images):
            for info in reversed(self.calibrations):
                if (
                    image.header == info.header
                    and image.header.frame_id == "rackonaut_camera_optical_frame"
                    and image.width == info.width and image.height == info.height and info.k[0] > 0
                ):
                    return image
        return None


def report(test_id, passed, evidence):
    print(f"{test_id} {'PASS' if passed else 'FAIL'}  {evidence}", flush=True)
    return passed


def describe_image(sample):
    return (
        f"{sample.width}x{sample.height} {sample.encoding}, "
        f"frame {sample.header.frame_id}, stamp {sample.header.stamp.sec}.{sample.header.stamp.nanosec:09d}"
    )


def convert_image(image):
    try:
        frame = CvBridge().imgmsg_to_cv2(image, desired_encoding="bgr8")
        contrast = cv2.meanStdDev(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))[1].item()
        passed = frame.shape == (image.height, image.width, 3) and contrast > 1.0
        return passed, f"BGR shape {frame.shape}, grayscale standard deviation {contrast:.1f}"
    except Exception as exc:
        return False, f"OpenCV/cv_bridge conversion failed: {exc}"


def drive_up(probe, odometry):
    if odometry is None or probe.commands.get_subscription_count() == 0:
        return False, "no odometry or command subscriber discovered"
    initial = odometry.pose.pose.position.z
    highest = initial
    command = Twist()
    command.linear.z = 0.25
    deadline = time.monotonic() + 4.0
    try:
        while time.monotonic() < deadline and highest - initial < 0.15:
            probe.commands.publish(command)
            rclpy.spin_once(probe, timeout_sec=0.10)
            highest = max(highest, probe.odometry.pose.pose.position.z)
            time.sleep(0.05)
    finally:
        for _ in range(5):
            probe.commands.publish(Twist())
            time.sleep(0.05)
    return highest - initial >= 0.15, f"command +0.25 m/s, measured z {initial:.3f} -> {highest:.3f} m"


def run(probe, reference, deadline):
    sample = None
    clock = False
    while time.monotonic() < deadline:
        rclpy.spin_once(probe, timeout_sec=0.2)
        sample = probe.sample()
        clock = probe.first_clock is not None and probe.first_clock < probe.last_clock
        if sample is not None and (not reference or (clock and probe.odometry is not None)):
            break

    evidence = describe_image(sample) if sample is not None else (
        f"no RGB/CameraInfo pair, received {len(probe.images)} images and {len(probe.calibrations)} CameraInfo"
    )
    if not reference:
        if sample is None:
            return report("ROS-02", False, evidence)
        passed, conversion = convert_image(sample)
        return report("ROS-02", passed, f"synthetic publisher/subscriber paired: {evidence}; {conversion}")

    odom = probe.odometry
    clock_ok = report("SIM-01", clock, f"sim clock {probe.first_clock} -> {probe.last_clock}")
    spawn_ok = report(
        "SIM-02", odom is not None,
        f"odometry {odom.header.frame_id} -> {odom.child_frame_id}" if odom else "no reference drone odometry",
    )
    movement_ok = report("SIM-03", *drive_up(probe, odom))
    camera_ok = report("CAM-01", sample is not None, f"Gazebo RGB/CameraInfo: {evidence}")
    if sample is not None:
        conversion_ok = report("CV-01", *convert_image(sample))
    else:
        print("CV-01 BLOCKED  no paired simulated frame to convert", flush=True)
        conversion_ok = False
    return all((clock_ok, spawn_ok, movement_ok, camera_ok, conversion_ok))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", action="store_true")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    rclpy.init(args=[])
    probe = Probe(args.reference)
    try:
        return 0 if run(probe, args.reference, time.monotonic() + args.timeout) else 1
    finally:
        probe.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
