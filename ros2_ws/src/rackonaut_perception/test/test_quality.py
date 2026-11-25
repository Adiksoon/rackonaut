import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

import cv2

from rackonaut_perception.observations import observation
from rackonaut_perception.quality import inspect_carton
from rackonaut_perception.quality_evidence import QualityEvidence
from rackonaut_perception.vision import Inspector, load_markers


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/quality"


class QualityTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Inspector(*load_markers(ROOT / "config/markers.json"))

    def inspect(self, file):
        image = cv2.imread(str(EVIDENCE / file))
        self.assertIsNotNone(image)
        reading, = self.engine.inspect(image).readings
        return image, reading, inspect_carton(image, reading)

    def test_real_camera_frames_include_occlusion_and_moved_damage(self):
        cases = (
            ("01-intact/camera.png", "A-01-01", "P001", "OK"),
            ("02-torn/camera.png", "A-01-02", "P003", "DAMAGED"),
            ("03-crushed/camera.png", "A-01-04", "P999", "DAMAGED"),
            ("04-uncertain-camera.png", "A-01-01", "P001", "UNCERTAIN"),
            ("05-moved-tear/camera.png", "A-01-01", "P001", "DAMAGED"),
        )
        for filename, slot, pallet, status in cases:
            with self.subTest(filename=filename):
                _, reading, verdict = self.inspect(filename)
                self.assertEqual((reading.slot.name, reading.classification.pallet_id, verdict.status),
                                 (slot, pallet, status))
                self.assertEqual(verdict.defect is not None, status == "DAMAGED")

    def test_capture_waits_for_stability_and_keeps_inventory_link(self):
        image, reading, verdict = self.inspect("02-torn/camera.png")
        slot = reading.slot.name
        timestamp = datetime(2026, 11, 25, 9, 0, tzinfo=timezone.utc)
        event = observation("INS-QUALITY-TEST", reading, timestamp)
        header = SimpleNamespace(frame_id="rackonaut_camera_optical_frame",
                                 stamp=SimpleNamespace(sec=4, nanosec=1))
        with TemporaryDirectory() as directory:
            recorder = QualityEvidence(directory, event["inspection_id"])
            for frame in range(6):
                self.assertFalse(recorder.ready({slot: verdict}, [reading], {slot: event}, frame / 10))
            ready = recorder.ready({slot: verdict}, [reading], {slot: event}, .6)
            self.assertEqual(len(ready), 1)
            saved = recorder.save(ready[0], image, image, timestamp, header)
            report = json.loads((saved / "report.json").read_text())
            self.assertEqual(report["observation_id"], event["observation_id"])
            self.assertEqual(report["status"], "DAMAGED")
            self.assertEqual(recorder.damage_count(), 1)
            self.assertTrue((saved / "camera.png").is_file())
            self.assertTrue((saved / "annotated.png").is_file())
            self.assertFalse(recorder.ready({slot: verdict}, [reading], {slot: event}, .7))
