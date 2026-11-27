from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from rackonaut_control.node import Control, Job
from rackonaut_control.service import MAPPING
from rackonaut_control.teaching import Camera, Pose, SECOND, Teaching, session_path


SESSION = "CAL-" + "A"*32
OTHER = "CAL-" + "B"*32
OWNER = "service-token"
JPEG = b"camera-frame-bytes"


class TeachingTests(TestCase):
    def poses(self, moving=False):
        return [Pose(round(i*.05*SECOND), 1., (.1+i*.001, .2, .8),
                     tuple(Rotation.from_euler("z", i*.003).as_quat()),
                     .20 if moving and i == 14 else .009, .02, (.003, .004, .005))
                for i in range(1, 21)]

    def camera(self, when=.775, received=1.):
        return Camera(round(when*SECOND), received, "2026-11-26T12:00:00+00:00", "camera", JPEG)

    def test_pair_uses_camera_time_and_interpolates_both_pose_components(self):
        early, current = self.camera(.69), self.camera()
        capture, data = Teaching.pair(self.poses(), [early, current], 1.2)
        self.assertEqual(capture, current)
        self.assertEqual(data["camera_stamp"], {"sec": 0, "nanosec": 775000000})
        np.testing.assert_allclose(data["position_m"], [.1155, .2, .8], atol=1e-10)
        np.testing.assert_allclose(data["orientation_xyzw"], Rotation.from_euler("z", .0465).as_quat())
        self.assertEqual(data["sync"], {"before_ms": 25., "after_ms": 25.})

    def test_pair_rejects_move_stale_or_missing_bracket(self):
        for poses, camera in [(self.poses(True), self.camera()), (self.poses(), self.camera(received=0.)),
                              (self.poses(), self.camera(1.1)), (self.poses()[12:], self.camera())]:
            with self.subTest(camera=camera), self.assertRaises(RuntimeError):
                Teaching.pair(poses, [camera], 1.2)

    def test_sessions_durable_photo_duplicate_confirmation_and_rename(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            catalog = directory / "markers.json"
            catalog.write_text('{"dictionary":"DICT_4X4_50","locations":{"0":"A-01-01"},"pallets":{"40":"P001"}}')
            teaching = Teaching(directory, catalog)
            teaching.create(SESSION)
            self.assertEqual(teaching.manifest(SESSION)["locations"], [])
            camera, sample = Teaching.pair(self.poses(), [self.camera()], 1.2)
            actual = cv2.aruco.drawMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), 0, 100)
            image = np.full((150, 150), 255, dtype=np.uint8)
            image[25:125, 25:125] = actual
            encoded = cv2.imencode(".jpg", image)[1].tobytes()
            camera = Camera(camera.stamp, camera.received, camera.received_utc, camera.frame, encoded)
            item = teaching.preview(SESSION, OWNER, 0, {"state": "TRACKING"}, camera, sample, 1.2)
            self.assertEqual(item["suggested_id"], "A-01-01")
            with self.assertRaises(FileNotFoundError):
                teaching.get_preview(item["capture_id"], "another user", 1.2)
            capture = teaching.get_preview(item["capture_id"], OWNER, 1.2)
            request = {"storage_location_id": "X-NEW-25", "revision": 0}
            first = teaching.edit("save", SESSION, request, capture)
            record = first["locations"][0]
            self.assertEqual(record["id_source"], "operator")
            self.assertEqual(teaching.photo(SESSION, capture.identity), encoded)
            with self.assertRaises(RuntimeError):
                teaching.edit("save", SESSION, {**request, "revision": 1}, capture)
            with self.assertRaises(ValueError):
                teaching.edit("save", SESSION, {**request, "revision": 1, "record_id": record["record_id"]}, capture)
            changed = teaching.edit("rename", SESSION, {"storage_location_id": "X-NEW-26",
                                    "record_id": record["record_id"], "revision": 1})
            self.assertEqual(changed["locations"][0]["position_m"], record["position_m"])
            teaching.create(OTHER)
            restarted = Teaching(directory, None)
            self.assertEqual(restarted.manifest(OTHER)["locations"], [])
            self.assertEqual(restarted.manifest(SESSION), changed)
            deleted = restarted.edit("delete", SESSION, {"revision": 2, "record_id": record["record_id"], "confirm": True})
            self.assertEqual(deleted["locations"], [])
            self.assertTrue((directory/"mapping"/SESSION/record["reference_image"]).is_file())

    def test_registration_requires_active_reservation_and_hold_not_departure_permit(self):
        zone = {"sensor": "FRESH", "occupied": False, "signals_acknowledged": True}
        safety = {"inspection_id": "INS-FLIGHT", "phase": "RESERVED", "permit": False,
                  "signals_online": True, "required": ["A"], "zones": {"A": zone}}
        telemetry = {"localization": "TRACKING", "lidar": True, "imu": True, "connection": True}
        manual = {"state": "HOLD"}
        flight = Job("INS-FLIGHT", {}, [], mapping_id=SESSION, manual_token="lease",
                     status_at=1., status={"stage": "MANUAL_FLIGHT", "manual": manual, "motion_owned": True})
        control = SimpleNamespace(job=flight, calibration=SimpleNamespace(state=MAPPING), stage=Control.stage,
                                  mapping_status=lambda: {"mapping_id": SESSION, "mapping_phase": "RECORDING", "source": "slam"},
                                  service_telemetry=lambda _: telemetry, safety_status=lambda: safety,
                                  energy_state=lambda: {"fresh": True, "budget_verified": True, "contact": False})
        self.assertIsNone(Control.teaching_gate(control, 1.1))
        manual["state"] = "MOVING"
        self.assertIn("hold position", Control.teaching_gate(control, 1.1))
        manual["state"] = "HOLD"
        telemetry["localization"] = "LOST"
        self.assertIn("TRACKING", Control.teaching_gate(control, 1.1))
        telemetry["localization"] = "TRACKING"
        for unsafe in ("RECOVERY", "RELEASED"):
            safety["phase"] = unsafe
            self.assertIn("Safety reservation", Control.teaching_gate(control, 1.1))
        safety["phase"] = "RESERVED"
        zone["occupied"] = True
        self.assertIn("Safety reservation", Control.teaching_gate(control, 1.1))

    def test_path_checks_reject_non_session_and_symbolic_escape(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for identity in ("../outside", "", None):
                with self.assertRaises(ValueError):
                    session_path(root, identity)
            (root/SESSION).symlink_to(root.parent)
            with self.assertRaises(ValueError):
                session_path(root, SESSION, "locations.json")
