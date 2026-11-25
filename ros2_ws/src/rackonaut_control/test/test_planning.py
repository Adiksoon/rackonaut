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

    def test_twin_uses_physical_bays_but_excludes_functional_stock(self):
        scene = self.layout["scene"]
        world = ElementTree.parse(self.share / "worlds/control_showcase.sdf")
        decks = [
            part for part in world.findall(".//model/link/visual") if part.attrib["name"].startswith("deck_")
        ]
        decor = [
            part for model in world.findall("world/model") for part in model.findall("link/visual")
            if part.attrib["name"].startswith(("decor_", "staged_")) and part.find("geometry/box") is not None
        ]
        self.assertEqual(len(scene["parts"]["deck"]), len(decks))
        self.assertEqual(len(scene["parts"]["decor"]), len(decor))
        self.assertEqual(len(scene["shell"]), 4)
        self.assertEqual({post["zone"] for post in scene["signals"]}, {"A", "B", "T"})
        deck_centers = {tuple(round(value, 3) for value in part[:3]) for part in scene["parts"]["deck"]}
        for slot in self.layout["slots"].values():
            x, y, deck = slot["bay_center"]
            self.assertIn((x, y, round(deck - .052, 3)), deck_centers)
        excluded = ("inspection_", "scenario", "pallet_id", "damage")
        self.assertFalse(any(term in json.dumps(self.layout) for term in excluded))

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

    def test_adaptive_moves_reserve_out_and_back_legs_in_laser_fields(self):
        selection = {"mode": "full", "adaptive": True}
        with self.assertRaises(ValueError):
            plan(self.layout, selection)
        safety = json.loads((self.share / "config/safety_fields.json").read_text())
        laser = json.loads((self.share / "config/laser_fields.json").read_text())
        planned = plan({**self.layout, "adaptive_world": True, "safety_fields": safety, "laser_fields": laser}, selection)
        reserved = list(zip(planned["safety_points"], planned["safety_points"][1:]))
        for waypoint in planned["route"]["waypoints"]:
            slot = waypoint.get("slot_id")
            if slot is None:
                continue
            entry = planned["route"]["retries"][slot]
            a, b, c, d = laser[entry["zone"]]["field"]
            original = [waypoint[key] for key in ("x", "y", "z")]
            self.assertTrue(entry["views"]["unreadable"])
            for candidates in entry["views"].values():
                for view in candidates:
                    alternate = [view[key] for key in ("x", "y", "z")]
                    self.assertTrue(a < alternate[0] < c and b < alternate[1] < d)
                    self.assertIn((original, alternate), reserved)
                    self.assertIn((alternate, original), reserved)
