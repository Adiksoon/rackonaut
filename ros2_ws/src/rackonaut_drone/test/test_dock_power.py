import json
from pathlib import Path
import runpy
from unittest.mock import Mock

from geometry_msgs.msg import Twist
from ros_gz_interfaces.msg import Contact, Contacts
from std_msgs.msg import String

DockPower = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/velocity_guard"))["DockPower"]


def dock_contact(second, touching=True):
    message = Contacts()
    message.header.stamp.sec = second
    if touching:
        contact = Contact()
        contact.collision1.name = "rackonaut_dock::body::dock_contact_surface_collision"
        contact.collision2.name = "rackonaut_reference_drone::base_link::body_collision"
        message.contacts.append(contact)
    return message


def mission(phase, landed):
    return String(data=json.dumps({"stage": phase, "landed": landed}))


def test_disarm_requires_fresh_confirmed_charging_contact(monkeypatch):
    monkeypatch.setitem(DockPower.allow.__globals__, "monotonic", lambda: 100.)
    node = Mock()
    power = DockPower(node)
    power.on_contact(dock_contact(1))
    power.on_mission(mission("DOCKING", False))
    assert power.allow(Twist(), 100.1)
    power.on_mission(mission("CHARGING", True))
    power.on_contact(dock_contact(2, False))
    assert power.allow(Twist(), 100.1)
    power.on_contact(dock_contact(1))  # A replay cannot restore the contact.
    assert power.allow(Twist(), 100.1)
    power.on_contact(dock_contact(3))
    assert power.allow(Twist(), 100.41)
    assert not power.allow(Twist(), 100.1)
    assert not node.create_publisher.return_value.publish.call_args.args[0].data


def test_docked_motors_require_a_fresh_authorized_climb(monkeypatch):
    monkeypatch.setitem(DockPower.allow.__globals__, "monotonic", lambda: 100.)
    node = Mock()
    power = DockPower(node)
    power.on_contact(dock_contact(1))
    power.on_mission(mission("CHARGING", True))
    assert not power.allow(Twist(), 100.1)

    lift = Twist()
    lift.linear.z = .25
    power.on_mission(mission("READY_TO_RESUME", True))
    assert not power.allow(lift, 100.1)
    power.on_mission(mission("ABORTED", False))
    assert not power.allow(lift, 100.1)
    power.on_mission(mission("RESUMING", False))
    assert not power.allow(lift, 100.5)
    assert not power.allow(Twist(), 100.1)
    assert power.allow(lift, 100.1)
    assert node.create_publisher.return_value.publish.call_args.args[0].data
