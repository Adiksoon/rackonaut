"""Guard the evidence boundaries of template reconstruction."""
from types import SimpleNamespace
import unittest

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from rackonaut_control.reconstruction.twin import estimated_hit, fit_bays, fit_rack, keyframe_voxels


class TwinTest(unittest.TestCase):
    def test_complete_template_preserves_evidence_and_missing_measurements(self):
        posts = [[u, v, .23, 5.3] for u in (1.1, 6.3, 8.9) for v in (1., 2.2)]
        row = {"id": "R01", "yaw_rad": 0., "bounds_uv": [[1.1, 1.], [8.9, 2.2]], "posts": posts,
               "levels": [{"z": z, "patches_uv": [[1.1, 1., 1.6, 2.]]} for z in (.4, 2.4, 4.4)],
               "vertical_extent_m": [.23, 5.3], "support_points": 450}
        np.testing.assert_allclose(fit_bays(posts, 1.2)[:2], [1.1, 2.6])
        empty = np.empty((0, 3))
        result = fit_rack(row, .01, empty, empty)
        np.testing.assert_allclose(result["stations_u"], [1.1, 3.7, 6.3, 8.9])
        self.assertEqual(result["observed_bounds_uv"], row["bounds_uv"])
        self.assertEqual(result["observed_vertical_extent_m"], [.23, 5.3])
        self.assertEqual(result["end_extension_m"], [0., 0.])
        self.assertLess(max(result["quality"]["deck_area_support_fraction"]), .10)
        self.assertEqual(len(result["levels_m"]), 3)
        self.assertEqual(len(row["posts"]), 6)

    def test_repeated_keyframes_do_not_amplify_a_viewpoint(self):
        def frame(origin, points):
            return SimpleNamespace(position=np.array(origin), orientation=Rotation.identity(),
                                   points=np.array(points), normals=np.tile([0, 0, 1], (len(points), 1)))
        nearby = [.022, .015, .018]
        repeat = frame([0, 0, 0], [nearby, [4., 3., 1.02]])
        second_view = frame([3, 0, 0], [[4.01, 3., 1.03], [4.01, 3., 1.03], [6., 8., 1.]])
        centers, normals, details = keyframe_voxels([repeat, repeat, repeat, second_view], [nearby])
        self.assertEqual(details["pose_groups"], 2)
        self.assertEqual(details["occupied_voxels"], 3)
        self.assertEqual(details["retained_beyond_ply_18cm"], 1)
        np.testing.assert_allclose(centers, [nearby, [4.005, 3., 1.025]])
        np.testing.assert_array_equal(normals, [[0, 0, 1], [0, 0, 1]])

    def test_estimated_location_requires_unique_supported_rack(self):
        row = {"id": "R01", "yaw_rad": 0., "observed_bounds_uv": [[1., 1.], [7., 2.]],
               "levels_m": [.4, 2.4, 4.4]}
        next_row = {**row, "id": "R02", "observed_bounds_uv": [[1., 3.], [7., 4.]]}
        origin, ray = np.array([2., 0., .46]), np.array([0., 1., 0.])
        tree = cKDTree([[2., 1., .25], [2.29, 1., .33], [1.81, 1., .54], [2., 1.08, .59]])
        accepted = estimated_hit([row], tree, origin, ray)
        self.assertEqual(accepted["rack_id"], "R01")
        self.assertEqual(accepted["level"], 1)
        self.assertIsNone(estimated_hit([row, next_row], tree, origin, ray))
        self.assertIsNone(estimated_hit([row], cKDTree([[6., 1., .25]]), origin, ray))
