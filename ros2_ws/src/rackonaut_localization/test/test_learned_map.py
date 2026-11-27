import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import numpy as np
from scipy.spatial.transform import Rotation

from rackonaut_localization.learned_map import load, save
from rackonaut_localization.slam import FrozenRegistration, Keyframe
from rackonaut_localization.warehouse_config import (FORMAT, FRAME, REQUIRED, STORE, check_drone_model, digest,
                                                    file_hash, verified_package)


class LearnedMapTests(TestCase):
    def test_legacy_warehouse_is_reference_and_models_are_incompatible(self):
        check_drone_model({}, "reference")
        check_drone_model({"drone_model": "x3"}, "x3")
        with self.assertRaisesRegex(ValueError, "different drone model"):
            check_drone_model({}, "x3")
        with self.assertRaisesRegex(ValueError, "different drone model"):
            check_drone_model({"drone_model": "x3"}, "reference")

    def test_round_trip_preserves_dock_and_measured_normals(self):
        with TemporaryDirectory() as scratch:
            path = Path(scratch) / "localization.npz"
            dock = np.array([-4.7, 10.3, .05])
            points = np.array([[x*.15, y*.15, 0.] for x in range(12) for y in range(12)])
            normals = np.repeat([[0., 0., 1.]], len(points), axis=0)
            save(path, [Keyframe(dock, Rotation.identity(), points, normals)], dock)
            origin, frames = load(path)
            np.testing.assert_array_equal(origin, dock)
            np.testing.assert_allclose(frames[0].points, points, atol=1.e-6)
            np.testing.assert_array_equal(frames[0].normals, normals)
            registration = FrozenRegistration(frames, origin)
            self.assertFalse(registration.consider(points, np.zeros(3), dock+.6, Rotation.identity()))
            self.assertEqual(registration.keyframe_count, 1)

    def test_rejects_both_changed_payload_and_replaced_manifest(self):
        with TemporaryDirectory() as scratch:
            root = Path(scratch)
            temporary = root / STORE / "draft"
            photo = "locations/CAP-" + "A"*32 + "/reference.jpg"
            for name in REQUIRED | {photo}:
                path = temporary / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
            manifest = {"schema_version": FORMAT, "frame": FRAME, "mapping_id": "CAL-" + "E"*32,
                        "revision": 1, "files": {name: file_hash(temporary / name) for name in REQUIRED | {photo}}}
            identity = "WH-" + digest(manifest)[:32].upper()
            manifest["configuration_id"] = identity
            folder = temporary.rename(temporary.with_name(identity))
            marker = folder / "manifest.json"
            marker.write_text(json.dumps(manifest))
            self.assertEqual(verified_package(root, identity)[1], manifest)
            measured = folder / "map.ply"
            measured.write_bytes(b"replaced")
            with self.assertRaisesRegex(ValueError, "map.ply"):
                verified_package(root, identity)
            measured.write_bytes(b"map.ply")
            manifest["revision"] = 2
            marker.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "manifest integrity"):
                verified_package(root, identity)
