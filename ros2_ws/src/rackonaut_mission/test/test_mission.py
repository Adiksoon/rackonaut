import json
from datetime import datetime, timezone
from math import hypot, pi, radians
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, call, patch

from rackonaut_mission.adaptive import next_issue
from rackonaut_mission.confirmation import current_observation
from rackonaut_mission.manual import ManualFlight
from rackonaut_mission.node import Mission
from rackonaut_mission.route import Target, heading_error, load_route, velocity


class MissionTests(TestCase):
    def sensor_guard_mission(self, *, localization_ready=True, cloud_ready=True):
        cloud = SimpleNamespace(received=99.9)
        mission = Mock(
            stage="VERTICAL_TAKEOFF", energy_enabled=True, safety_at=100., safety_phase="RESERVED",
            safety_zones={"D", "A"}, route=SimpleNamespace(zones=["D", "A"]),
            scanner=Mock(cloud=cloud), navigation=Mock(), sensor_localization=True,
            localization={"state": "TRACKING", "reason": "Synchronized LiDAR fit"},
            localization_at=100., odom_at=100., sensor_hold_at=None,
            sensor_ready_at=None, sensor_hold_reason="", settled_since=99.,
            recovery=Mock(), calibration_id=None, manual=None, learned=None,
            command=Mock(), battery={"percent": 90.}, energy_model=SimpleNamespace(reserve=8.),
        )
        mission.scanner.current.return_value = cloud if cloud_ready else None
        mission.localization_ready.return_value = localization_ready
        mission.energy_fresh.return_value = True
        mission.next_inspection_index.return_value = None
        mission.autonomous_sensor_hold.side_effect = lambda now: Mission.autonomous_sensor_hold(mission, now)
        return mission

    def test_transient_sensor_gap_stops_motion_and_waits_for_fresh_aligned_cloud(self):
        for localization_ready, cloud_ready in ((False, True), (True, False)):
            with self.subTest(localization=localization_ready, lidar=cloud_ready):
                mission = self.sensor_guard_mission(
                    localization_ready=localization_ready, cloud_ready=cloud_ready)
                self.assertTrue(Mission.energy_guard(mission, 100.))
                mission.send_velocity.assert_called_once_with(scale=0.)
                self.assertIsNone(mission.settled_since)

                mission.localization_ready.return_value = True
                mission.scanner.current.return_value = mission.scanner.cloud
                self.assertTrue(Mission.energy_guard(mission, 100.1))
                self.assertIsNone(mission.sensor_ready_at)

                mission.scanner.cloud.received = 100.2
                self.assertTrue(Mission.energy_guard(mission, 100.2))
                self.assertTrue(Mission.energy_guard(mission, 100.4))
                self.assertFalse(Mission.energy_guard(mission, 100.5))
                self.assertIsNone(mission.sensor_hold_at)
                mission.finish.assert_not_called()

    def test_persistent_sensor_gap_aborts_with_diagnostics(self):
        mission = self.sensor_guard_mission(cloud_ready=False)
        self.assertTrue(Mission.energy_guard(mission, 100.))
        mission.odom_at = mission.localization_at = mission.safety_at = 101.25
        self.assertTrue(Mission.energy_guard(mission, 101.25))
        result, detail, _ = mission.finish.call_args.args
        self.assertEqual(result, "ABORTED")
        self.assertIn("Onboard lidar stopped advancing", detail)
        self.assertIn("aligned lidar age=1.350s", detail)

    def test_reservation_loss_still_aborts_during_sensor_hold(self):
        mission = self.sensor_guard_mission(cloud_ready=False)
        self.assertTrue(Mission.energy_guard(mission, 100.))
        mission.safety_phase = "RECOVERY"
        self.assertTrue(Mission.energy_guard(mission, 100.1))
        mission.finish.assert_called_once_with(
            "ABORTED", "Safety clearance lost; automatic restart disabled", 100.1)
        mission.send_velocity.assert_called_once_with(scale=0.)

    def test_docked_charging_continues_when_safety_opens_the_zones(self):
        mission = Mock(stage="CHARGING", command=None, landed=True, energy_enabled=True,
                       recovery=Mock(), safety_phase="RELEASED")
        mission.physical_dock.return_value = True
        self.assertTrue(Mission.energy_guard(mission, 100.))
        mission.dock_tick.assert_called_once_with(100.)
        mission.finish.assert_not_called()

        mission.physical_dock.return_value = False
        self.assertTrue(Mission.energy_guard(mission, 100.1))
        mission.finish.assert_called_once_with(
            "ABORTED", "Dock contact or Safety clearance lost during charging", 100.1)

    def test_x3_caps_translation_near_the_dock_and_still_sends_zero(self):
        command = Mock()
        target = Target(1., 1., .1, 0.)
        mission = SimpleNamespace(
            x3=True, stage="DOCKING", target=target, command=command,
            route=SimpleNamespace(pad=Target(0., 0., .1, 0.)),
            pose=Target(0., 0., .8, 0.),
        )
        with patch("rackonaut_mission.node.velocity", return_value=(.3, -.2, -.25, .2)):
            Mission.send_velocity(mission)
            slow = command.publish.call_args.args[0]
            Mission.send_velocity(mission, scale=0.)
            stopped = command.publish.call_args.args[0]
            mission.stage = "RESUMING"
            Mission.send_velocity(mission)
            normal = command.publish.call_args.args[0]
        for actual, expected in zip(
            (slow.linear.x, slow.linear.y, slow.linear.z, slow.angular.z), (.12, -.08, -.10, .2),
        ):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual((stopped.linear.x, stopped.linear.y, stopped.linear.z, stopped.angular.z),
                         (0., 0., 0., 0.))
        self.assertEqual((normal.linear.x, normal.linear.y, normal.linear.z), (.3, -.2, -.25))

    def test_x3_resume_waits_for_fresh_safety_clearance_and_ready_charge(self):
        pad = Target(0., 0., .1, 0.)
        mission = Mock(
            calibration_id=None, energy_enabled=True, stage="READY_TO_RESUME",
            safety_interlock=True, safety_permit=True, safety_at=99., safety_zones={"D", "A"},
            permit_departure=2, departures=1, pose=pad, odom_at=100., speed=0.,
            route=SimpleNamespace(zones=["D", "A"], pad=pad, takeoff=Target(0., 0., 2., 0.)),
            battery={"percent": 70., "contact": True, "dock": "CHARGING", "sim_time": 101.},
            learned=None, manual=None, aerial=None, sensor_localization=False, scanner=None,
            command_topic="/drone/cmd_vel", started=98., completed=["A-01-01"], sorties=[],
        )
        mission.readiness = lambda now: Mission.readiness(mission, now)
        mission.required_departure.return_value = 50.
        mission.count_publishers.return_value = 0
        mission.count_subscribers.return_value = 1

        self.assertIn("safety interlock", Mission.start(mission, 100.))
        mission.safety_at = 100.
        self.assertIn("charge readiness", Mission.start(mission, 100.))
        mission.set_flight_enabled.assert_not_called()
        mission.create_publisher.assert_not_called()

        mission.battery["dock"] = "READY"
        self.assertEqual(Mission.start(mission, 100.), "")
        mission.set_flight_enabled.assert_called_once_with(True)
        self.assertEqual(mission.transition.call_args.args[0], "RESUMING")
        self.assertEqual(mission.sorties[-1]["completed_before"], ["A-01-01"])

    def test_x3_cuts_power_only_after_confirmed_docking(self):
        for model, contact in ((True, False), (False, True), (True, True)):
            mission = Mock(stage="DOCKING", manual=None, calibration_id=None,
                           battery={"contact": contact, "percent": 17.},
                           x3=model, obstacle_retreat=False, resume_index=2)
            Mission.advance_energy_motion(mission, 100.)
            calls = []
            if contact:
                calls.append(call.stop_motion())
                if model:
                    calls.append(call.set_flight_enabled(False))
                calls.extend((call.close_sortie("DOCKED_FOR_CHARGE"),
                              call.transition("CHARGING", mission.route.pad, 100.,
                                              "Docking confirmed — charging")))
            self.assertEqual(mission.method_calls, calls)

    def test_manual_rejects_expired_reordered_and_cross_mission_requests(self):
        flight = ManualFlight(SimpleNamespace(inspection_id="INS-CURRENT"))
        request = {"inspection_id": "INS-CURRENT", "sequence": 5, "sent": 12.8,
                   "action": "movement", "axes": [1, 0, 0, 0], "speed": .5}
        with patch("rackonaut_mission.manual.monotonic", return_value=13.):
            for stale in (dict(request, sent=12.4), dict(request, inspection_id="INS-OTHER"),
                          dict(request, axes=[1, 0, True, 0])):
                flight.receive(SimpleNamespace(data=json.dumps(stale)))
                self.assertEqual(flight.sequence, -1)
            flight.receive(SimpleNamespace(data=json.dumps(request)))
            self.assertEqual(flight.requested, (.2, 0., 0., 0.))
            for replay in (request, dict(request, sequence=4)):
                flight.receive(SimpleNamespace(data=json.dumps(dict(replay, action="return"))))
                self.assertFalse(flight.return_requested)
            flight.receive(SimpleNamespace(data=json.dumps(dict(request, action="return", sequence=6))))
            self.assertTrue(flight.return_requested)
            flight.receive(SimpleNamespace(data=json.dumps(dict(request, sequence=7))))
            self.assertEqual(flight.requested, (0., 0., 0., 0.))

    def test_manual_distinguishes_safety_from_emergency_stop(self):
        mission = SimpleNamespace(stage="ABORTED", detail="Stopped by the operator", safety_alarm=None)
        flight = ManualFlight(mission)
        self.assertEqual(flight.snapshot()["state"], "EMERGENCY_STOP")
        mission.safety_alarm = {"event": "mission_aborted"}
        self.assertEqual(flight.snapshot()["state"], "EMERGENCY_STOP")
        mission.safety_alarm = {"event": "intrusion", "message": "Zone occupied: Aisle A."}
        self.assertEqual(flight.snapshot()["state"], "SAFETY")
        self.assertIn("Aisle A", flight.snapshot()["detail"])

    def test_calibration_energy_status_has_no_resume_leg(self):
        motion = SimpleNamespace(stage="RETURN_TO_DOCK", calibration_id="CAL-TEST", resume_index=None)
        self.assertEqual(Mission.aerial_remaining_cost(motion, ["A-01-03"], 11.7), 11.7)

    def test_adaptive_request_depends_on_observation_and_linked_photo(self):
        readable = {"occupancy": "occupied", "label_status": "readable", "pallet_id": "P999"}
        damaged = {"status": "DAMAGED"}
        self.assertEqual(next_issue(None, None, False), "missing")
        self.assertEqual(next_issue(dict(readable, occupancy="uncertain"), damaged, False), "uncertain")
        self.assertEqual(next_issue(dict(readable, label_status="unreadable"), damaged, False), "unreadable")
        self.assertEqual(next_issue(readable, damaged, False), "damage")
        self.assertIsNone(next_issue(readable, damaged, True))
        self.assertIsNone(next_issue(readable, None, False))

    def test_world_error_rotates_into_body_frame(self):
        pose = Target(0, 0, .79, pi / 2)
        forward, left, up, yaw = velocity(Target(5, 0, 3, pi / 2), pose)
        self.assertAlmostEqual(forward, 0.)
        self.assertAlmostEqual(left, -.56)
        self.assertAlmostEqual(hypot(forward, left), .56)
        self.assertAlmostEqual(up, .50)
        self.assertAlmostEqual(yaw, 0.)
        self.assertAlmostEqual(heading_error(radians(-179), radians(179)), radians(2))

    def test_default_route_has_five_distinct_stops(self):
        route = load_route(Path(__file__).resolve().parents[1] / "config/showcase.json")
        self.assertGreater(route.takeoff.z, route.pad.z)
        self.assertEqual([stop.slot_id for stop in route.stops], [f"A-01-0{n}" for n in range(1, 6)])
        self.assertTrue(all(stop.yaw == pi / 2 for stop in route.stops))

    def test_confirmation_excludes_wrong_stale_seen_and_future_observations(self):
        since = datetime(2026, 11, 25, 8, 0, 30, tzinfo=timezone.utc)
        now = datetime(2026, 11, 25, 8, 0, 35, tzinfo=timezone.utc)
        current = {
            "inspection_id": "INS-CURRENT",
            "slot_id": "A-01-03",
            "observation_id": "OBS-A",
            "timestamp": "2026-11-25T08:00:33.123Z",
            "occupancy": "occupied",
            "pallet_id": "P999",
        }
        rejected = [
            dict(current, observation_id="OBS-STALE", timestamp="2026-11-25T08:00:29.999Z"),
            dict(current, observation_id="OBS-FUTURE", timestamp="2026-11-25T08:05:00Z"),
            dict(current, observation_id="OBS-OTHER", slot_id="A-01-04"),
            dict(current, observation_id="OBS-PRIOR", inspection_id="INS-PRIOR"),
            dict(current, observation_id="OBS-SEEN"),
        ]
        args = ("INS-CURRENT", "A-01-03", since, {"OBS-SEEN"}, now)
        self.assertIsNone(current_observation(rejected, *args))
        self.assertEqual(current_observation([*rejected, current], *args), current)
