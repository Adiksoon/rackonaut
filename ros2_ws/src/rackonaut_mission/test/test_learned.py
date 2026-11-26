import json
from pathlib import Path
from unittest import TestCase

from ament_index_python.packages import get_package_share_path
from rackonaut_energy.aerial import Network
from rackonaut_energy.model import Model
from rackonaut_mission.learned import forecast, observed_prefix, ordered_targets, straight_continuation


ROOT = Path(__file__).resolve().parents[4]
ARCHIVE = next((ROOT / "docs/route-teaching-evidence/mapping").glob("CAL-*"))


class LearnedRouteExecutionTests(TestCase):
    def test_selection_keeps_recorded_direction_and_all_approved_edges(self):
        graph = json.loads((ARCHIVE / "route.json").read_text())
        profile = get_package_share_path("rackonaut_warehouse") / "config/aerial_layout.json"
        network = Network(json.loads(profile.read_text()))
        first, last = (row["record_id"] for row in graph["locations"])
        one, zones = ordered_targets(graph, {last}, network)
        both, _ = ordered_targets(graph, {first, last}, network)
        self.assertEqual([node[0] for node in one], [node["to"] for node in graph["edges"]])
        self.assertEqual([node[1] for node in one], [node[1] for node in both])
        self.assertEqual([node[2] for node in one if node[2]], ["A-01-03"])
        self.assertEqual([node[2] for node in both if node[2]], ["A-01-01", "A-01-03"])
        self.assertEqual(set(zones), {"D", "A"})
        self.assertEqual([gate for *_, gate in one if gate], ["A"])
        edge = graph["edges"][16]
        edge["from"], edge["to"] = edge["to"], edge["from"]
        with self.assertRaisesRegex(ValueError, "unapproved directed segment"):
            ordered_targets(graph, {first, last}, network)

    def test_budget_includes_the_directed_return_once_and_preserves_reserve(self):
        model = Model()
        pad = (0., 0., 0., 0.)
        stop = (1., 0., 0., 0.)
        total = forecast(model, pad, [stop, pad], 1, return_from=0)
        manual_return = forecast(model, stop, [pad], 0)
        self.assertAlmostEqual(total["return_percent"], manual_return["percent"])
        self.assertAlmostEqual(total["required_percent"], total["percent"] + model.reserve)
        self.assertGreater(total["percent"], total["return_percent"])

    def test_lookahead_continues_through_straight_vertex_and_stops_at_turn(self):
        pose, target = (0., 0., 0., 0.), (.40, 0., 0., 0.)
        self.assertTrue(straight_continuation(pose, target, (.90, 0., 0., 0.)))
        self.assertFalse(straight_continuation(pose, target, (.40, .30, 0., 0.)))
        self.assertFalse(straight_continuation(pose, target, (.20, 0., 0., 0.)))

    def test_visibility_stop_remains_in_the_known_section_of_the_same_leg(self):
        pose, end = (0., 0., 1., 0.), (.4, 0., 1., .02)
        first, *unchanged = observed_prefix(pose, end, .244)
        self.assertAlmostEqual(first, .122)
        self.assertEqual(unchanged, [0., 1., .02])
        self.assertIsNone(observed_prefix(pose, end, .12))
        self.assertIsNone(observed_prefix(pose, end, None))
