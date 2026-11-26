"""Transform real GPU lidar returns using the calibrated fixed mounts."""

from dataclasses import dataclass, field
from functools import lru_cache
from math import cos, isfinite, isnan, sin

from .geometry import overlaps

MIN_ADJACENT = 3
MAX_MAP_RETURNS = 120
MAX_MAP_HITS = 96


@lru_cache(maxsize=12)
def directions(start, step, count):
    return [(cos(start + i * step), sin(start + i * step)) for i in range(count)]


def spread(items, limit):
    if len(items) <= limit:
        return items
    return [items[i * (len(items) - 1) // (limit - 1)] for i in range(limit)]


def scan_points(scan, config):
    """Return finite endpoints and in-field clusters with adjacent support."""
    x, y, _, yaw = config["pose"]
    vectors = directions(yaw + scan.angle_min, scan.angle_increment, len(scan.ranges))
    points, hits, run = [], [], []

    def finish_run():
        if len(run) >= MIN_ADJACENT:
            hits.extend(run)
        run.clear()

    for distance, (dx, dy) in zip(scan.ranges, vectors):
        inside = False
        if isfinite(distance) and scan.range_min <= distance <= scan.range_max:
            raw = (x + distance * dx, y + distance * dy)
            point = (round(raw[0], 3), round(raw[1], 3))
            points.append(point)
            inside = overlaps(raw, config["field"])
            if inside:
                run.append(point)
        if not inside:
            finish_run()
    finish_run()
    return spread(points, MAX_MAP_RETURNS), spread(hits, MAX_MAP_HITS)


@dataclass
class Reading:
    stamp: tuple | None = None
    at: float = -1e6
    points: list = field(default_factory=list)
    hits: list = field(default_factory=list)
    occupied_since_ns: int | None = None


class LaserPresence:
    def __init__(self, configs, timeout):
        self.configs = configs
        self.timeout = timeout
        self.readings = {zone: Reading() for zone in configs}

    def accept(self, zone, message, now, detected_clock):
        reading = self.readings[zone]
        config = self.configs[zone]
        stamp = (message.header.stamp.sec, message.header.stamp.nanosec)
        angle_span = message.angle_max - message.angle_min
        arc_min, arc_max = config["arc"]
        if (message.header.frame_id != config["frame"]
                or reading.stamp is not None and stamp <= reading.stamp
                or len(message.ranges) != config["samples"]
                or not all(isfinite(v) for v in (message.angle_min, angle_span, message.angle_increment,
                                                 message.range_min, message.range_max))
                or abs(message.angle_min - arc_min) > .01 or abs(message.angle_max - arc_max) > .01
                or abs(message.angle_increment * (len(message.ranges) - 1) - angle_span) > .01
                or not 0 < message.range_min < message.range_max
                or sum(isnan(distance) for distance in message.ranges) > len(message.ranges) // 20):
            return
        points, hits = scan_points(message, config)
        previously_occupied = reading.occupied_since_ns if self.health(zone, now) == "FRESH" else None
        reading.stamp, reading.at = stamp, now
        reading.points, reading.hits = points, hits
        reading.occupied_since_ns = (previously_occupied or detected_clock()) if hits else None

    def health(self, zone, now):
        reading = self.readings[zone]
        if reading.stamp is None:
            return "UNKNOWN"
        return "FRESH" if now - reading.at <= self.timeout else "STALE"

    def occupied(self, now):
        return [zone for zone, reading in self.readings.items() if reading.hits and self.health(zone, now) == "FRESH"]

    def map_data(self, now):
        for zone, reading in self.readings.items():
            fresh = self.health(zone, now) == "FRESH"
            yield zone, {
                "age_ms": round((now - reading.at) * 1000) if reading.stamp is not None else None,
                "points": reading.points if fresh else [],
                "hits": reading.hits if fresh else [],
            }
