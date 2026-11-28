import json
from collections import Counter
from unittest import TestCase
from xml.etree import ElementTree

from ament_index_python.packages import get_package_share_path

from rackonaut_avoidance.planner import HALF_HEIGHT, RADIUS
from rackonaut_energy.aerial import Network


def box_data(element):
    return tuple(map(float, (
        element.findtext("pose").split()[:3] + element.findtext("geometry/box/size").split()
    )))


def intersects(sweep, solid):
    return all(sweep[i] < solid[i] + solid[i + 3] / 2 - 1e-8
               and sweep[i + 3] > solid[i] - solid[i + 3] / 2 + 1e-8 for i in range(3))


class OpenAisleTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.share = get_package_share_path("rackonaut_warehouse")
        cls.historical = cls.config("aerial_layout.json")
        cls.open_aisle = cls.config("open_aisle_aerial_layout.json")

    @classmethod
    def config(cls, name):
        return json.loads((cls.share / "config" / name).read_text())

    @classmethod
    def world(cls, name):
        return ElementTree.parse(cls.share / "worlds" / name).find("world")

    def test_new_worlds_change_only_the_aerial_installation(self):
        for file in ("localization_showcase.sdf", "localization_laser_showcase.sdf"):
            historical, open_aisle = self.world(file), self.world("open_aisle_" + file)
            for world in (historical, open_aisle):
                world.remove(world.find("model[@name='protected_flight_infrastructure']"))
            self.assertEqual(ElementTree.tostring(open_aisle), ElementTree.tostring(historical))
        for key in ("nodes", "edges", "gates", "inspection_volumes", "technical", "pad", "dock", "scene"):
            self.assertEqual(self.open_aisle[key], self.historical[key], key)

    def test_twin_and_static_localization_use_the_same_changed_geometry_as_gazebo(self):
        boxes = {}
        for prefix in ("", "open_aisle_"):
            world = self.world(prefix + "localization_showcase.sdf")
            visuals = world.findall("model[@name='protected_flight_infrastructure']/link/visual")
            boxes[prefix] = Counter(box_data(part) for part in visuals if part.find("geometry/box") is not None)
        twin = Counter(tuple(float(f"{value:.5g}") for value in part[:6])
                       for key in ("parts", "screens") for part in self.open_aisle[key])
        self.assertEqual(twin, boxes["open_aisle_"])
        historical_map = self.config("localization_map.json")
        open_map = self.config("open_aisle_localization_map.json")
        self.assertEqual(open_map["world_frame"], historical_map["world_frame"])
        self.assertEqual(open_map["triangles"], historical_map["triangles"])
        old, new = (Counter(map(tuple, data["boxes"])) for data in (historical_map, open_map))
        self.assertEqual(old - new, boxes[""] - twin)
        self.assertEqual(new - old, twin - boxes[""])

    def test_overhead_turns_have_floors_and_only_connected_faces_are_open(self):
        world = self.world("open_aisle_localization_showcase.sdf")
        structure = world.find("model[@name='protected_flight_infrastructure']/link")
        solids = set(map(box_data, structure.findall("collision")))
        network = Network(self.open_aisle)
        for joint, closed in (("junction", {(0, 1), (1, 1)}),
                              ("trunk_A", {(0, -1)}),
                              ("trunk_B", {(0, -1), (1, -1)})):
            with self.subTest(joint=joint):
                x, y, z = network.nodes[joint][:3]
                self.assertIn((x, y, round(z - .6, 3), 1.86, 1.86, .035), solids)
                for axis in (0, 1):
                    for side in (-1, 1):
                        px = round(x + side*.91, 3) if axis == 0 else x
                        py = round(y + side*.91, 3) if axis == 1 else y
                        size = (.032, 1.86, 1.10) if axis == 0 else (1.86, .032, 1.10)
                        self.assertEqual((px, py, z, *size) in solids, (axis, side) in closed)
                radius, half = .33 + RADIUS, .33 + HALF_HEIGHT
                self.assertFalse(any(intersects(
                    (x-radius, y-radius, z-half, x+radius, y+radius, z+half), solid
                ) for solid in solids))

    def test_both_portals_clear_the_shared_guard_volume_and_keep_zone_requirements(self):
        network = Network(self.open_aisle)
        world = self.world("open_aisle_localization_showcase.sdf")
        structure = world.find("model[@name='protected_flight_infrastructure']/link")
        solids = [box_data(part) for part in structure.findall("collision")]
        visuals = [box_data(part) for part in structure.findall("visual") if part.find("geometry/box") is not None]
        for zone in ("A", "B"):
            with self.subTest(zone=zone):
                trunk = network.nodes[f"trunk_{zone}"][:3]
                entry = network.nodes[f"entry_{zone}"][:3]
                foot = network.nodes[f"foot_{zone}"][:3]
                for start, end in ((trunk, entry), (entry, foot), (foot, entry)):
                    edge = next(box for a, b, _, box in network.edges
                                if {network.nodes[a][:3], network.nodes[b][:3]} == {start, end})
                    size = (RADIUS, RADIUS, HALF_HEIGHT)
                    sweep = [edge[i] - size[i] for i in range(3)] + [edge[i + 3] + size[i] for i in range(3)]
                    self.assertFalse([shape for shape in solids + visuals if intersects(sweep, shape)])
                work_area = (*[coord - .97 for coord in entry[:2]], .04,
                             *[coord + .97 for coord in entry[:2]], 6.05)
                self.assertFalse([shape for shape in solids + visuals if intersects(work_area, shape)])
                self.assertTrue(network.allows(entry, foot, [zone]))
                self.assertFalse(network.allows(entry, foot, ["D"]))
