import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from rackonaut_safety.manager import CALIBRATION_INTERRUPTED, Manager


def test_calibration_holds_reservation_until_physical_dock():
    releases = []
    safety = SimpleNamespace(
        supervise_charging=lambda *_: False,
        phase="RESERVED", mission={"stage": CALIBRATION_INTERRUPTED, "landed": True, "motion_owned": False},
        mission_at=10., calibration_terminal_at=None, energy_at=10., at_pad=lambda _: True,
        energy={"fresh": True, "contact": True, "contact_source": "gazebo_dock_switch", "switch_engaged": False},
        release=releases.append,
    )
    Manager.supervise(safety, 10.)
    assert not releases
    safety.energy["switch_engaged"] = True
    Manager.supervise(safety, 10.1)
    assert len(releases) == 1


def ready():
    events = []
    manager = SimpleNamespace(
        phase="RECOVERY", mission_at=10., required=["D", "A"], clear_since={"A": 4., "D": 4.},
        light_state={"A": "RESERVED", "D": "RESERVED"}, run="INS-CONTROL-1",
        mission={"stage": "ABORTED", "recovery": {
            "inspection_id": "INS-CONTROL-1", "recovery_id": "REC-123456789ABC",
            "required_zones": ["A", "D"], "phase": "RECOVERY_AUTHORIZED", "permit_request": True
        }},
        recovery_id=None, recovery_revocation=None,
        energy={"fresh": True, "contact_source": "gazebo_dock_switch", "contact": True, "switch_engaged": True},
        energy_at=10., at_pad=lambda _: True, blockers=lambda _: ("", [], ""),
        event=lambda kind, *_args, **_kw: events.append(kind),
        release=lambda _msg: events.append("released"),
    )
    return manager, events


def permit(manager, now=10., person=()):
    return Manager.recovery_permit(manager, now, {"A": "FRESH", "D": "FRESH"}, person, True)["permit"]


def test_scoped_approval_then_revocation_cannot_rearm_same_recovery():
    safety, events = ready()
    proposal = safety.mission["recovery"]
    assert permit(safety) is None
    proposal["authorized_at"] = "2026-11-25T12:00:00Z"
    proposal["required_zones"] = ["D"]
    assert permit(safety) is None
    proposal["required_zones"] = ["A", "D"]
    assert permit(safety, person=["A"]) is None
    assert permit(safety) == proposal["recovery_id"]
    assert permit(safety, person=["A"]) is None
    assert permit(safety) is None
    assert events == ["recovery_permitted", "recovery_revoked"]


def test_release_requires_completion_of_permitted_recovery_and_live_dock_switch():
    safety, events = ready()
    proposal = safety.mission["recovery"]
    proposal["authorized_at"] = "2026-11-25T12:00:00Z"
    assert permit(safety) == proposal["recovery_id"]
    proposal["phase"] = "RECOVERY_COMPLETE"
    safety.energy["switch_engaged"] = False
    assert permit(safety) is None
    assert events == ["recovery_permitted"]
    safety.energy["switch_engaged"] = True
    permit(safety)
    assert events == ["recovery_permitted", "released"]


def charging_manager():
    safety = Mock(
        recovery_enabled=True, charging_pause=False, phase="RESERVED", airborne=True,
        permit_issued=True, required=["D", "A"], run="INS-CONTROL-1",
        mission={"stage": "CHARGING", "landed": True, "motion_owned": False,
                 "energy": {"departures": 1}},
        mission_at=10., energy_at=10., odom_at=10., light_at=10., reserved_at=8.,
        prepared_at=6., alarm=None, message="Reserved", clear_since={"A": 9., "D": 9.}, events=[],
        fields={"D": [], "A": []}, laser=None, aerial=None, energy_permits={1},
        light_state={"D": "RESERVED", "A": "RESERVED"}, sensor_mode="virtual",
        energy={"fresh": True, "contact": True, "contact_source": "gazebo_dock_switch",
                "switch_engaged": True},
    )
    safety.at_pad.return_value = True
    safety.sensor_health.return_value = "FRESH"
    safety.occupied.return_value = []
    safety.blockers.side_effect = lambda now: Manager.blockers(safety, now)
    safety.release.side_effect = lambda message: Manager.release(safety, message)
    safety.supervise_charging.side_effect = lambda stage, now: Manager.supervise_charging(safety, stage, now)
    safety.supervise.side_effect = lambda now: Manager.supervise(safety, now)
    safety.visual_state.side_effect = lambda *args: Manager.visual_state(safety, *args)
    safety.recovery_permit.return_value = None
    return safety


def charging_tick(safety, now):
    safety.mission_at = safety.energy_at = safety.odom_at = safety.light_at = now
    with patch("rackonaut_safety.manager.monotonic", return_value=now):
        Manager.tick(safety)
    return json.loads(safety.state.publish.call_args.args[0].data)


def test_charging_opens_zones_at_verified_dock_and_requires_fresh_clearance_to_resume():
    safety = charging_manager()
    safety.energy["switch_engaged"] = False
    assert charging_tick(safety, 10.)["phase"] == "RESERVED"
    safety.energy["switch_engaged"] = True
    state = charging_tick(safety, 10.1)
    assert state["phase"] == "RELEASED"
    assert state["required"] == []
    assert state["zones"]["A"]["state"] == "OPEN"
    assert not state["permit"]

    safety.mission["stage"] = "READY_TO_RESUME"
    safety.occupied.return_value = ["A"]
    state = charging_tick(safety, 30.)
    assert state["phase"] == "RELEASED"
    assert not state["permit"]

    safety.occupied.return_value = []
    safety.light_state = {"D": "OPEN", "A": "OPEN"}
    assert charging_tick(safety, 31.)["phase"] == "PREPARING"
    assert not charging_tick(safety, 33.9)["permit"]
    assert charging_tick(safety, 34.)["phase"] == "RESERVED"
    assert not charging_tick(safety, 34.2)["permit"]
    safety.light_state = {"D": "RESERVED", "A": "RESERVED"}
    state = charging_tick(safety, 34.3)
    assert state["permit_departure"] == 2

    safety.mission.update(stage="RESUMING", landed=False, motion_owned=True)
    state = charging_tick(safety, 34.4)
    assert state["phase"] == "RESERVED"
    assert not safety.charging_pause


def test_charging_loses_verified_contact_and_requests_recovery():
    safety = charging_manager()
    assert charging_tick(safety, 10.)["phase"] == "RELEASED"
    safety.energy["contact"] = False
    charging_tick(safety, 10.1)
    safety.recover.assert_called_once()
    assert not safety.charging_pause


def test_loss_of_dock_contact_revokes_permission_while_waiting_for_departure():
    safety = charging_manager()
    safety.charging_pause = True
    safety.mission["stage"] = "READY_TO_RESUME"
    assert charging_tick(safety, 10.)["permit_departure"] == 2

    def recover(*_args):
        safety.phase = "RECOVERY"
        safety.alarm = {"zones": ["D"], "event": "touchdown_unknown"}

    safety.recover.side_effect = recover
    safety.energy["switch_engaged"] = False
    state = charging_tick(safety, 10.1)
    assert state["phase"] == "RECOVERY"
    assert not state["permit"]
