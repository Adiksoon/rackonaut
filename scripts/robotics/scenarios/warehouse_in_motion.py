"""Stage three physical Gazebo events and verify reports from the real inspection stack."""

import argparse
from hashlib import sha256
import json
from math import hypot
import os
from pathlib import Path
import signal
import subprocess
from time import monotonic, sleep
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ASSETS = Path(__file__).resolve().parent
SLOTS = ("A-01-01", "A-01-02", "A-01-03")
CART = "scenario_loaded_cart"
WRAP = "scenario_label_wrap"
PARKED = (5.10, -1.82, 0.)
BLOCKED = (5.10, .45, 0.)
LABEL = (5.76, 2.504, .94)
TERMINAL = {"ABORTED", "COMPLETE", "COMPLETE_WITH_MISSES", "ERROR"}


def pose(position):
    return "position { x: %.4f y: %.4f z: %.4f } orientation { w: 1 }" % position


def gazebo(service, request_type, payload):
    result = subprocess.run(
        ["ign", "service", "-s", f"/world/rackonaut/{service}", "--reqtype", f"ignition.msgs.{request_type}",
         "--reptype", "ignition.msgs.Boolean", "--timeout", "1500", "--req", payload],
        capture_output=True, text=True, timeout=4, check=True,
    )
    if "data: true" not in result.stdout:
        raise RuntimeError(f"Gazebo rejected {service}: {result.stdout.strip()} {result.stderr.strip()}")


def spawn(name, asset, position):
    gazebo("create", "EntityFactory",
           f"name: {json.dumps(name)} sdf_filename: {json.dumps(str(ASSETS / asset))} pose {{ {pose(position)} }} "
           "allow_renaming: false")


def move(name, position):
    gazebo("set_pose", "Pose", f"name: {json.dumps(name)} {pose(position)}")


def cross(start, end):
    for fraction in (.25, .50, .75, 1.):
        y = start[1] + fraction * (end[1] - start[1])
        move(CART, (start[0], y, start[2]))
        sleep(.10)


