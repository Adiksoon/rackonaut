"""Build a directed calibration route using only the recorded flight."""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from math import atan2, cos, degrees, dist, hypot, radians, sin

import numpy as np

from rackonaut_avoidance.manual import BOUNDARY_MARGIN
from rackonaut_avoidance.planner import HALF_HEIGHT, LOOKAHEAD, RADIUS
from rackonaut_energy.aerial import Network, interval, segment_inside
from rackonaut_energy.model import Model

from .route_recording import FORMAT
from .teaching import FRAME, SECOND


MAX_GAP_NS = int(.52 * SECOND)
SIMPLIFICATION_M = .015
PRESERVE_YAW_RAD = radians(7)
HOVER_M = .024
MERGE_WINDOW = 28
DOCK_LIMIT_M = .12
OBSTRUCTED = {"BRAKING", "BLOCKED", "FAULT", "ABORTED", "RECOVERY_REQUIRED"}


def ns(stamp):
    return stamp["sec"] * SECOND + stamp["nanosec"]


def yaw(q):
    x, y, z, w = q
    return atan2(2 * (w*z + x*y), 1 - 2 * (y*y + z*z))


def angle(delta):
    return atan2(sin(delta), cos(delta))


@dataclass
class Knot:
    time: int
    xyz: np.ndarray
    quaternion: list | None
    phase: tuple
    raw: tuple
    locations: list = field(default_factory=list)


def raw_knots(rows):
    return [Knot(ns(row["stamp"]), np.asarray(row["position_m"]), row["orientation_xyzw"],
                 (row["stage"], row["flight_phase"]), (i, i)) for i, row in enumerate(rows)]


def with_inspections(knots, records):
    stamps = [point.time for point in knots]
    by_time = {point.time: point for point in knots}
    for record in records:
        time = ns(record["camera_stamp"])
        i = bisect_left(stamps, time)
        if i == len(knots) or i == 0:
            raise ValueError(f'{record["storage_location_id"]}: camera time is outside the recorded flight.')
        a, b = knots[i-1], knots[i]
        if b.time - a.time > MAX_GAP_NS or a.phase[0] != "MANUAL_FLIGHT" or b.phase[0] != "MANUAL_FLIGHT":
            raise ValueError(f'{record["storage_location_id"]}: camera time lacks a continuous manual flight bracket.')
        alpha = (time-a.time)/(b.time-a.time)
        xyz = np.asarray(record["position_m"])
        q = record["orientation_xyzw"]
        heading = yaw(a.quaternion) + alpha * angle(yaw(b.quaternion)-yaw(a.quaternion))
        if dist(xyz, a.xyz+alpha*(b.xyz-a.xyz)) > .035 or abs(angle(yaw(q)-heading)) > .12:
            raise ValueError(f'{record["storage_location_id"]}: measured inspection pose differs from its time bracket.')
        if time not in by_time or not by_time[time].locations:
            by_time[time] = Knot(time, xyz, q, a.phase, (i-1, i))
        bound = by_time[time]
        if not np.allclose(bound.xyz, xyz, atol=1.e-7) or not np.allclose(bound.quaternion, q, atol=1.e-7):
            raise ValueError("Two records at the same camera time disagree on the pose.")
        bound.locations.append(record)
    return [by_time[stamp] for stamp in sorted(by_time)]


def deviation(points, first, last):
    start, end = points[first], points[last]
    line = end-start
    length = float(np.linalg.norm(line))
    if length < 1.e-8:
        return 0., np.linalg.norm(points[first:last+1]-start, axis=1), None
    direction = line/length
    steps = points[first:last+1]-start
    along = steps @ direction
    offsets = steps - np.clip(along, 0., length)[:, None]*direction
    return length, np.linalg.norm(offsets, axis=1), along


def measure_safety(rows, network):
    for i, (a,b) in enumerate(zip(rows,rows[1:])):
        if a["dock_contact"] or b["dock_contact"]:
            zones = set(a["safety"]["zones"]) | set(b["safety"]["zones"]) | {"D"}
        else:
            zones = set(a["safety"]["zones"]) & set(b["safety"]["zones"])
        if not network.allows(a["position_m"], b["position_m"], sorted(zones)):
            raise ValueError(f"Recorded segment {i} leaves its approved flight volume.")
        if ns(b["stamp"])-ns(a["stamp"]) > MAX_GAP_NS:
            raise ValueError(f"Trajectory gap after sample {i} exceeds {MAX_GAP_NS/SECOND:.2f} s.")
        if a["localization"]["state"] != "TRACKING" or b["localization"]["state"] != "TRACKING":
            raise ValueError(f"Missing tracking at sample {i}.")
        if not (a["dock_contact"] or b["dock_contact"] or
                a["safety"]["phase"] == "RESERVED" and b["safety"]["phase"] == "RESERVED" and
                a["safety"]["verified"] and b["safety"]["verified"]):
            raise ValueError(f"Missing flight reservation evidence at sample {i}.")


def inset_volumes(network, zones, clearance):
    return [[*(value+clearance for value in box[:3]), *(value-clearance for value in box[3:])]
            for box in network.volumes(zones) if all(b-a>2*clearance for a,b in zip(box[:3],box[3:]))]


