from types import SimpleNamespace

from rackonaut_safety.manager import Manager


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
