"""Check the safety scope against the generated warehouse and real routes."""

import json
import unittest

from ament_index_python.packages import get_package_share_path

from rackonaut_control.planning import plan
from rackonaut_safety.geometry import crosses, overlaps, route_zones


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = get_package_share_path("rackonaut_warehouse") / "config"
        cls.layout = json.loads((config / "control_layout.json").read_text())
        cls.fields = json.loads((config / "safety_fields.json").read_text())

    def test_aisle_routes_reserve_only_the_aisle_and_transfer(self):
        for aisle in ("A", "B"):
            with self.subTest(aisle=aisle):
                path = plan(self.layout, {"mode": "aisle", "aisles": [aisle]})["points"]
                self.assertEqual(route_zones(path, self.fields), [aisle, "T"])

    def test_full_and_cross_aisle_custom_routes_reserve_all_monitored_fields(self):
        for selection in ({"mode": "full"}, {"mode": "custom", "slots": ["A-01-03", "B-02-01"]}):
            with self.subTest(selection=selection):
                self.assertEqual(route_zones(plan(self.layout, selection)["points"], self.fields), ["A", "B", "T"])

    def test_path_intersection_and_worker_envelope_are_conservative_at_edges(self):
        aisle = self.fields["A"]
        self.assertTrue(crosses([1., 0., .79], [26., 0., .79], aisle))
        self.assertFalse(crosses([1., -3., .79], [26., -3., .79], aisle))
        self.assertTrue(overlaps([3.2, 0., 0.], aisle, margin=.28))
        self.assertFalse(overlaps([3.68, 3.9, 0.], aisle, margin=.28))


if __name__ == "__main__":
    unittest.main()
