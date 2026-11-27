"""Archive, validate and approve route proposals without sending motion commands."""

import hashlib
import json
from datetime import datetime, timezone
from math import isfinite

from rackonaut_energy.aerial import Network
from rackonaut_energy.model import Model
from rackonaut_localization.learned_map import MAP_FILE
from rackonaut_localization.warehouse_config import (HISTORICAL_VARIANT, MAX_SORTIES, check_warehouse_variant,
                                                    file_hash, trajectory_file)
from rackonaut_mission.learned import forecast as execution_forecast, ordered_targets

from .learned_route import forecast, graph, ns
from .route_recording import FORMAT, MAX_SAMPLES
from .teaching import FRAME, atomic_write, session_path


ROUTE_FILES = {"trajectory.jsonl", "route.json", "route-validation.json", "sorties.json",
               *(trajectory_file(number) for number in range(1, MAX_SORTIES + 1))}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def finite_vector(values, size):
    return (isinstance(values, list) and len(values) == size
            and all(type(v) in (int,float) and isfinite(v) for v in values))


def mission_forecast(route, selected, model, network):
    targets, _ = ordered_targets(route, selected, network)
    stops = [index for index, (_, _, slot, _, _) in enumerate(targets) if slot]
    xyz = [entry[1] for entry in targets]
    budget = execution_forecast(model, (*route["nodes"][0]["position_m"], route["nodes"][0]["yaw_rad"]),
                                xyz, len(stops), stops[-1] if stops else None)
    return {**budget, "duration_sim_s": budget["seconds"], "mission_percent": budget["percent"],
            "within_capacity": budget["required_percent"] <= 100.}


def aggregate_forecasts(budgets):
    return {"distance_m": round(sum(b["distance_m"] for b in budgets), 3),
            "climb_m": round(sum(b["climb_m"] for b in budgets), 3),
            "duration_sim_s": round(sum(b["duration_sim_s"] for b in budgets), 2),
            "mission_percent": round(sum(b["mission_percent"] for b in budgets), 3),
            "return_percent": max((b["return_percent"] or 0.) for b in budgets),
            "reserve_percent": max(b["reserve_percent"] for b in budgets),
            "required_percent": max(b["required_percent"] for b in budgets),
            "within_capacity": all(b["within_capacity"] for b in budgets)}


