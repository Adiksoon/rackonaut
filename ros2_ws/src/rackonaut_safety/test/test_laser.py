from math import inf, nan
from types import SimpleNamespace
import unittest

from rackonaut_safety.laser import LaserPresence, scan_points


def scan(ranges, stamp=1, frame="fixed"):
    return SimpleNamespace(ranges=ranges, angle_min=-.2, angle_max=.2, angle_increment=.1,
                           range_min=.12, range_max=15.,
                           header=SimpleNamespace(frame_id=frame, stamp=SimpleNamespace(sec=stamp, nanosec=0)))


CONFIG = {"pose": [0., 2., .115, 0.], "field": [1., 1.5, 3., 2.5],
          "frame": "fixed", "arc": [-.2, .2], "samples": 5}


class LaserTests(unittest.TestCase):
    def test_wall_beyond_field_and_isolated_returns_do_not_occupy(self):
        points, hits = scan_points(scan([4., 4., 2., 4., 4.]), CONFIG)
        self.assertEqual(len(points), 5)
        self.assertEqual(hits, [])

    def test_three_neighboring_returns_mark_a_stationary_obstruction(self):
        _, hits = scan_points(scan([inf, 2., 2., 2., inf]), CONFIG)
        self.assertEqual(len(hits), 3)
        self.assertEqual(hits[1], (2., 2.))

    def test_bad_frames_nan_and_repeated_stamps_do_not_refresh_zone(self):
        laser = LaserPresence({"A": CONFIG, "B": CONFIG}, .75)
        laser.accept("A", scan([inf] * 5), 1., lambda: 1)
        laser.accept("A", scan([inf] * 5), 1.5, lambda: 1)
        laser.accept("A", scan([inf] * 5, stamp=2, frame="another"), 1.6, lambda: 1)
        laser.accept("A", scan([nan] * 5, stamp=3), 1.7, lambda: 1)
        self.assertEqual(laser.health("A", 1.8), "STALE")
        self.assertEqual(laser.health("B", 1.8), "UNKNOWN")
        laser.accept("A", scan([2.] * 5, stamp=4), 1.9, lambda: 22)
        self.assertEqual(laser.occupied(1.9), ["A"])
        self.assertEqual(laser.readings["A"].occupied_since_ns, 22)
        self.assertEqual(laser.occupied(3.), [])
