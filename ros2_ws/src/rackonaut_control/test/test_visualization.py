import json
from pathlib import Path
import tempfile
from time import monotonic, sleep
import unittest
from unittest.mock import patch

from ament_index_python.packages import get_package_share_path
from rackonaut_control.visualization import ARTIFACT, Visualizations


class VisualizationTest(unittest.TestCase):
    def polling(self, models, session, **parameters):
        stop = monotonic() + 20
        while monotonic() < stop:
            result = models.get("calibration", session, **parameters)
            if result:
                return result
            sleep(.04)
        self.fail("The visualization job did not finish")

    def test_generated_artifact_is_persistent_and_tracks_location_revision(self):
        session = "CAL-" + "A" * 32
        camera = get_package_share_path("rackonaut_control") / "config" / "reference-camera.json"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "mapping" / session
            folder.mkdir(parents=True)
            header = ("ply\nformat binary_little_endian 1.0\nelement vertex 1\nproperty float x\n"
                      "property float y\nproperty float z\nend_header\n")
            (folder / "map.ply").write_bytes(header.encode() + bytes(12))
            manifest = {"mapping_id": session, "frame": "rackonaut_odom", "revision": 0, "locations": []}
            source = folder / "locations.json"
            source.write_text(json.dumps(manifest))
            (folder / "result.json").write_text(json.dumps({"mapping_id": session, "frame": "rackonaut_odom"}))
            models = Visualizations(root, camera)
            try:
                models.prime("calibration", session)
                body, etag = self.polling(models, session)
                artifact = folder / ARTIFACT
                self.assertTrue(artifact.is_file())
                first_stamp = artifact.stat().st_mtime_ns
                self.assertEqual(json.loads(body)["binding"]["revision"], 0)
                self.assertEqual(json.loads(body)["point_count"], 1)
            finally:
                models.close()
            models = Visualizations(root, camera)
            try:
                self.assertEqual(self.polling(models, session), (body, etag))
                self.assertEqual(artifact.stat().st_mtime_ns, first_stamp)
                manifest["revision"] += 1
                source.write_text(json.dumps(manifest))
                revised, new_etag = self.polling(models, session, private=True)
                self.assertEqual(json.loads(revised)["binding"]["revision"], 1)
                self.assertNotEqual(etag, new_etag)
                self.assertEqual(json.loads(source.read_bytes()), manifest)
            finally:
                models.close()

    def test_historical_visualization_uses_dispatch_revision(self):
        camera = get_package_share_path("rackonaut_control") / "config" / "reference-camera.json"
        run = "INS-CONTROL-20260101-000001-ABC"
        warehouse = "WH-" + "C" * 32
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dispatch = root / "dispatch" / run
            dispatch.mkdir(parents=True)
            (dispatch / "route.json").write_text(json.dumps({"learned": {
                "configuration_id": warehouse, "revision": 2,
            }}))
            models = Visualizations(root, camera)
            try:
                with patch.object(models, "get") as get:
                    models.for_run(run)
                    get.assert_called_once_with("warehouse", warehouse, 2)
                with self.assertRaises(FileNotFoundError):
                    models.for_run("INS-UNBOUND")
            finally:
                models.close()

    def test_camera_binding_comes_from_archive_and_mismatches_disable_projection(self):
        reference = get_package_share_path("rackonaut_control") / "config" / "reference-camera.json"
        x3 = reference.with_name("x3-camera.json")
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            result, sensors = folder / "result.json", folder / "sensors.json"
            model = Visualizations(folder, reference)
            try:
                result.write_text("{}")
                self.assertEqual(model.camera_for(folder), ("reference", reference))
                result.write_text('{"drone_model":"x3"}')
                self.assertEqual(model.camera_for(folder), ("x3", x3))
                camera = {"frame": "rackonaut_camera_optical_frame", "position_m": [.27, 0., .04]}
                sensors.write_text(json.dumps({"drone_model": "x3", "camera": camera}))
                self.assertEqual(model.camera_for(folder), ("x3", x3))
                for conflicting in ({}, {"drone_model": "x3", "camera": {**camera, "position_m": [.23, 0., 0.]}}):
                    sensors.write_text(json.dumps(conflicting))
                    self.assertEqual(model.camera_for(folder), (None, None))
                result.write_text('{"drone_model":"unknown"}')
                self.assertEqual(model.camera_for(folder), (None, None))
            finally:
                model.close()
