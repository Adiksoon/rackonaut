"""Directed execution and energy estimates for an approved calibration graph."""

from dataclasses import dataclass
from math import atan2, cos, dist, hypot, isfinite, sin
import re


TRANSIT = "LEARNED_TRANSIT"
VIEW = "LEARNED_INSPECTION"
LAND = "LEARNED_LAND"
STAGES = {TRANSIT, VIEW, LAND}
SLOT = re.compile(r"[A-Z]-[0-9]{2}-[0-9]{2}")
WAREHOUSE = re.compile(r"WH-[0-9A-F]{32}")
SHA = re.compile(r"[0-9a-f]{64}")
MAX_POSE_ERROR = .057
INSPECTION_HOLD = 3.


@dataclass(frozen=True)
class Learned:
    configuration_id: str
    revision: int
    approval_sha256: str
    node_ids: tuple


def check_metadata(metadata):
    if (not isinstance(metadata, dict) or not WAREHOUSE.fullmatch(str(metadata.get("configuration_id")))
            or not SHA.fullmatch(str(metadata.get("approval_sha256"))) or type(metadata.get("revision")) is not int
            or metadata["revision"] <= 0):
        raise ValueError("The learned route must identify an approved warehouse revision.")


def xyz_in_gate(point, bounds):
    return bounds[0] <= point[0] <= bounds[2] and bounds[1] <= point[1] <= bounds[3]


def ordered_targets(graph, selected, network):
    """Preserve the measured order, including bypassed inspection stops."""
    nodes, edges = graph["nodes"], graph["edges"]
    if not 3 <= len(nodes) <= 512 or len(edges) != len(nodes)-1:
        raise ValueError("The directed warehouse route cannot be reserved by Safety.")
    if (nodes[0]["type"] != "DOCK" or nodes[-1]["type"] != "DOCK"
            or len({node["id"] for node in nodes}) != len(nodes)):
        raise ValueError("The learned path needs a distinct start and end at the dock.")
    points = [node["position_m"] for node in nodes]
    for point in points:
        if (len(point) != 3 or any(type(v) not in (float, int) or not isfinite(v) for v in point)
                or point[2] < 0):
            raise ValueError("A learned waypoint must contain a finite airborne or dock pose.")
    allocated = network.required(points)
    by_node = {}
    for binding in graph["locations"]:
        if binding["record_id"] in selected:
            slot = binding["storage_location_id"]
            if not SLOT.fullmatch(slot) or by_node.get(binding["node"]) or slot in by_node.values():
                raise ValueError("Selected inspections require distinct inventory slots and viewpoints.")
            by_node[binding["node"]] = slot
    if len(by_node) != len(selected):
        raise ValueError("Select locations from the approved revision.")
    targets = []
    height = network.nodes["shaft"][2]
    for origin, node, edge in zip(nodes, nodes[1:], edges):
        if (edge["from"] != origin["id"] or edge["to"] != node["id"]
                or edge["validation"] != "historical_envelope"
                or not set(edge["required_zones"]) <= set(allocated)
                or not network.allows(origin["position_m"], node["position_m"], edge["required_zones"])
                or origin["stamp_ns"] >= node["stamp_ns"] or not isfinite(node["yaw_rad"])):
            raise ValueError("The plan contains an unapproved directed segment.")
        previous, current = origin["position_m"], node["position_m"]
        slot = by_node.get(node["id"], "")
        if slot and (node["type"] != "INSPECTION" or not xyz_in_gate(current, network.aisles[slot[0]][:2]
                                                                    + network.aisles[slot[0]][3:5])):
            raise ValueError("A learned inspection must stay in its reserved aisle.")
        descent = ""
        if previous[2] >= height-.19 > current[2]:
            descent = next((zone for zone, bounds in network.gates.items()
                            if zone in allocated and xyz_in_gate(previous, bounds) and xyz_in_gate(current, bounds)), "")
        phase = LAND if node is nodes[-1] else VIEW if slot else TRANSIT
        targets.append((node["id"], (*current, node["yaw_rad"]), slot, phase, descent))
    return targets, tuple(allocated)


def forecast(model, origin, points, stops, return_from=None):
    """Price a fly-through with separate allowance for corrections and a dock hold."""
    seconds, used, climb, distance = 0., 0., 0., 0.
    costs = []
    previous = origin
    for point in points:
        dx, dy, dz = (b-a for a, b in zip(previous[:3], point[:3]))
        turn = abs(atan2(sin(point[3]-previous[3]), cos(point[3]-previous[3])))
        along = hypot(dx, dy)
        pace = max(along/.48, abs(dz)/.37, turn/.31)
        correction = pace * .12 + .16
        used += model.draw(along/pace, 0., dz/pace, True)*pace if pace else 0.
        used += model.hover*correction
        costs.append(used)
        seconds += pace+correction
        distance += dist(previous[:3], point[:3])
        climb += max(0., dz)
        previous = point
    dwell = INSPECTION_HOLD*stops + .85
    total = used + model.hover*dwell
    return {"seconds": seconds+dwell, "percent": total, "climb_m": climb, "distance_m": distance,
            "return_percent": total if return_from is None else used-costs[return_from]+model.hover*.85,
            "reserve_percent": model.reserve, "required_percent": total+model.reserve}


def straight_continuation(pose, target, following):
    """Check that a short live look-ahead still crosses the current vertex."""
    first = [b-a for a, b in zip(pose[:3], target[:3])]
    next_leg = [b-a for a, b in zip(target[:3], following[:3])]
    first_length = dist(pose[:3], target[:3])
    next_length = dist(target[:3], following[:3])
    if first_length < .025 or next_length < .11:
        return False
    if sum(a*b for a, b in zip(first, next_leg)) < .98*first_length*next_length:
        return False
    ratio = first_length/(first_length+next_length)
    on_line = [a+ratio*(b-a) for a, b in zip(pose[:3], following[:3])]
    return dist(on_line, target[:3]) <= .025


def observed_prefix(pose, goal, unknown_at):
    """Return a point with stopping room inside the visible part of the active leg."""
    length = dist(pose[:3], goal[:3])
    if unknown_at is None or unknown_at < .15 or length <= unknown_at:
        return None
    fraction = min(.13, unknown_at / 2.) / length
    point = tuple(start + fraction * (end-start) for start, end in zip(pose[:3], goal[:3]))
    return (*point, goal[3])
