import json
from dataclasses import asdict
from unittest import TestCase
from xml.etree import ElementTree

from ament_index_python.packages import get_package_share_path

from rackonaut_control.planning import energy_forecast, plan
from rackonaut_energy.aerial import Network
from rackonaut_energy.model import Model


class PlanningTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.share = get_package_share_path("rackonaut_warehouse")
        cls.layout = json.loads((cls.share / "config/control_layout.json").read_text())

    def test_x3_splits_aerial_descent_inside_reserved_volume(self):
        layout = dict(self.layout)
        aerial = json.loads((self.share / "config/aerial_layout.json").read_text())
        layout.update(aerial=aerial, pad=aerial["pad"], takeoff_z=aerial["nodes"]["shaft"][2])
        selection = {"mode": "full", "quality": True}
        baseline = plan(layout, selection)
        candidate = plan(layout, selection, orthogonal_descent=True)
        self.assertEqual(candidate["slots"], baseline["slots"])
        self.assertEqual(candidate["required_zones"], baseline["required_zones"])
        waypoints = candidate["route"]["waypoints"]
        index = next(i for i, row in enumerate(waypoints) if row.get("slot_id") == "B-02-01")
        high, descent, low = waypoints[index - 2:index + 1]
        self.assertEqual(high["slot_id"], "B-01-02")
        self.assertEqual((descent["x"], descent["y"], descent["z"]), (high["x"], high["y"], low["z"]))
        self.assertEqual(descent["phase"], "AISLE_APPROACH")

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

    def test_aerial_crossing_keeps_ground_transfer_open_and_rejects_diagonal(self):
        profile = json.loads((self.share / "config/aerial_layout.json").read_text())
        layout = {**self.layout, "aerial": profile, "pad": profile["pad"], "takeoff_z": 6.7}
        route = plan(layout, {"mode": "custom", "slots": ["A-01-01", "B-01-01"]})
        network = Network(profile)
        pad = [part[:2] for part in profile["scene"]["parts"]["marking"] if part[3:5] == [2.65, 2.1]]
        self.assertEqual(pad, [[profile["pad"]["x"], profile["pad"]["y"]]])
        self.assertIn("D", {signal["zone"] for signal in profile["scene"]["signals"]})
        self.assertEqual(set(route["required_zones"]), {"D", "A", "B"})
        waypoints = route["route"]["waypoints"]
        self.assertEqual([p["gate"] for p in waypoints if p.get("phase") == "AISLE_DESCENT"], ["A", "B"])
        self.assertFalse(network.allows(network.nodes["entry_A"], network.nodes["entry_B"], route["required_zones"]))
        slot = layout["slots"]["B-02-01"]["viewpoint"]
        back = network.home(slot, route["required_zones"])
        self.assertEqual(back[-1].pose, network.nodes["dock"])
        self.assertIn("AISLE_ASCENT", [leg.phase for leg in back])
        telemetry = {"model": asdict(Model(hover=.26, movement=.19, climb=.52)), "percent": 100.}
        for location in layout["slots"]:
            single = plan(layout, {"mode": "custom", "slots": [location]})
            self.assertTrue(energy_forecast(layout, single, telemetry)["can_start"], location)

    def test_energy_forecast_includes_adaptive_motion_and_blocks_an_empty_battery(self):
        safety = json.loads((self.share / "config/safety_fields.json").read_text())
        layout = {**self.layout, "safety_fields": safety, "adaptive_world": True}
        route = plan(layout, {"mode": "custom", "slots": ["A-01-01"], "adaptive": True, "quality": True})
        forecast = energy_forecast(layout, route, {"model": asdict(Model()), "percent": 5.})
        self.assertFalse(forecast["can_start"])
        self.assertFalse(forecast["single_cycle"])
        self.assertGreater(forecast["adaptive_seconds"], 8.)
        self.assertGreater(forecast["minimum_percent"], forecast["return_percent"] + forecast["reserve_percent"])

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
