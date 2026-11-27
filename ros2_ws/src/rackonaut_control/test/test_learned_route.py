from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from rackonaut_control.learned_route import raw_knots, stale_dock_preflight, with_inspections
from rackonaut_control.route_recording import RouteRecorder
from rackonaut_control.route_review import RouteReview
from rackonaut_control.teaching import FRAME, Pose, Teaching
from rackonaut_energy.model import Model


SESSION = "CAL-" + "A" * 32
QUATERNION = [0., 0., 0., 1.]
PROFILE = {
    "nodes": {"dock": [0., 0., 0.], "shaft": [0., 0., 1.], "entry_A": [1., 0., 1.]},
    "gates": {},
    "inspection_volumes": {"A": [.7, -.5, .7, 1.5, .5, 1.4]},
    "edges": [["dock", "shaft", "shaft"], ["shaft", "entry_A", "tunnel"]],
}


def observation(index, x, z, stage, contact=False):
    return {"stamp": {"sec": 0, "nanosec": index * 100_000_000},
            "position_m": [x, 0., z], "orientation_xyzw": QUATERNION,
            "stage": stage, "flight_phase": stage, "dock_contact": contact,
            "localization": {"state": "TRACKING"},
            "safety": {"phase": "RESERVED", "verified": True, "zones": ["D", "A"]},
            "collision": {"state": "CLEAR", "scan_age_ms": 70., "verified_distance_m": 0., "direction": []}}


def location(index):
    return {"camera_stamp": {"sec": 0, "nanosec": index * 100_000_000},
            "record_id": "LOC-A", "storage_location_id": "A-01-01",
            "position_m": [1., 0., 1.], "orientation_xyzw": QUATERNION}


