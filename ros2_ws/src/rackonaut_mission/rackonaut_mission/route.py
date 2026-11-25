"""Fixed route in odometry coordinates and bounded body-frame commands."""

import json
import re
from dataclasses import dataclass, replace
from math import atan2, cos, hypot, isfinite, radians, sin
from pathlib import Path


@dataclass(frozen=True)
class Target:
    x: float
    y: float
    z: float
    yaw: float
    slot_id: str = ""


@dataclass(frozen=True)
class Route:
    pad: Target
    takeoff: Target
    stops: tuple[Target, ...]


def load_route(path):
    def target(x, y, z, yaw_deg, slot_id=""):
        if not all(isfinite(value) for value in (x, y, z, yaw_deg)) or z < 0:
            raise ValueError("Route poses must be finite, with z at or above the floor.")
        return Target(float(x), float(y), float(z), radians(yaw_deg), slot_id)

    config = json.loads(Path(path).read_text())
    pad = target(**config["pad"])
    height = config["takeoff_z"]
    stops = tuple(target(**item) for item in config["waypoints"])
    if pad.slot_id or not isfinite(height) or height <= pad.z:
        raise ValueError("The takeoff altitude must be above the pad.")
    if not stops or any(not re.fullmatch(r"[A-Z]-[0-9]{2}-[0-9]{2}", stop.slot_id) for stop in stops):
        raise ValueError("Each inspection waypoint requires a valid slot_id.")
    if len({stop.slot_id for stop in stops}) != len(stops):
        raise ValueError("An inspection route must list each slot at most once.")
    if any(stop.z <= pad.z for stop in stops):
        raise ValueError("Inspection waypoints must be above the pad altitude.")
    return Route(pad, replace(pad, z=float(height)), stops)


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
