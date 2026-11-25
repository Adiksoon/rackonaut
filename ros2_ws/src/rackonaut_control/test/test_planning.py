import json
from unittest import TestCase
from xml.etree import ElementTree

from ament_index_python.packages import get_package_share_path

from rackonaut_control.planning import plan


class PlanningTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.share = get_package_share_path("rackonaut_warehouse")
        cls.layout = json.loads((cls.share / "config/control_layout.json").read_text())

    def test_layout_slots_match_world_placards(self):
        markers = json.loads((self.share / "config/control_markers.json").read_text())
        world = ElementTree.parse(self.share / "worlds/control_showcase.sdf")
        self.assertEqual(set(markers["locations"].values()), set(self.layout["slots"]))
        self.assertTrue(set(markers["locations"]).isdisjoint(markers["pallets"]))
        for marker, slot in markers["locations"].items():
            placard = world.find(f".//visual[@name='slot_{int(marker):02d}']/pose")
            self.assertEqual([float(value) for value in placard.text.split()[:3]], self.layout["slots"][slot]["label"])

    def test_crossings_use_the_front_corridor_in_both_directions(self):
        route = plan(self.layout, {"mode": "custom", "slots": ["A-01-02", "B-01-02"], "quality": True})
        self.assertEqual(route["slots"], ["A-01-02", "B-01-02"])
        cuts = []
        for (ax, ay, _), (bx, by, _) in zip(route["points"], route["points"][1:]):
            if min(ay, by) < -3 < max(ay, by):
                cuts.append((ax, bx))
        self.assertEqual(cuts, [(2.1, 2.1), (2.1, 2.1)])
        self.assertEqual(len([p for p in route["route"]["waypoints"] if "slot_id" in p]), 2)

    def test_modes_resolve_exact_scope(self):
        self.assertEqual(len(plan(self.layout, {"mode": "full"})["slots"]), 11)
        b_scope = plan(self.layout, {"mode": "aisle", "aisles": ["B"]})
        self.assertEqual(b_scope["slots"], ["B-01-01", "B-01-02", "B-02-01"])
        self.assertFalse(b_scope["quality"])
        with self.assertRaises(ValueError):
            plan(self.layout, {"mode": "aisle", "aisles": ["C"]})
        with self.assertRaises(ValueError):
            plan(self.layout, {"mode": "custom", "slots": []})
