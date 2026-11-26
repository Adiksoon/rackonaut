"""Simulation-only inputs, energy integration and conservative corridor estimates."""

from dataclasses import dataclass
from math import atan2, cos, hypot, isfinite, sin


@dataclass(frozen=True)
class Model:
    hover: float = .55
    movement: float = .32
    climb: float = .80
    ground: float = .015
    charge: float = 6.0
    reserve: float = 8.0
    ready: float = 88.0

    def __post_init__(self):
        if (not all(isfinite(value) and value > 0 for value in vars(self).values())
                or self.reserve >= self.ready or self.ready > 100):
            raise ValueError("Invalid simulated energy model.")

    def draw(self, vx, vy, vz, airborne):
        return self.hover + self.movement * hypot(vx, vy) + self.climb * max(0., vz) if airborne else self.ground


def dock_path(pose, dock, height, crossing):
    """Approach along the occupied aisle to the front transfer corridor."""
    x, y, z, _ = pose
    dx, dy, _, heading = dock
    if x < crossing + .15 and abs(y - dy) < .16:
        return [(dx, dy, height, heading), dock]
    return [(crossing, y, height, heading), (crossing, dy, height, heading),
            (dx, dy, height, heading), dock]


def sortie_path(dock, height, crossing, slot):
    x, y, _, heading = dock
    return [(x, y, height, heading), (crossing, y, height, heading),
            (crossing, slot[1], height, heading), slot]


def estimate(model, origin, points, scan_seconds=0.0):
    """Percentage points and simulated seconds, using this controller's measured pace."""
    used = model.hover * scan_seconds
    seconds = scan_seconds
    for target in points:
        dx, dy, dz, turn = [b - a for a, b in zip(origin, target)]
        distance = hypot(dx, dy)
        angle = abs(atan2(sin(turn), cos(turn)))
        if distance < .02 and abs(dz) < .02 and angle < .02:
            continue
        duration = max(distance / .48, abs(dz) / .37, angle / .31) + .85
        used += model.hover * duration + model.movement * distance + model.climb * max(0, dz)
        seconds += duration
        origin = target
    return used, seconds


def first_requirement(model, dock, height, crossing, slot, scan_seconds):
    outbound = sortie_path(dock, height, crossing, slot)
    forecast, _ = estimate(model, dock, [*outbound, *dock_path(slot, dock, height, crossing)], scan_seconds)
    return forecast + model.reserve


def contact(pose, dock, speed, rotation):
    x, y, z, heading = pose
    dx, dy, dz, direction = dock
    yaw = heading - direction
    return (hypot(x - dx, y - dy) <= .09 and abs(z - dz) <= .022
            and abs(atan2(sin(yaw), cos(yaw))) <= .065 and speed <= .055 and rotation <= .09)