def swept_support(rows, start, end):
    """The original commanded direction must cover each appreciable measured step."""
    for a, b in zip(rows[start:end], rows[start+1:end+1]):
        motion = np.subtract(b["position_m"],a["position_m"])
        length = float(np.linalg.norm(motion))
        if length <= .018:
            continue
        states = (a["collision"], b["collision"])
        if any(state["state"] in OBSTRUCTED for state in states):
            return False
        if not any(state["scan_age_ms"] is not None and state["scan_age_ms"] <= 650
                   and state["verified_distance_m"] >= length + 2*SIMPLIFICATION_M
                   and state["direction"] and np.dot(state["direction"],motion) >= .90*length
                   for state in states):
            return False
    return True


def simplify(knots, network, zones, rows=None):
    points = np.array([k.xyz for k in knots])
    headings = np.unwrap([yaw(k.quaternion) if k.quaternion is not None else 0. for k in knots])
    mandatory = {0, len(knots)-1}
    for i, k in enumerate(knots):
        if k.locations or i and k.phase!=knots[i-1].phase:
            mandatory.add(i)
            if i:
                mandatory.add(i-1)
    stops = sorted(mandatory)
    keep = [0]
    for boundary in stops[1:]:
        first = keep[-1]
        while first < boundary:
            last = min(boundary, first+MERGE_WINDOW)
            while last > first+1:
                length, errors, along = deviation(points, first, last)
                if length > LOOKAHEAD or errors.max() > SIMPLIFICATION_M:
                    last -= 1
                    continue
                progression = (np.linspace(0.,1.,last-first+1) if length<HOVER_M
                               else np.clip(along/length,0.,1.))
                expected_yaw = headings[first]+progression*(headings[last]-headings[first])
                check_yaw = np.max(abs(headings[first:last+1]-expected_yaw)) <= PRESERVE_YAW_RAD
                # Reject a loop that stays close to a line but reverses direction on it.
                monotonic = length<HOVER_M or np.min(np.diff(along))>=-.002
                if not (check_yaw and monotonic and network.allows(points[first], points[last], zones)):
                    last -= 1
                    continue
                if rows is not None:
                    a,b=knots[first].raw[0],knots[last].raw[1]
                    sigma = max(max(sample["position_sigma_m"]) for sample in rows[a:b+1])
                    current_zones = set(zones)
                    for sample in rows[a:b+1]:
                        if not sample["dock_contact"]:
                            current_zones.intersection_update(sample["safety"]["zones"])
                    volumes=inset_volumes(network,sorted(current_zones),BOUNDARY_MARGIN+sigma+errors.max())
                    if not segment_inside(points[first],points[last],volumes):
                        last -= 1
                        continue
                    if length>=HOVER_M and not swept_support(rows,a,b):
                        last -= 1
                        continue
                break
            keep.append(last)
            first = last
    return keep


def forecast(nodes, selected, model):
    """Model continuous fly-through at the existing controller's estimate speeds."""
    visits = [i for i, n in enumerate(nodes) if selected.intersection(n["record_ids"])]
    seconds = [0.]
    costs = [0.]
    ascent = 0.
    distance = 0.
    for a,b in zip(nodes,nodes[1:]):
        dx,dy,dz = (end-start for start,end in zip(a["position_m"],b["position_m"]))
        horizontal = hypot(dx,dy)
        delta_yaw = abs(angle(b["yaw_rad"]-a["yaw_rad"]))
        duration = max(horizontal/.48,abs(dz)/.37,delta_yaw/.31)
        distance += dist(a["position_m"],b["position_m"])
        ascent += max(0.,dz)
        used = model.draw(horizontal/duration,0.,dz/duration,True)*duration if duration else 0.
        seconds.append(duration)
        costs.append(used)
    dwell = len(visits)*3. + 2*.85
    total = sum(costs)+model.hover*dwell
    return {"distance_m":round(distance,3), "climb_m": round(ascent,3),
            "duration_sim_s":round(sum(seconds)+dwell,2), "mission_percent":round(total,3),
            "return_percent":round(sum(costs[visits[-1]+1:])+model.hover*.85,3) if visits else None,
            "reserve_percent":model.reserve, "required_percent":round(total+model.reserve,3),
            "within_capacity":total+model.reserve<=100.}


def required_zones(network, a, b, reserved):
    return [zone for zone in reserved if any(interval(a,b,box) is not None for box in network.reservable[zone])]


