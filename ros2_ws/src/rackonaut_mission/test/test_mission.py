from datetime import datetime, timezone
from math import hypot, pi, radians
from pathlib import Path
from unittest import TestCase

from rackonaut_mission.adaptive import next_issue
from rackonaut_mission.confirmation import current_observation
from rackonaut_mission.route import Target, heading_error, load_route, velocity


class MissionTests(TestCase):
    def test_adaptive_request_depends_on_observation_and_linked_photo(self):
        readable = {"occupancy": "occupied", "label_status": "readable", "pallet_id": "P999"}
        damaged = {"status": "DAMAGED"}
        self.assertEqual(next_issue(None, None, False), "missing")
        self.assertEqual(next_issue(dict(readable, occupancy="uncertain"), damaged, False), "uncertain")
        self.assertEqual(next_issue(dict(readable, label_status="unreadable"), damaged, False), "unreadable")
        self.assertEqual(next_issue(readable, damaged, False), "damage")
        self.assertIsNone(next_issue(readable, damaged, True))
        self.assertIsNone(next_issue(readable, None, False))

    def test_world_error_rotates_into_body_frame(self):
        pose = Target(0, 0, .79, pi / 2)
        forward, left, up, yaw = velocity(Target(5, 0, 3, pi / 2), pose)
        self.assertAlmostEqual(forward, 0.)
        self.assertAlmostEqual(left, -.56)
        self.assertAlmostEqual(hypot(forward, left), .56)
        self.assertAlmostEqual(up, .50)
        self.assertAlmostEqual(yaw, 0.)
        self.assertAlmostEqual(heading_error(radians(-179), radians(179)), radians(2))

    def test_default_route_has_five_distinct_stops(self):
        route = load_route(Path(__file__).resolve().parents[1] / "config/showcase.json")
        self.assertGreater(route.takeoff.z, route.pad.z)
        self.assertEqual([stop.slot_id for stop in route.stops], [f"A-01-0{n}" for n in range(1, 6)])
        self.assertTrue(all(stop.yaw == pi / 2 for stop in route.stops))

    def test_confirmation_excludes_wrong_stale_seen_and_future_observations(self):
        since = datetime(2026, 11, 25, 8, 0, 30, tzinfo=timezone.utc)
        now = datetime(2026, 11, 25, 8, 0, 35, tzinfo=timezone.utc)
        current = {
            "inspection_id": "INS-CURRENT",
            "slot_id": "A-01-03",
            "observation_id": "OBS-A",
            "timestamp": "2026-11-25T08:00:33.123Z",
            "occupancy": "occupied",
            "pallet_id": "P999",
        }
        rejected = [
            dict(current, observation_id="OBS-STALE", timestamp="2026-11-25T08:00:29.999Z"),
            dict(current, observation_id="OBS-FUTURE", timestamp="2026-11-25T08:05:00Z"),
            dict(current, observation_id="OBS-OTHER", slot_id="A-01-04"),
            dict(current, observation_id="OBS-PRIOR", inspection_id="INS-PRIOR"),
            dict(current, observation_id="OBS-SEEN"),
        ]
        args = ("INS-CURRENT", "A-01-03", since, {"OBS-SEEN"}, now)
        self.assertIsNone(current_observation(rejected, *args))
        self.assertEqual(current_observation([*rejected, current], *args), current)