class Scenario:
    def __init__(self, output, http_port, mock_port):
        self.output = output
        self.http_port = http_port
        self.mock_port = mock_port
        self.events = []
        self.run_id = None
        self.cart_in_lane = False

    def request(self, path, payload=None, *, port=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(f"http://127.0.0.1:{port or self.http_port}{path}", data=data,
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=3) as response:
            return response.read()

    def read(self, path, payload=None, *, port=None):
        return json.loads(self.request(path, payload, port=port))

    def event(self, name, **details):
        entry = {"event": name, **details}
        self.events.append(entry)
        with (self.output / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry) + "\n")
        print(json.dumps(entry), flush=True)

    def wait_ready(self):
        deadline = monotonic() + 90
        while monotonic() < deadline:
            try:
                state = self.read("/api/state")
            except (URLError, OSError):
                sleep(.25)
                continue
            if (state["drone_model"] == "x3" and state["physical_dock"] and state["at_pad"]
                    and not state["busy"] and state["camera"]
                    and state["backend"]["online"] and state["backend"]["mode"] == "mock_sap"
                    and (state["localization"] or {}).get("state") == "TRACKING"
                    and (state["energy"] or {}).get("contact")
                    and (state["safety"] or {}).get("signals_online")):
                return
            sleep(.25)
        raise RuntimeError("Full Robotics did not become ready")

    def verify(self, mission, state):
        status = mission["status"]
        result = mission.get("result")
        if (mission["stage"] != "COMPLETE" or set(status["confirmed"]) != set(SLOTS)
                or not status["landed"] or not state["physical_dock"]
                or state["safety"]["phase"] != "RELEASED"):
            raise RuntimeError(f"Inspection did not land and confirm all requested slots: {status['detail']}")
        observed_events = {row["event"] for row in self.events}
        if self.cart_in_lane or not {"label_covered", "lidar_stop", "autonomous_resume"} <= observed_events:
            raise RuntimeError("The label cover, measured stop or autonomous resume was not observed")
        query = urlencode({"inspection_id": self.run_id})
        discrepancies = self.read(f"/api/discrepancies?{query}", port=self.mock_port)
        actual = {row["slot_id"]: row for row in discrepancies}
        expected = {"A-01-01": "unreadable_label", "A-01-02": "wrong_pallet", "A-01-03": "missing_pallet"}
        for slot, outcome in expected.items():
            if actual.get(slot, {}).get("outcome") != outcome:
                raise RuntimeError(f"{slot}: expected {outcome}, received {actual.get(slot)}")
        observations = status["confirmed"]
        if (observations["A-01-01"]["occupancy"], observations["A-01-01"]["label_status"],
                observations["A-01-01"]["pallet_id"], observations["A-01-02"]["pallet_id"]) != (
                    "occupied", "unreadable", None, "P003"):
            raise RuntimeError("Camera observations do not match the staged warehouse")
        business = self.read(f"/api/business/summary?{query}", port=self.mock_port)
        issues = {row["type"] for row in business["issues"]}
        if not {"UNREADABLE_LABEL", "WRONG_PALLET", "MISSING_PALLET", "MISPLACED_PALLET"} <= issues:
            raise RuntimeError("Mock SAP did not produce the expected business findings")
        photos = {}
        for slot, event in observations.items():
            row = next(row for row in business["slots"] if row["slot_id"] == slot)
            proof = next((item for item in row["quality_history"] if item["status"] == "CAPTURED"
                          and item["inspection_id"] == self.run_id and item["slot_id"] == slot
                          and item["observation_id"] == event["observation_id"]
                          and item["timestamp"] == item["observation_timestamp"] == event["timestamp"]
                          and item["occupancy"] == event["occupancy"]), None)
            if proof is None:
                raise RuntimeError(f"No original was linked to the camera observation at {slot}")
            original = self.request(proof["photos"]["original"])
            if not original.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError(f"The original at {slot} was not a PNG")
            filename = f"{slot}-original.png"
            (self.output / filename).write_bytes(original)
            photos[slot] = {"file": filename, "observation_id": event["observation_id"],
                            "sha256": sha256(original).hexdigest(), "camera": proof["camera"]}
        html = self.request(result["url"])
        if self.run_id.encode() not in html or not all(slot.encode() in html for slot in SLOTS):
            raise RuntimeError("Inspection report does not contain the expected run and locations")
        if not all(f"class='outcome {outcome}'".encode() in html for outcome in expected.values()):
            raise RuntimeError("Inspection report does not render all verified discrepancies")
        (self.output / "report.html").write_bytes(html)
        (self.output / "result.json").write_text(json.dumps({
            "inspection_id": self.run_id, "drone_model": state["drone_model"],
            "confirmed": observations, "discrepancies": discrepancies, "photos": photos,
            "business_findings": [{"type": row["type"], "slot_id": row["slot_id"]} for row in business["issues"]],
            "landed": True, "physical_dock": True, "safety": "RELEASED", "report_http": 200,
            "wall_seconds": round(monotonic() - self.started_at, 1), "events": self.events,
        }, indent=2) + "\n")
        self.event("verified", inspection_id=self.run_id, confirmed=len(SLOTS), report_http=200)

    def run(self):
        self.wait_ready()
        spawn(CART, "warehouse-cart.sdf", PARKED)
        selection = {"mode": "custom", "slots": list(SLOTS), "quality": True}
        plan = self.read("/api/plan", selection)
        if plan["slots"] != list(SLOTS) or not plan["energy"]["can_start"]:
            raise RuntimeError("Scenario flight plan was rejected")
        self.run_id = self.read("/api/start", selection)["inspection_id"]
        self.started_at = monotonic()
        self.event("started", inspection_id=self.run_id, slots=list(SLOTS))
        wrapped = False
        cart_entered_at = None
        stopped_pose = None
        resumed = False
        deadline = monotonic() + 650
        while monotonic() < deadline:
            state = self.read("/api/state")
            mission = state["mission"] or {}
            if mission.get("inspection_id") != self.run_id:
                raise RuntimeError("Control Center changed the active inspection")
            status, stage = mission["status"] or {}, mission["stage"]
            if stage == "OVERHEAD_TRANSIT" and not wrapped:
                spawn(WRAP, "warehouse-label-cover.sdf", LABEL)
                wrapped = True
                self.event("label_covered", slot=SLOTS[0])
            if stage == "OVERHEAD_TRANSIT" and cart_entered_at is None:
                self.cart_in_lane = True
                cart_entered_at = monotonic()
                cross(PARKED, BLOCKED)
                self.event("cart_entered", gate="A")
            if self.cart_in_lane and stage == "AISLE_DESCENT":
                events = (status.get("avoidance") or {}).get("events", [])
                stop = next((row for row in reversed(events) if row.get("stage") == "AISLE_DESCENT" and row.get("detected", 0) >= cart_entered_at
                             and row.get("reason") == "measured obstacle" and row.get("stopped_at")
                             and hypot(row["stopped_at"][0] - BLOCKED[0],
                                       row["stopped_at"][1] - BLOCKED[1]) < .25
                             and row["stopped_at"][2] > 1.80), None)
                if stop:
                    stopped_pose = stop["stopped_at"]
                    self.event("lidar_stop", **stop)
                    cross(BLOCKED, PARKED)
                    self.cart_in_lane = False
                    self.event("cart_cleared", gate="A")
            if (stopped_pose and not self.cart_in_lane and not resumed
                    and stage == "AISLE_DESCENT" and state["position_fresh"]
                    and state["position"][2] < stopped_pose[2] - .15):
                resumed = True
                self.event("autonomous_resume", stage=stage, position=state["position"][:3])
            if stage in TERMINAL:
                (self.output / "final-state.json").write_text(json.dumps(state, indent=2) + "\n")
            if (stage == "COMPLETE" and mission.get("result")
                    and state["physical_dock"] and state["safety"]["phase"] == "RELEASED"):
                self.verify(mission, state)
                return
            if stage in TERMINAL and stage != "COMPLETE":
                raise RuntimeError(mission.get("error") or status.get("detail") or stage)
            sleep(.10)
        raise RuntimeError("Scenario timed out")


def cleanup(output):
    root = ASSETS.parents[2]
    workers = {str(root / "ros2_ws/install" / package / "lib" / package / executable)
               for package, executable in (("rackonaut_mission", "run_mission"), ("rackonaut_perception", "inspect"))}
    runs = {entry.name for entry in (output / "data/dispatch").glob("INS-CONTROL-*")}
    for process in Path("/proc").iterdir():
        if not process.name.isdecimal():
            continue
        try:
            args = (process / "cmdline").read_text(errors="replace").split("\0")
            if workers.intersection(args) and any(f"inspection_id:={run}" in args for run in runs):
                os.kill(int(process.name), signal.SIGTERM)
        except OSError:
            continue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("http_port", type=int, nargs="?")
    parser.add_argument("mock_port", type=int, nargs="?")
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.cleanup:
        cleanup(args.output)
        return
    if not args.http_port or not args.mock_port:
        parser.error("HTTP and Mock SAP ports are required")
    scenario = Scenario(args.output, args.http_port, args.mock_port)
    try:
        scenario.run()
    finally:
        if scenario.cart_in_lane:
            move(CART, PARKED)


if __name__ == "__main__":
    main()
