from pathlib import Path
from types import SimpleNamespace
import runpy
from unittest.mock import Mock

import numpy as np
import pytest
from sensor_msgs.msg import PointCloud2

from rackonaut_avoidance import sensor
from rackonaut_mission.node import Mission

module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/run_mission"))
X3Scanner, X3Mission = module["X3Scanner"], module["X3Mission"]


@pytest.fixture
def scanner(monkeypatch):
    monkeypatch.setattr(sensor, "unpack",
                        lambda message: (np.ones((1, 1)), np.zeros((0, 3)), np.zeros((0, 3))))
    return X3Scanner(Mock(), exact_pose=True)


def scan(second):
    message = PointCloud2()
    message.header.stamp.sec = second
    return message


def pose(second):
    return second, np.zeros(3), np.eye(3)


def test_delayed_exact_pose_can_match_even_after_a_newer_scan(scanner, monkeypatch):
    monkeypatch.setattr(sensor, "monotonic", lambda: 100.)
    scanner.receive(scan(1))
    scanner.poses.append(pose(0))
    assert scanner.current(100.15) is None

    monkeypatch.setattr(sensor, "monotonic", lambda: 100.20)
    scanner.receive(scan(2))
    scanner.poses.append(pose(1))
    cloud = scanner.current(100.21)
    assert cloud.time == 1.
    assert cloud.received == 100.
    assert scanner.current(100.22) is cloud

    scanner.poses.append(pose(2))
    assert scanner.current(100.30).time == 2.


def test_exact_pose_cannot_revive_stale_scan(scanner, monkeypatch):
    monkeypatch.setattr(sensor, "monotonic", lambda: 100.)
    scanner.receive(scan(1))
    scanner.poses.append(pose(1))
    assert scanner.current(100. + sensor.STALE_SECONDS + .01) is None


def test_resume_to_distant_upper_viewpoint_stays_inside_reserved_corridor():
    import json

    from ament_index_python.packages import get_package_share_path
    from rackonaut_energy.aerial import Network
    from rackonaut_mission.route import Target

    config = get_package_share_path("rackonaut_warehouse") / "config"
    profile = json.loads((config / "aerial_layout.json").read_text())
    node = X3Mission.__new__(X3Mission)
    node.aerial = Network(profile)
    node.route = SimpleNamespace(zones=("D", "A", "B"))

    target = Target(13.86, .45, 2.89, 1.57, "A-01-08")
    legs = node.outbound(target)
    assert legs[-3].pose == node.aerial.nodes["foot_A"]
    assert legs[-2].pose == (*legs[-3].pose[:2], target.z, legs[-3].pose[3])
    assert legs[-2].phase == "AISLE_APPROACH"
    assert node.aerial.allows(legs[-3].pose, legs[-2].pose, node.route.zones)
    assert node.aerial.allows(legs[-2].pose, legs[-1].pose, node.route.zones)

    low = Target(8.26, -5.55, .79, 1.57, "B-02-01")
    assert node.outbound(low) == node.aerial.sortie(node.coordinates(low), "B")


@pytest.mark.parametrize("stage,height,scale,expected", [
    ("DOCKING", .70, 1., .40), ("LAND", .45, .25, .25), ("DOCKING", .30, 0., 0.),
    ("DOCKING", 1., 1., 1.), ("RESUMING", .40, 1., 1.),
])
def test_speed_limit_applies_only_on_final_approach(monkeypatch, stage, height, scale, expected):
    sent = Mock()
    monkeypatch.setattr(Mission, "send_velocity", sent)
    node = X3Mission.__new__(X3Mission)
    node.stage = stage
    node.pose = SimpleNamespace(z=height)
    node.route = SimpleNamespace(pad=SimpleNamespace(z=.06))
    node.send_velocity(scale=scale)
    sent.assert_called_once_with(None, expected)
