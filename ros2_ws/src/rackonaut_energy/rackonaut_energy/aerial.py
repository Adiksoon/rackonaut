"""Shared corridor graph and continuous segment validation for the aerial showcase."""

from collections import deque
from dataclasses import dataclass
from math import dist, isfinite


def interval(start, end, box):
    lower, upper = 0., 1.
    for a, b, minimum, maximum in zip(start[:3], end[:3], box[:3], box[3:]):
        delta = b - a
        if abs(delta) <= 1e-9:
            if not minimum <= a <= maximum:
                return None
            continue
        enter, leave = sorted(((minimum - a) / delta, (maximum - a) / delta))
        lower, upper = max(lower, enter), min(upper, leave)
        if lower > upper:
            return None
    return lower, upper


def segment_inside(start, end, volumes):
    # Intervals span the entire segment, including the joins between boxes.
    intervals = sorted(hit for box in volumes if (hit := interval(start, end, box)) is not None)
    covered = 0.
    for begin, finish in intervals:
        if begin > covered + 1e-7:
            return False
        covered = max(covered, finish)
        if covered >= 1. - 1e-7:
            return True
    return False


@dataclass(frozen=True)
class Leg:
    pose: tuple
    phase: str
    gate: str = ""


class Network:
    def __init__(self, profile):
        self.nodes = {name: (*point, 0.) for name, point in profile["nodes"].items()}
        self.aisles = profile["inspection_volumes"]
        self.gates = profile["gates"]
        self.connections = {name: [] for name in self.nodes}
        self.edges = []
        for a, b, kind in profile["edges"]:
            self.connections[a].append((b, kind))
            self.connections[b].append((a, kind))
            low = [min(x, y) - .33 for x, y in zip(self.nodes[a][:3], self.nodes[b][:3])]
            high = [max(x, y) + .33 for x, y in zip(self.nodes[a][:3], self.nodes[b][:3])]
            self.edges.append((a, b, kind, [*low, *high]))
        self.protected = [box for _, _, kind, box in self.edges if kind == "tunnel"]
        self.reservable = {"D": [], **{name: [box] for name, box in self.aisles.items()}}
        for _, _, kind, box in self.edges:
            if kind != "tunnel":
                self.reservable["D" if kind == "shaft" else kind].append(box)

    def volumes(self, zones):
        return [*self.protected, *(box for zone in zones for box in self.reservable[zone])]

    def allows(self, a, b, zones):
        return segment_inside(a, b, self.volumes(zones))

    def required(self, path):
        if (not isinstance(path, list) or not 3 <= len(path) <= 512
                or any(not isinstance(p, list) or len(p) != 3
                       or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v) for v in p)
                       for p in path)):
            raise ValueError("Aerial safety requires a complete three-dimensional flight plan.")
        if dist(path[0], self.nodes["dock"][:3]) > .02 or dist(path[-1], self.nodes["dock"][:3]) > .02:
            raise ValueError("Aerial plans must start and end at the technical dock.")
        pairs = list(zip(path, path[1:]))
        if any(not self.allows(a, b, self.reservable) for a, b in pairs):
            raise ValueError("A planned segment leaves the aerial flight envelope.")
        zones = [zone for zone, boxes in self.reservable.items()
                 if any((hit := interval(a, b, box)) is not None and hit[1] - hit[0] > 1e-5
                        for a, b in pairs for box in boxes)]
        if "D" not in zones or not set(zones) & self.aisles.keys():
            raise ValueError("Aero mission must use the shaft and an inspection aisle.")
        return zones

    @staticmethod
    def phase(start, end, kind):
        if kind == "shaft":
            return ("VERTICAL_TAKEOFF" if start == "dock" else "DOCKING"), ""
        if kind == "tunnel":
            return ("ENTERING_CORRIDOR" if start == "shaft" else "OVERHEAD_TRANSIT"), ""
        return ("AISLE_DESCENT" if end.startswith("foot_") else "AISLE_ASCENT"), kind

    def path(self, source, target, *, returning=False):
        if source == target:
            return []
        queue = deque([(source, [])])
        seen = {source}
        while queue:
            name, route = queue.popleft()
            for next_name, kind in self.connections[name]:
                if next_name in seen:
                    continue
                seen.add(next_name)
                phase, gate = self.phase(name, next_name, kind)
                if returning and kind == "tunnel":
                    phase = "RETURN_TRANSIT"
                candidate = [*route, Leg(self.nodes[next_name], phase, gate)]
                if next_name == target:
                    return candidate
                queue.append((next_name, candidate))
        raise ValueError(f"No aerial route from {source} to {target}.")

    def sortie(self, slot_pose, zone):
        return [*self.path("dock", f"foot_{zone}"), Leg(tuple(slot_pose), "TRANSIT", zone)]

    def home(self, position, zones):
        candidates = set()
        for zone in zones:
            if zone in self.aisles and interval(position, position, self.aisles[zone]):
                candidates.add(f"foot_{zone}")
        for a, b, kind, box in self.edges:
            if (kind == "tunnel" or ("D" if kind == "shaft" else kind) in zones) and interval(position, position, box):
                candidates.update((a, b))
        routes = []
        for name in sorted(candidates):
            prefix = []
            if dist(position[:3], self.nodes[name][:3]) > .025:
                zone = name[-1] if name.startswith("foot_") else ""
                phase = "AISLE_ASCENT" if any(
                    gate in zones and name == f"entry_{gate}" and position[2] < self.nodes[name][2] - .33
                    for gate in self.aisles
                ) else "RETURN_TRANSIT"
                prefix = [Leg(self.nodes[name], phase, zone)]
            route = [*prefix, *self.path(name, "dock", returning=True)]
            if not route:
                return []
            points = [position, *(leg.pose for leg in route)]
            if all(self.allows(a, b, zones) for a, b in zip(points, points[1:])):
                length = sum(dist(a[:3], b[:3]) for a, b in zip(points, points[1:]))
                routes.append((length, route))
        if not routes:
            raise ValueError("Aerial position has no connected safe return.")
        return min(routes, key=lambda pair: pair[0])[1]
