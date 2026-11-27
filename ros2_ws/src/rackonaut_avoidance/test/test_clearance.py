from math import pi
from unittest import TestCase
from unittest.mock import Mock, patch

import numpy as np
from sensor_msgs.msg import PointCloud2, PointField

from rackonaut_avoidance.manual import ZERO, protect
from rackonaut_avoidance.planner import Navigator, sweep
from rackonaut_avoidance.sensor import (
    BEAMS, FRAME, FULL_ROUTE_RANGE, HEIGHT, MAX_RANGE, STALE_SECONDS, WIDTH,
    Cloud, Scanner, rotation, unpack,
)


class ClearanceTests(TestCase):
    def test_exact_pairing_retains_delayed_pose_without_refreshing_scan(self):
        scanner = Scanner(Mock(), exact_pose=True)
        older, newer = PointCloud2(), PointCloud2()
        older.header.stamp.sec, newer.header.stamp.sec = 20, 21
        scanner.poses.append((19., np.zeros(3), np.eye(3)))
        unpacked = np.ones((1, 1)), np.empty((0, 3)), np.empty((0, 3))
        with patch("rackonaut_avoidance.sensor.monotonic", return_value=100.):
            scanner.receive(older)
        self.assertIsNone(scanner.current(100.15))
        with patch("rackonaut_avoidance.sensor.monotonic", return_value=100.20):
            scanner.receive(newer)
        scanner.poses.append((20., np.zeros(3), np.eye(3)))
        with patch("rackonaut_avoidance.sensor.unpack", return_value=unpacked):
            cloud = scanner.current(100.21)
            self.assertEqual((cloud.time, cloud.received), (20., 100.))
            scanner.poses.append((21., np.zeros(3), np.eye(3)))
            cloud = scanner.current(100.22)
            self.assertEqual((cloud.time, cloud.received), (21., 100.20))
            self.assertIsNone(scanner.current(100.20 + STALE_SECONDS + .01))

    def test_exact_pairing_does_not_recover_an_expired_scan_on_late_odometry(self):
        scanner = Scanner(Mock(), exact_pose=True)
        scan = PointCloud2()
        scan.header.stamp.sec = 20
        with patch("rackonaut_avoidance.sensor.monotonic", return_value=100.):
            scanner.receive(scan)
        scanner.poses.append((20., np.zeros(3), np.eye(3)))
        with patch("rackonaut_avoidance.sensor.unpack") as decode:
            self.assertIsNone(scanner.current(100. + STALE_SECONDS + .01))
        decode.assert_not_called()

    def frame(self, points=(), ranges=None):
        return Cloud(1., 2., np.array([0., 0., .88]), np.eye(3),
                     np.full((HEIGHT, WIDTH), 8. if ranges is None else ranges),
                     np.array(points).reshape(-1, 3), np.empty((0, 3)))

    def test_swept_rotor_volume_detects_an_off_axis_return(self):
        check = sweep(self.frame([(1.02, .33, .82)]), (0., 0., .79), (2., 0., .79), 1.5)
        self.assertIsNotNone(check.hit)
        self.assertLess(check.hit, 1.0)
        self.assertFalse(check.confirmed)

    def test_unobserved_volume_is_not_clear_and_stale_cloud_fails(self):
        check = sweep(self.frame(ranges=np.nan), (0., 0., .79), (1., 0., .79), 1.)
        self.assertIsNone(check.hit)
        self.assertIsNotNone(check.unknown)
        nav = Navigator()
        result = nav.step(None, (0., 0., .79, 0.), (1., 0., .79, 0.), "TRANSIT", .2, 4.,
                          True, lambda *args: True, lambda *args: 1.)
        self.assertFalse(result.advance)
        self.assertEqual(result.scale, 0.)
        self.assertEqual(nav.mode, "FAULT")

    def test_signed_range_limits_keep_near_beams_blocked(self):
        pixels = (BEAMS * 2.).astype("<f4")
        pixels[5, 12] = np.copysign(np.inf, BEAMS[5, 12])
        pixels[4, 13] = -np.copysign(np.inf, BEAMS[4, 13])
        msg = PointCloud2(height=HEIGHT, width=WIDTH, point_step=12, row_step=12*WIDTH,
                          fields=[PointField(name=name, offset=4*i, datatype=PointField.FLOAT32, count=1)
                                  for i, name in enumerate("xyz")], data=pixels.tobytes())
        msg.header.frame_id = FRAME
        health, points, near = unpack(msg)
        self.assertEqual(health[5, 12], 8.)
        self.assertTrue(np.isnan(health[4, 13]))
        self.assertEqual(len(points), WIDTH*HEIGHT-2)
        np.testing.assert_allclose(near, [BEAMS[4, 13]])

    def test_body_to_world_yaw_preserves_sensor_axes(self):
        angle = pi / 4
        matrix = rotation(np.array([0., 0., np.sin(angle), np.cos(angle)]))
        np.testing.assert_allclose(matrix @ [1., 0., 0.], [0., 1., 0.], atol=1e-7)

    def test_full_route_measurements_keep_the_original_motion_guard_horizon(self):
        pixels = (BEAMS * 2.).astype("<f4")
        pixels[5, 12] = BEAMS[5, 12] * 12.
        points = PointCloud2(height=HEIGHT, width=WIDTH, point_step=12, row_step=12*WIDTH,
                             fields=[PointField(name=name, offset=4*i, datatype=PointField.FLOAT32, count=1)
                                     for i, name in enumerate("xyz")], data=pixels.tobytes())
        points.header.frame_id = FRAME
        points.header.stamp.sec = 1
        ranges, returns, _ = unpack(points, sensor_range=FULL_ROUTE_RANGE)
        self.assertAlmostEqual(ranges[5, 12], 12., places=4)
        self.assertEqual(len(returns), WIDTH * HEIGHT)

        scanner = Scanner(Mock(), sensor_range=FULL_ROUTE_RANGE)
        scanner.poses.append((1., np.zeros(3), np.eye(3)))
        scanner.pending = points, 2.
        cloud = scanner.current(2.)
        self.assertEqual(cloud.ranges[5, 12], MAX_RANGE)
        self.assertEqual(len(cloud.hits), WIDTH * HEIGHT - 1)

    def test_manual_obstacles_stop_forward_side_and_vertical_commands(self):
        pose = (0., 0., .79, 0.)
        for point, request in [
            ((.58, 0., .79), (.3, 0., 0., 0.)),
            ((0., -.58, .79), (0., -.3, 0., 0.)),
            ((0., 0., 1.09), (0., 0., .2, 0.)),
            ((0., 0., .45), (0., 0., -.2, 0.)),
        ]:
            with self.subTest(point=point):
                motion = protect(self.frame([point]), pose, ZERO, request, 2.1, lambda a, b: True)
                self.assertEqual(motion.velocity, ZERO)
                self.assertEqual(motion.state, "BLOCKED")
                self.assertIsNotNone(motion.scan.hit)

    def test_manual_yaw_requires_observed_rotor_clearance(self):
        pose = (0., 0., .79, 0.)
        request = (0., 0., 0., .3)
        self.assertEqual(protect(self.frame(), pose, ZERO, request, 2.1, lambda a, b: True).velocity, request)
        self.assertEqual(protect(self.frame(ranges=np.nan), pose, ZERO, request, 2.1,
                                 lambda a, b: True).velocity, ZERO)
        self.assertEqual(protect(self.frame([(.4, 0., .79)]), pose, ZERO, request, 2.1,
                                 lambda a, b: True).velocity, ZERO)

    def test_manual_speed_reduces_before_wall_and_then_brakes(self):
        pose = (0., 0., .79, 0.)
        cloud = self.frame([(.85, 0., .79)])
        request = (.4, 0., 0., 0.)
        reduced = protect(cloud, pose, ZERO, request, 2.1, lambda a, b: True)
        self.assertEqual(reduced.state, "LIMITED")
        self.assertGreater(reduced.velocity[0], 0.)
        self.assertLess(reduced.velocity[0], request[0])
        braking = protect(cloud, pose, (.4, 0., 0.), request, 2.4, lambda a, b: True)
        self.assertEqual(braking.state, "BRAKING")
        self.assertEqual(braking.velocity, ZERO)
