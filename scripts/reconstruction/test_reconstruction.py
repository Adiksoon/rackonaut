"""Regression tests for conservative geometry and camera projection."""
from base64 import b64decode
from pathlib import Path
import unittest

import numpy as np

from geometry import reconstruct
from reconstruct import projected_hits, read_json
from validate import angle_error, perturb


class ReconstructionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = Path(__file__).resolve().parents[2]
        cls.bundle = read_json(base / "docs/reconstruction-evidence/goal24.json")
        cls.points = np.frombuffer(b64decode(cls.bundle["points_f32le"]),"<f4").reshape(-1,3).astype(float)

    def test_reconstructs_supported_shelves_with_empty_cells(self):
        rows,_ = reconstruct(self.points)
        self.assertEqual(len(rows),2)
        for row in rows:
            self.assertEqual(len(row["levels"]),3)
            self.assertGreater(row["support_points"],200)
            self.assertGreater(len(row["posts"]),2)
            for level in row["levels"]:
                self.assertGreater(len(level["patches_uv"]),10)

    def test_real_cloud_with_removed_rows_and_a_rotated_frame(self):
        erased,partial,rotated = perturb(self.bundle)
        self.assertEqual(erased["rows"],1)
        self.assertEqual(partial["rows"],0)
        self.assertEqual(rotated["rows"],2)
        self.assertTrue(all(angle_error(np.radians(yaw), np.radians(27)) < 1. for yaw in rotated["yaw_deg_mod_180"]))

    def test_projection_reports_all_supported_faces_before_deciding(self):
        rows = [{"id":name,"yaw_rad":0.,"bounds_uv":[[-2.,v],[2.,v+1.]],
                 "levels":[{"z":1.,"patches_uv":[[-.5,v,.5,v+.5]]}]}
                for name,v in [("near",2.),("far",5.)]]
        points = np.asarray([[x,v,z] for x in (-.12,0.,.12) for z in (.9,1.1) for v in (2.,5.)])
        result = list(projected_hits(np.array([0.,0.,1.]),np.array([0.,1.,0.]),points,rows))
        self.assertEqual([item["rack_id"] for item in result],["near","far"])
        self.assertEqual(list(projected_hits(np.array([0.,0.,1.]),np.array([1.,0.,0.]),points,rows)),[])


if __name__ == "__main__":
    unittest.main()
