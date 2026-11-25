"""Fixed route in odometry coordinates and bounded body-frame commands."""

import json
import re
from dataclasses import dataclass, field, replace
from math import atan2, cos, hypot, isfinite, radians, sin
from pathlib import Path


@dataclass(frozen=True)
class Target:
    x: float
    y: float
    z: float
    yaw: float
    slot_id: str = ""

    def inside(self, bounds, margin=0.):
        x1, y1, x2, y2 = bounds
        return x1 - margin <= self.x <= x2 + margin and y1 - margin <= self.y <= y2 + margin


@dataclass(frozen=True)
class RetryViews:
    zone: str
    bounds: tuple
    views: dict


@dataclass(frozen=True)
class Route:
    pad: Target
    takeoff: Target
    waypoints: tuple[Target, ...]
    retries: dict[str, RetryViews] = field(default_factory=dict)
    crossing: float | None = None
    zones: tuple[str, ...] = ()

    @property
    def stops(self):
        return tuple(point for point in self.waypoints if point.slot_id)


def load_route(path):
    def target(x, y, z, yaw_deg, slot_id=""):
        if not all(isfinite(value) for value in (x, y, z, yaw_deg)) or z < 0:
            raise ValueError("Route poses must be finite, with z at or above the floor.")
        return Target(float(x), float(y), float(z), radians(yaw_deg), slot_id)

    config = json.loads(Path(path).read_text())
    pad = target(**config["pad"])
    height = config["takeoff_z"]
    waypoints = tuple(target(**item) for item in config["waypoints"])
    stops = tuple(point for point in waypoints if point.slot_id)
    if pad.slot_id or not isfinite(height) or height <= pad.z:
        raise ValueError("The takeoff altitude must be above the pad.")
    if not stops or any(not re.fullmatch(r"[A-Z]-[0-9]{2}-[0-9]{2}", stop.slot_id) for stop in stops):
        raise ValueError("Each inspection waypoint requires a valid slot_id.")
    if len({stop.slot_id for stop in stops}) != len(stops):
        raise ValueError("An inspection route must list each slot at most once.")
    if any(point.z <= pad.z for point in waypoints):
        raise ValueError("Waypoints must be above the pad altitude.")
    retries = {}
    configured = config.get("retries", {})
    if configured and set(configured) != {stop.slot_id for stop in stops}:
        raise ValueError("Adaptive viewpoints must match the planned locations.")
    for stop in stops:
        if stop.slot_id not in configured:
            continue
        entry = configured[stop.slot_id]
        bounds = tuple(entry["bounds"])
        if (len(bounds) != 4 or not all(map(isfinite, bounds)) or not stop.inside(bounds)
                or entry["zone"] != stop.slot_id[0]):
            raise ValueError(f"Invalid adaptive envelope for {stop.slot_id}.")
        views = {}
        for reason, rows in entry["views"].items():
            poses = tuple(target(**row) for row in rows)
            if (reason not in {"missing", "uncertain", "unreadable", "damage"} or len(poses) > 2
                    or any(p.slot_id != stop.slot_id or not p.inside(bounds)
                           or not .62 <= p.z <= 3.18
                           or hypot(p.x - stop.x, p.y - stop.y) > .75
                           or abs(p.z - stop.z) > .18 or abs(heading_error(p.yaw, stop.yaw)) > .35
                           for p in poses)):
                raise ValueError(f"Unsafe adaptive viewpoint for {stop.slot_id}.")
            views[reason] = poses
        retries[stop.slot_id] = RetryViews(entry["zone"], bounds, views)
    crossing = config.get("energy_crossing_x")
    zones = tuple(config.get("energy_zones", ()))
    if crossing is not None and (not isfinite(crossing) or "T" not in zones
                                 or any(stop.slot_id[0] not in zones for stop in stops)):
        raise ValueError("Energy route requires the reserved transfer corridor and inspection aisles.")
    return Route(pad, replace(pad, z=float(height)), waypoints, retries, crossing, zones)


def heading_error(target, actual):
    return atan2(sin(target - actual), cos(target - actual))


def velocity(target, pose):
    """Return body x/y/z in m/s and yaw rate in rad/s."""
    dx, dy = target.x - pose.x, target.y - pose.y
    gain = min(1.25, .56 / max(hypot(dx, dy), 1e-6))
    c, s = cos(pose.yaw), sin(pose.yaw)
    return (
        gain * (c * dx + s * dy),
        gain * (-s * dx + c * dy),
        max(-.50, min(.50, 1.35 * (target.z - pose.z))),
        max(-.47, min(.47, 1.6 * heading_error(target.yaw, pose.yaw))),
    )
