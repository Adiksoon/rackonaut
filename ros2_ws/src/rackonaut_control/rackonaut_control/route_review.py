"""Archive, validate and approve route proposals without sending motion commands."""

import hashlib
import json
from datetime import datetime, timezone
from math import isfinite

from rackonaut_energy.aerial import Network
from rackonaut_energy.model import Model
from rackonaut_localization.learned_map import MAP_FILE
from rackonaut_localization.warehouse_config import HISTORICAL_VARIANT, check_warehouse_variant, file_hash

from .learned_route import forecast, graph, ns
from .route_recording import FORMAT, MAX_SAMPLES
from .teaching import FRAME, atomic_write, session_path


ROUTE_FILES = {"trajectory.jsonl", "route.json", "route-validation.json"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def finite_vector(values, size):
    return (isinstance(values, list) and len(values) == size
            and all(type(v) in (int,float) and isfinite(v) for v in values))


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

    def inputs(self, session):
        if not self.profile:
            raise ValueError("Route review requires the protected aerial profile.")
        path = session_path(self.root, session, "trajectory.jsonl")
        result = self.read(session,"result.json")
        if not result or result.get("mapping_id") != session or result.get("frame") != FRAME:
            raise RuntimeError("Route review requires the saved map from verified docking.")
        check_warehouse_variant(result, self.warehouse_variant)
        if not session_path(self.root,session,"map.ply").is_file() or not path.is_file():
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
        manifest = self.teaching.manifest(session)
        dependency = {"trajectory_sha256": hashlib.sha256(data).hexdigest(),
                      "locations_sha256": digest(manifest), "profile_sha256": digest(self.profile),
                      "map_result_sha256": digest(result)}
        if result.get("localization_archive") == MAP_FILE:
            dependency.update(map_sha256=file_hash(session_path(self.root, session, "map.ply")),
                              localization_sha256=file_hash(session_path(self.root, session, MAP_FILE)))
        return samples, manifest, header, footer, dependency

    def state(self, session, inputs=None):
        samples, manifest, _, _, dependency = inputs or self.inputs(session)
        route = self.read(session,"route.json")
        validation = self.read(session,"route-validation.json")
        payload = {"mapping_id":session,"status":"unreviewed","route":None,"validation":None,
                   "raw_positions":[row["position_m"] for row in samples], "locations":manifest["locations"]}
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
        samples,manifest,header,footer,dependency = source
        view = self.state(session,source)
        route = view["route"]
        if action=="review":
            if route is None:
                route = {**graph(samples,self.profile,manifest,header,footer),"inputs":dependency}
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
                expected = graph(samples,self.profile,manifest,header,footer)
                network = Network(self.profile)
                outside = [index for index,(a,b) in enumerate(zip(route["nodes"],route["nodes"][1:]))
                           if not network.allows(a["position_m"],b["position_m"],route["edges"][index]["required_zones"])]
                if outside:
                    raise ValueError(f"Route segments leave the approved flight volume: {outside}.")
                if any(route.get(k)!=v for k,v in expected.items()):
                    raise ValueError("The route does not match its measured source and directed edges.")
                validation.update(valid=route["forecast"]["within_capacity"],validated_segments=len(route["edges"]),
                                  issues=[] if route["forecast"]["within_capacity"] else ["Model budget plus reserve exceeds 100%."])
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
        return {"mapping_id":session,"route_sha256":signature,
                "selected":[item for item in route["locations"] if item["record_id"] in chosen],
                "waypoint_ids":[node["id"] for node in route["nodes"]],
                "edges":len(route["edges"]),"forecast":forecast(route["nodes"],chosen,Model(**header["energy_model"]))}
