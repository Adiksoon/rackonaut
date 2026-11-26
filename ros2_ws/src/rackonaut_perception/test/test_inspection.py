import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import URLError

import cv2
import numpy as np

from rackonaut_perception.observations import StableReadings, observation, post_observation
from rackonaut_perception.vision import Classification, Inspector, load_markers

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT.parent / "rackonaut_warehouse/docs/evidence"


class InspectionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Inspector(*load_markers(ROOT / "config/markers.json"))

    def readings(self, pattern):
        path = next(EVIDENCE.glob(pattern))
        return self.engine.inspect(cv2.imread(str(path))).readings

    def test_original_gazebo_camera_frames(self):
        for pattern, slot, expected in (
            ("07*", "A-01-01", Classification("occupied", "readable", "P001")),
            ("08*", "A-01-03", Classification("empty", "not_applicable")),
            ("09*", "A-01-05", Classification("occupied", "unreadable")),
        ):
            with self.subTest(pattern=pattern):
                actual = self.readings(pattern)
                self.assertEqual([(r.slot.name, r.classification) for r in actual], [(slot, expected)])

    def test_multiple_locations_are_handled_independently(self):
        first = cv2.imread(str(next(EVIDENCE.glob("07*"))))
        second = cv2.imread(str(next(EVIDENCE.glob("08*"))))
        result = self.engine.inspect(np.hstack((first, second)))
        self.assertEqual([(r.slot.name, r.classification.pallet_id, r.classification.occupancy) for r in result.readings],
                         [("A-01-01", "P001", "occupied"), ("A-01-03", None, "empty")])

    def test_missing_frame_breaks_streak_and_rearm_allows_reinspection(self):
        reading = self.readings("07*")
        gate = StableReadings(stable_frames=3)
        self.assertEqual(gate.update(reading, 0), [])
        self.assertEqual(gate.update([], .1), [])
        self.assertEqual(gate.update(reading, .2), [])
        self.assertEqual(gate.update(reading, .3), [])
        self.assertEqual(gate.update(reading, .4), reading)
        gate.record(reading[0])
        self.assertEqual(gate.update(reading, .5), [])
        gate.rearm()
        self.assertEqual(gate.update(reading, .6), [])
        self.assertEqual(gate.update(reading, .7), [])
        self.assertEqual(gate.update(reading, .8), reading)

    def test_uncertain_reading_requires_a_framed_streak(self):
        reading = replace(self.readings("07*")[0], classification=Classification("uncertain", "unknown"))
        cropped = replace(reading, reason="Frame the whole slot")
        framed = replace(reading, reason="Shelf edge unclear")
        gate = StableReadings(stable_frames=2, uncertain_frames=3)
        for index in range(4):
            self.assertEqual(gate.update([cropped], .1 * index), [])
        self.assertEqual(gate.update([framed], .4), [])
        self.assertEqual(gate.update([framed], .5), [])
        self.assertEqual(gate.update([framed], .6), [framed])

    @patch("rackonaut_perception.observations.sleep")
    @patch("rackonaut_perception.observations.urlopen")
    def test_transport_retries_identical_observation(self, open_url, _):
        reading = self.readings("07*")[0]
        event = observation("INS-TEST", reading, datetime.now(timezone.utc))
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(status=200))
        response.__exit__ = Mock(return_value=False)
        open_url.side_effect = [URLError("unavailable"), response]
        self.assertEqual(post_observation("http://127.0.0.1:8000", event), (True, "HTTP 200"))
        first, second = (call.args[0].data for call in open_url.call_args_list)
        self.assertEqual(first, second)
        self.assertEqual(json.loads(first), event)