def graph(rows, profile, manifest, header, footer):
    network = Network(profile)
    zones = sorted({zone for row in rows for zone in row["safety"]["zones"]})
    if not zones or any(zone not in network.reservable for zone in zones):
        raise ValueError("The recording contains an unknown or empty reservation.")
    if not manifest["locations"]:
        raise ValueError("Teach at least one measured location before reviewing the route.")
    measure_safety(rows, network)
    origin = network.nodes["dock"][:3]
    if not (rows[0]["dock_contact"] and rows[-1]["dock_contact"]
            and dist(rows[0]["position_m"],origin)<=DOCK_LIMIT_M
            and dist(rows[-1]["position_m"],origin)<=DOCK_LIMIT_M):
        raise ValueError("The recording must start and end at the verified physical dock.")
    stages = {row["stage"] for row in rows}
    if not {"VERTICAL_TAKEOFF", "MANUAL_FLIGHT", "RETURN_TO_DOCK"} <= stages:
        raise ValueError("The recording does not contain the takeoff, manual flight and return phases.")
    raw = raw_knots(rows)
    raw_stamps = [k.time for k in raw]
    knots = with_inspections(raw,manifest["locations"])
    keep = simplify(knots,network,zones,rows)
    points = np.array([p.xyz for p in knots])
    nodes, edges, bindings = [],[],[]
    approach = "OUTBOUND"
    for index, j in enumerate(keep):
        item = knots[j]
        stage, phase = item.phase
        if stage in {"RETURN_TO_DOCK","LAND","DOCKING"}:
            approach = "RETURN"
        turning = index and abs(angle(yaw(item.quaternion)-nodes[-1]["yaw_rad"]))>.12
        kind = ("DOCK" if index in (0,len(keep)-1) else "INSPECTION" if item.locations else
                "TAKEOFF" if stage=="VERTICAL_TAKEOFF" else "LANDING" if phase=="DOCKING" else
                "TURN" if turning else "RETURN" if approach=="RETURN" else "TRANSIT")
        node = {"id":f"W{index:04d}", "type":kind, "position_m":item.xyz.tolist(),
                "orientation_xyzw":item.quaternion, "yaw_rad":yaw(item.quaternion), "stamp_ns":item.time,
                "phase":phase, "leg":approach, "raw_bracket":list(item.raw),
                "record_ids":[r["record_id"] for r in item.locations]}
        nodes.append(node)
        for location in item.locations:
            bindings.append({"record_id":location["record_id"],"storage_location_id":location["storage_location_id"],
                             "node":node["id"],"stamp_ns":item.time,"raw_bracket":list(item.raw),
                             "location_revision":manifest["revision"],"orientation_xyzw":item.quaternion})
        if not index:
            continue
        i = keep[index-1]
        a,b = knots[i].xyz,item.xyz
        length, _, _ = deviation(points,i,j)
        measured = [sample.xyz for sample in raw[bisect_left(raw_stamps,knots[i].time):bisect_right(raw_stamps,item.time)]]
        comparison = np.array([a,*measured,b])
        errors = deviation(comparison,0,len(comparison)-1)[1]
        merged = j>i+1
        if not network.allows(a,b,zones):
            raise ValueError(f"Route segment {index-1} leaves the approved flight volume.")
        edges.append({"from":nodes[-2]["id"],"to":node["id"],"length_m":length,
                      "direction_xyz":((b-a)/length).tolist() if length>1.e-8 else [0.,0.,0.],
                      "raw_span":[knots[i].raw[0],item.raw[1]],"required_zones":required_zones(network,a,b,zones),
                      "max_deviation_m":float(errors.max()),"type":"simplified" if merged else "recorded",
                      "validation":"historical_envelope",
                      "limitations":["require_live_sweep","reverse_requires_evidence","yaw_control"]})
    model = Model(**header["energy_model"])
    return {"schema_version":FORMAT,"mapping_id":manifest["mapping_id"],"frame":FRAME,
            "location_revision":manifest["revision"],"nodes":nodes,"edges":edges,"locations":bindings,
            "flight_constraints":{"horizontal_radius_m":RADIUS,"vertical_half_height_m":HALF_HEIGHT,
                                  "boundary_margin_m":BOUNDARY_MARGIN,"reverse":"requires_separate_evidence"},
            "summary":{"raw_samples":len(rows),"waypoints":len(nodes),
                       "recorded_distance_m":sum(dist(a["position_m"],b["position_m"]) for a,b in zip(rows,rows[1:])),
                       "learned_distance_m":sum(e["length_m"] for e in edges),
                       "max_deviation_m":max(e["max_deviation_m"] for e in edges)},
            "forecast":forecast(nodes,{r["record_id"] for r in bindings},model),
            "calibration_energy":footer["energy"]}


def legacy_geometry(result, profile):
    network = Network(profile)
    path = result["trajectory"]
    knots = [Knot(i,np.array(point),None,("legacy","legacy"),(i,i)) for i,point in enumerate(path)]
    keep = simplify(knots,network,tuple(network.reservable))
    points = np.array(path)
    return {"mapping_id":result["mapping_id"], "source":"legacy_xyz", "eligible_for_approval":False,
            "limitations":["missing_sample_times","missing_orientations","missing_clearance_evidence"],
            "raw_samples":len(knots),"waypoints":len(keep),
            "recorded_distance_m":sum(dist(a,b) for a,b in zip(path,path[1:])),
            "learned_distance_m":sum(dist(path[i],path[j]) for i,j in zip(keep,keep[1:])),
            "max_deviation_m":max(float(deviation(points,i,j)[1].max()) for i,j in zip(keep,keep[1:])),
            "preview_positions":[path[i] for i in keep]}