class LearnedRouteTests(TestCase):
    def test_full_route_uses_two_directed_journals_without_joining_the_docks(self):
        with TemporaryDirectory() as scratch:
            teaching = Teaching(Path(scratch), None)
            teaching.create(SESSION)
            review = RouteReview(teaching, PROFILE)
            review.write(SESSION, "result.json", {"mapping_id": SESSION, "frame": FRAME, "multi_sortie": True})
            (teaching.root / SESSION / "map.ply").write_bytes(b"ply\n")
            states = [(0., 0., "WAITING"), (0., 1., "VERTICAL_TAKEOFF"),
                      (.8, 1., "MANUAL_FLIGHT"), (1., 1., "MANUAL_FLIGHT"), (1., 1., "MANUAL_FLIGHT"),
                      (1., 1., "RETURN_TO_DOCK"), (0., 1., "RETURN_TO_DOCK"), (0., 0., "COMPLETE")]
            manifest, index = teaching.manifest(SESSION), []
            for number, base in [(1, 0), (2, 60)]:
                record_id = f"LOC-{number}"
                manifest["locations"].append({
                    **location(base + 4), "record_id": record_id, "storage_location_id": f"A-01-0{number}",
                    "camera_stamp": {"sec": base // 10, "nanosec": 400_000_000},
                })
                run = f"INS-{number}"
                recorder = RouteRecorder(teaching.root, SESSION, run, vars(Model()),
                                         {"contact": True, "contact_source": "gazebo_dock_switch"}, number)
                try:
                    if number == 2:
                        preflight = observation(0, 0., 0., "STARTING", True)
                        preflight["localization"] = {"state": "STALE", "source": "slam"}
                        recorder.add(Pose((base-1)*100_000_000, 0., (0., 0., 0.), tuple(QUATERNION),
                                          0., 0., (.01, .01, .01)), preflight, force=True)
                    for offset, (x, z, stage) in enumerate(states):
                        ros_index = base + offset
                        sample = observation(0, x, z, stage, offset in (0, len(states) - 1))
                        sample["localization"]["source"] = "slam"
                        pose = Pose(ros_index * 100_000_000, 0., (x, 0., z), tuple(QUATERNION),
                                    0., 0., (.01, .01, .01))
                        recorder.add(pose, sample, force=True)
                finally:
                    recorder.finish("COMPLETE", True, {"dock_contact_source": "gazebo_dock_switch"})
                    self.assertTrue(recorder.done.wait(2.))
                index.append(dict(number=number, trajectory=f"trajectory-{number:02d}.jsonl",
                                  samples=recorder.count, status="DOCKED", inspection_id=run))
            manifest["revision"] = 2
            teaching.write_manifest(SESSION, manifest)
            review.write(SESSION, "sorties.json", index)
            proposal = review.action("review", SESSION, {})
            route = proposal["route"]
            self.assertEqual([leg["locations"][0]["record_id"] for leg in route["sorties"]], ["LOC-1", "LOC-2"])
            self.assertEqual(route["sorties"][1]["nodes"][0]["raw_bracket"], [1, 1])
            self.assertTrue(all(edge["from"][:3] == edge["to"][:3] for edge in route["edges"]))
            request = {"route_sha256": proposal["route_sha256"], "confirm": True}
            self.assertEqual(review.action("validate", SESSION, request)["status"], "validated")
            self.assertEqual(review.action("approve", SESSION, request)["status"], "approved")
            planned = review.action("plan", SESSION, {**request, "record_ids": ["LOC-1", "LOC-2"]})
            self.assertEqual(len(planned["sorties"]), 2)
            self.assertLess(planned["forecast"]["required_percent"], 100.)
            review.write(SESSION, "sorties.json", index[:1])
            self.assertEqual(review.state(SESSION)["status"], "stale")

    def test_stale_preflight_cannot_hide_loss_or_motion(self):
        dock = PROFILE["nodes"]["dock"]
        first = {**observation(0, 0., 0., "STARTING", True), "speed_mps": 0.}
        next_sample = {**observation(1, 0., 0., "WAITING", True), "speed_mps": 0.}
        first["localization"] = {"state": "STALE", "source": "slam"}
        next_sample["localization"]["source"] = "slam"
        self.assertTrue(stale_dock_preflight(first, next_sample, dock))
        self.assertFalse(stale_dock_preflight({**first, "dock_contact": False}, next_sample, dock))
        self.assertFalse(stale_dock_preflight({**first, "speed_mps": .15}, next_sample, dock))
        first["localization"]["state"] = "LOST"
        self.assertFalse(stale_dock_preflight(first, next_sample, dock))

    def test_camera_time_distinguishes_repeated_visits_to_same_pose(self):
        rows = [observation(i, x, 1., "MANUAL_FLIGHT") for i, x in enumerate([1., 1., .9, 1., 1.])]
        bound = [point for point in with_inspections(raw_knots(rows), [location(4)]) if point.locations]
        self.assertEqual(len(bound), 1)
        self.assertEqual(bound[0].raw, (3, 4))
        self.assertEqual(bound[0].time, 400_000_000)

    def test_archived_route_requires_complete_journal_and_current_locations(self):
        with TemporaryDirectory() as scratch:
            teaching = Teaching(Path(scratch), None)
            teaching.create(SESSION)
            folder = teaching.root / SESSION
            folder.joinpath("map.ply").write_text("ply\n")
            review = RouteReview(teaching, PROFILE)
            review.write(SESSION, "result.json", {"mapping_id": SESSION, "frame": FRAME})
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                review.action("approve", SESSION, {"confirm": True})
            manifest = teaching.manifest(SESSION)
            manifest.update(revision=1, locations=[location(5)])
            teaching.write_manifest(SESSION, manifest)
            states = [
                (0., 0., "WAITING"), (0., 1., "VERTICAL_TAKEOFF"),
                (.5, 1., "MANUAL_FLIGHT"), (.9, 1., "MANUAL_FLIGHT"),
                (1., 1., "MANUAL_FLIGHT"), (1., 1., "MANUAL_FLIGHT"),
                (1., 1., "RETURN_TO_DOCK"), (0., 1., "RETURN_TO_DOCK"),
                (0., .5, "DOCKING"), (0., 0., "COMPLETE"),
            ]
            recorder = RouteRecorder(teaching.root, SESSION, "INS", vars(Model()), {"contact": True})
            try:
                for index, (x, z, stage) in enumerate(states):
                    sample = observation(index, x, z, stage, index in (0, len(states)-1))
                    pose = Pose(index * 100_000_000, 0., (x, 0., z), tuple(QUATERNION), 0., 0., (.01, .01, .01))
                    recorder.add(pose, sample, force=True)
            finally:
                recorder.finish("COMPLETE", True, {"sorties": []})
                self.assertTrue(recorder.done.wait(2.))
            original = review.action("review", SESSION, {})
            request = {"route_sha256": original["route_sha256"], "confirm": True}
            valid = review.action("validate", SESSION, request)
            self.assertTrue(valid["validation"]["valid"])
            self.assertEqual(review.action("approve", SESSION, request)["status"], "approved")
            self.assertEqual(RouteReview(Teaching(Path(scratch), None), PROFILE).state(SESSION)["status"], "approved")
            open_aisle = RouteReview(teaching, PROFILE, "open-aisle")
            with self.assertRaisesRegex(ValueError, "different warehouse geometry"):
                open_aisle.action("review", SESSION, {})
            result = review.read(SESSION, "result.json")
            open_aisle.write(SESSION, "result.json", {**result, "warehouse_variant": "open-aisle"})
            with self.assertRaisesRegex(ValueError, "different warehouse geometry"):
                review.action("review", SESSION, {})
            self.assertEqual(open_aisle.state(SESSION)["status"], "stale")
            review.write(SESSION, "result.json", result)
            route = review.read(SESSION, "route.json")
            route["nodes"][3]["position_m"][1] = 5.
            review.write(SESSION, "route.json", route)
            altered = review.state(SESSION)
            invalid = review.action("validate", SESSION, {"route_sha256": altered["route_sha256"]})
            self.assertFalse(invalid["validation"]["valid"])
            self.assertIn("leave the approved flight volume", invalid["validation"]["issues"][0])
            manifest["locations"][0]["position_m"][2] += .02
            manifest["revision"] += 1
            teaching.write_manifest(SESSION, manifest)
            self.assertEqual(review.state(SESSION)["status"], "stale")
            with self.assertRaisesRegex(RuntimeError, "route changed"):
                review.action("approve", SESSION, request)