class RouteReview:
    def __init__(self, teaching, profile, warehouse_variant=HISTORICAL_VARIANT):
        self.teaching = teaching
        self.root = teaching.root
        self.profile = profile
        self.warehouse_variant = warehouse_variant

    def read(self, session, name):
        try:
            return json.loads(session_path(self.root, session, name).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None

    def write(self, session, name, payload):
        atomic_write(session_path(self.root, session, name), (json.dumps(payload, indent=2, allow_nan=False)+"\n").encode())

    def trajectory(self, session, number=None, entry=None):
        path = session_path(self.root, session, trajectory_file(number))
        if not path.is_file():
            raise RuntimeError("The mapping archive or timed trajectory is incomplete.")
        with path.open("rb") as stream:
            data = stream.read(16_000_001)
        if len(data) > 16_000_000:
            raise ValueError("The captured trajectory exceeds the review limit.")
        lines = data.splitlines()
        if not 4 <= len(lines) <= MAX_SAMPLES+2:
            raise ValueError("The captured trajectory is incomplete.")
        header, *samples, footer = (json.loads(line) for line in lines)
        if (header.get("kind")!="header" or header.get("source")!="slam" or footer.get("kind")!="end"
                or not footer.get("complete") or not footer.get("physical_dock")
                or footer.get("stage")!="COMPLETE" or footer.get("sample_count")!=len(samples)):
            raise ValueError("The recording must include a complete SLAM flight and verified docking.")
        if entry is not None and (header.get("sortie") != number or header.get("inspection_id") != entry["inspection_id"]
                                  or header["takeoff_dock"].get("contact_source") != "gazebo_dock_switch"
                                  or footer["energy"].get("dock_contact_source") != "gazebo_dock_switch"
                                  or entry["samples"] != len(samples)):
            raise ValueError("The sortie index disagrees with the measured dock-to-dock journal.")
        for row in [header,*samples,footer]:
            if row.get("mapping_id")!=session or row.get("frame")!=FRAME or row.get("schema_version")!=FORMAT:
                raise ValueError("The archive contains conflicting mapping IDs, frame or format.")
        previous = -1
        for i,row in enumerate(samples):
            if (row.get("kind")!="pose" or row.get("index")!=i or not finite_vector(row.get("position_m"),3)
                    or not finite_vector(row.get("orientation_xyzw"),4) or not finite_vector(row.get("position_sigma_m"),3)
                    or ns(row["stamp"])<=previous):
                raise ValueError(f"Invalid timed SLAM sample at index {i}.")
            previous=ns(row["stamp"])
        return samples, header, footer, hashlib.sha256(data).hexdigest()

    def inputs(self, session):
        if not self.profile:
            raise ValueError("Route review requires the protected aerial profile.")
        result = self.read(session, "result.json")
        if not result or result.get("mapping_id") != session or result.get("frame") != FRAME:
            raise RuntimeError("Route review requires the saved map from verified docking.")
        check_warehouse_variant(result, self.warehouse_variant)
        if not session_path(self.root, session, "map.ply").is_file():
            raise RuntimeError("The mapping archive or timed trajectory is incomplete.")
        manifest = self.teaching.manifest(session)
        dependency = {
                      "locations_sha256": digest(manifest), "profile_sha256": digest(self.profile),
                      "map_result_sha256": digest(result)}
        multi = result.get("multi_sortie") is True
        if multi:
            entries = self.read(session, "sorties.json")
            if (not isinstance(entries, list) or not 1 <= len(entries) <= MAX_SORTIES or any(
                not isinstance(entry, dict) or entry.get("number") != number
                or entry.get("trajectory") != trajectory_file(number) or entry.get("status") != "DOCKED"
                for number, entry in enumerate(entries, 1)
            )):
                raise ValueError("The calibration has no complete sortie index.")
            flights = [self.trajectory(session, number, entry) for number, entry in enumerate(entries, 1)]
            if len({entry["inspection_id"] for entry in entries}) != len(entries) or any(
                ns(first[0][-1]["stamp"]) >= ns(second[0][0]["stamp"]) for first, second in zip(flights, flights[1:])
            ):
                raise ValueError("Calibration sorties overlap or repeat a mission.")
            dependency.update(sortie_index_sha256=file_hash(session_path(self.root, session, "sorties.json")),
                              trajectory_sha256_by_sortie=[flight[3] for flight in flights])
        else:
            flights = [self.trajectory(session)]
            dependency["trajectory_sha256"] = flights[0][3]
        if result.get("localization_archive") == MAP_FILE:
            dependency.update(map_sha256=file_hash(session_path(self.root, session, "map.ply")),
                              localization_sha256=file_hash(session_path(self.root, session, MAP_FILE)))
        return flights, manifest, dependency

    def proposal(self, flights, manifest, multi):
        if not multi:
            rows, header, footer, _ = flights[0]
            return graph(rows, self.profile, manifest, header, footer)
        network = Network(self.profile)
        sorties = []
        bound = set()
        for number, (rows, header, footer, _) in enumerate(flights, 1):
            start, end = ns(rows[0]["stamp"]), ns(rows[-1]["stamp"])
            records = [row for row in manifest["locations"] if start < ns(row["camera_stamp"]) < end]
            route = graph(rows, self.profile, {**manifest, "locations": records}, header, footer,
                          require_locations=False)
            selected = {row["record_id"] for row in records}
            bound |= selected
            route["forecast"] = mission_forecast(route, selected, Model(**header["energy_model"]), network)
            route["sortie"] = number
            prefix = f"S{number:02d}-"
            for node in route["nodes"]:
                node["id"] = prefix + node["id"]
            for edge in route["edges"]:
                edge["from"], edge["to"] = prefix + edge["from"], prefix + edge["to"]
            for location in route["locations"]:
                location["node"] = prefix + location["node"]
            sorties.append(route)
        if not bound or bound != {row["record_id"] for row in manifest["locations"]}:
            raise ValueError("Every taught location must be bound to a recorded sortie.")
        return {**sorties[0], "sortie": None, "sorties": sorties,
                **{key: [row for route in sorties for row in route[key]] for key in ("nodes", "edges", "locations")},
                "summary": {
                    **{key: sum(route["summary"][key] for route in sorties)
                       for key in ("raw_samples", "waypoints", "recorded_distance_m", "learned_distance_m")},
                    "max_deviation_m": max(route["summary"]["max_deviation_m"] for route in sorties),
                },
                "forecast": aggregate_forecasts([route["forecast"] for route in sorties]),
                "calibration_energy": [route["calibration_energy"] for route in sorties]}

    def state(self, session, inputs=None):
        flights, manifest, dependency = inputs or self.inputs(session)
        route = self.read(session,"route.json")
        validation = self.read(session,"route-validation.json")
        payload = {"mapping_id":session,"status":"unreviewed","route":None,"validation":None,
                   "raw_positions":[row["position_m"] for samples, _, _, _ in flights for row in samples],
                   "locations":manifest["locations"]}
        if route and route.get("inputs")!=dependency:
            payload["status"]="stale"
            return payload
        if not route:
            return payload
        signature = digest({k:v for k,v in route.items() if k!="approval"})
        current = validation if validation and validation.get("route_sha256")==signature else None
        approved = route.get("approval")
        status = ("approved" if current and current["valid"] and approved and approved.get("route_sha256")==signature
                  else "validated" if current and current["valid"] else "rejected" if current else "review")
        return {**payload,"route":route,"validation":current,"status":status,"route_sha256":signature}

    def action(self, action, session, request):
        source = self.inputs(session)
        flights, manifest, dependency = source
        multi = "sortie_index_sha256" in dependency
        view = self.state(session,source)
        route = view["route"]
        if action=="review":
            if route is None:
                route = {**self.proposal(flights, manifest, multi), "inputs": dependency}
                self.write(session,"route.json",route)
            return self.state(session,source)
        if not route or request.get("route_sha256")!=view["route_sha256"]:
            raise RuntimeError("The learned route changed. Review the current revision first.")
        signature = view["route_sha256"]
        if action=="validate":
            validation = {"schema_version":FORMAT,"mapping_id":session,"frame":FRAME,
                          "location_revision":manifest["revision"],"route_sha256":signature,
                          "scope":"historical_envelope", "live_clearance":"required"}
            try:
                expected = self.proposal(flights, manifest, multi)
                network = Network(self.profile)
                points = {point["id"]: point["position_m"] for point in route["nodes"]}
                outside = [index for index, edge in enumerate(route["edges"])
                           if not network.allows(points[edge["from"]], points[edge["to"]], edge["required_zones"])]
                if outside:
                    raise ValueError(f"Route segments leave the approved flight volume: {outside}.")
                if any(route.get(k)!=v for k,v in expected.items()):
                    raise ValueError("The route does not match its measured source and directed edges.")
                validation.update(valid=route["forecast"]["within_capacity"],validated_segments=len(route["edges"]),
                                  issues=[] if route["forecast"]["within_capacity"] else ["Model budget plus reserve exceeds 100%."])
                if multi:
                    validation["sorties"] = [{"number": leg["sortie"], "edges": len(leg["edges"]),
                                              "forecast": leg["forecast"]} for leg in route["sorties"]]
            except (ValueError, KeyError, IndexError, TypeError) as error:
                validation.update(valid=False,validated_segments=0,issues=[str(error)])
            self.write(session,"route-validation.json",validation)
            return self.state(session,source)
        if view["status"] not in {"validated","approved"}:
            raise RuntimeError("Validate the measured route before planning or approving.")
        if action=="approve":
            if request.get("confirm") is not True:
                raise ValueError("Confirm approval of this reviewed route.")
            self.write(session,"route.json",{**route,"approval":{"route_sha256":signature,
                       "approved_at_utc":datetime.now(timezone.utc).isoformat(),
                       "location_revision":manifest["revision"]}})
            return self.state(session,source)
        ids=request.get("record_ids")
        known={item["record_id"] for item in route["locations"]}
        if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in known for i in ids):
            raise ValueError("Select learned locations from the current route.")
        chosen=set(ids)
        budgets = None
        if multi:
            network = Network(self.profile)
            budgets = [mission_forecast(leg, chosen & {row["record_id"] for row in leg["locations"]},
                                        Model(**flight[1]["energy_model"]), network)
                       for leg, flight in zip(route["sorties"], flights)
                       if any(row["record_id"] in chosen for row in leg["locations"])]
        return {"mapping_id":session,"route_sha256":signature,
                "selected":[item for item in route["locations"] if item["record_id"] in chosen],
                "waypoint_ids":[node["id"] for node in route["nodes"]],
                "edges":len(route["edges"]),
                "forecast":aggregate_forecasts(budgets) if multi else forecast(route["nodes"],chosen,Model(**flights[0][1]["energy_model"])),
                **({"sorties": budgets} if multi else {})}
