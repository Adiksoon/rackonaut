import json
from pathlib import Path
import runpy

from ament_index_python.packages import get_package_share_path
import pytest

from rackonaut_control.planning import plan
from rackonaut_mission.route import load_route

plan_x3 = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/serve_x3"))["plan_x3"]


@pytest.fixture
def layout():
    config = get_package_share_path("rackonaut_warehouse") / "config"
    layout = json.loads((config / "control_layout.json").read_text())
    layout["aerial"] = aerial = json.loads((config / "aerial_layout.json").read_text())
    layout["pad"] = aerial["pad"]
    layout["takeoff_z"] = aerial["nodes"]["shaft"][2]
    layout["safety_fields"] = json.loads((config / "safety_fields.json").read_text())
    layout["adaptive_world"] = True
    return layout


@pytest.mark.parametrize("adaptive", [False, True])
def test_descents_use_separate_segments_and_preserve_reserved_areas(layout, tmp_path, adaptive):
    selection = {"mode": "full", "quality": True, "adaptive": adaptive}
    baseline = plan(layout, selection)
    planned = plan_x3(layout, selection)
    route = planned["route"]
    waypoints = route["waypoints"]

    assert planned["slots"] == baseline["slots"]
    assert planned["required_zones"] == baseline["required_zones"]
    for previous_slot, target_slot in (
        ("A-01-02", "A-01-03"), ("A-01-04", "A-01-05"),
        ("A-01-06", "A-01-07"), ("B-01-02", "B-02-01"),
    ):
        index = next(i for i, row in enumerate(waypoints) if row.get("slot_id") == target_slot)
        previous, descent, target = waypoints[index - 2:index + 1]
        assert previous["slot_id"] == previous_slot
        assert descent == {
            "x": previous["x"], "y": previous["y"], "z": target["z"],
            "yaw_deg": previous["yaw_deg"], "phase": "AISLE_APPROACH",
        }

    if adaptive:
        assert route["retries"] == baseline["route"]["retries"]
        assert all(point in planned["safety_points"] for point in baseline["safety_points"])
    route_file = tmp_path / "route.json"
    route_file.write_text(json.dumps({
        **route, "energy_crossing_x": layout["crossing_x"], "energy_zones": planned["required_zones"],
    }))
    assert len(load_route(route_file).stops) == 11


def test_plain_layout_keeps_the_standard_route(layout):
    del layout["aerial"]
    selection = {"mode": "custom", "slots": ["A-01-02", "A-01-03"]}
    assert plan_x3(layout, selection) == plan(layout, selection)
