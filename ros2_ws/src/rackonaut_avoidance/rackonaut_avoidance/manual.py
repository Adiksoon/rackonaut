"""Limit a requested direction using the aircraft's existing swept-volume model."""

from dataclasses import dataclass, field
from math import cos, hypot, sin

import numpy as np

from .planner import HALF_HEIGHT, LOOKAHEAD, RADIUS, STENCIL, STOP_MARGIN, Sweep, braking_distance, current_airframe, sweep


ZERO = (0., 0., 0., 0.)
LINEAR_LIMIT = .40
VERTICAL_LIMIT = .28
YAW_LIMIT = .40
BOUNDARY_MARGIN = .06


def empty_sweep():
    return Sweep(None, None, np.empty((0, 3)))


@dataclass(frozen=True)
class Motion:
    velocity: tuple = ZERO
    state: str = "HOLD"
    detail: str = "Hold position"
    direction: tuple = (0., 0., 0.)
    scan: Sweep = field(default_factory=empty_sweep)
    clearance: float | None = None


def world_vector(body, yaw):
    forward, left, up = body[:3]
    return np.array((forward * cos(yaw) - left * sin(yaw), forward * sin(yaw) + left * cos(yaw), up))


def limit_request(axes, setting):
    x, y, z, yaw = axes
    length = max(1., hypot(x, y, z))
    return (x * LINEAR_LIMIT * setting / length, y * LINEAR_LIMIT * setting / length,
            z * VERTICAL_LIMIT * setting / length, yaw * YAW_LIMIT * setting)


def available_run(position, direction, allowed):
    start = (*position[:3], position[3])
    lower, upper = 0., LOOKAHEAD
    if allowed(start, (*(np.asarray(start[:3]) + upper * direction), start[3])):
        return upper
    for _ in range(8):
        reach = (lower + upper) * .5
        if allowed(start, (*(np.asarray(start[:3]) + reach * direction), start[3])):
            lower = reach
        else:
            upper = reach
    return lower


def yaw_clearance(cloud, xyz):
    # The same cylindrical footprint encloses all yaw angles of the reference drone.
    delta = cloud.hits - xyz
    near = cloud.hits[(np.linalg.norm(delta[:, :2], axis=1) <= RADIUS) & (abs(delta[:, 2]) <= HALF_HEIGHT)]
    if len(near) or len(cloud.near):
        return Sweep(0., None, near)
    observed = cloud.observed(xyz + STENCIL) | current_airframe(STENCIL)
    return Sweep(None, None if observed.all() else 0., near)


def speed_that_stops(clearance, margin, age):
    lo, hi = 0., LINEAR_LIMIT
    for _ in range(8):
        speed = (lo + hi) * .5
        if braking_distance(speed, age) - STOP_MARGIN + margin < clearance:
            lo = speed
        else:
            hi = speed
    return lo


def protect(cloud, pose, actual_body, request, now, allowed):
    if cloud is None:
        return Motion(state="FAULT", detail="Onboard LiDAR stopped advancing")
    if request == ZERO:
        return Motion()
    xyz, yaw = np.asarray(pose[:3]), pose[3]
    wanted = world_vector(request, yaw)
    moving = world_vector(actual_body, yaw)
    requested_speed, actual_speed = np.linalg.norm(wanted), np.linalg.norm(moving)
    age = now - cloud.received
    # A changed request never masks drift towards a different obstacle.
    if actual_speed > .055 and (requested_speed < .001 or np.dot(moving, wanted) < .85 * actual_speed * requested_speed):
        drift = moving / actual_speed
        check = sweep(cloud, xyz, xyz + drift * LOOKAHEAD, LOOKAHEAD)
        if check.limit <= braking_distance(actual_speed, age) or (
                available_run(pose, drift, allowed) <= braking_distance(actual_speed, age) - STOP_MARGIN + BOUNDARY_MARGIN):
            return Motion(state="BRAKING", detail="Stopping before changing direction", direction=tuple(drift),
                          scan=check, clearance=min(LOOKAHEAD, check.limit))
    direction = wanted / requested_speed if requested_speed >= .001 else np.zeros(3)
    scale = 1.
    check, clearance = empty_sweep(), None
    if requested_speed >= .001:
        check = sweep(cloud, xyz, xyz + direction * LOOKAHEAD, LOOKAHEAD)
        boundary = available_run(pose, direction, allowed)
        clearance = min(LOOKAHEAD, check.limit, boundary)
        current_speed = max(0., float(np.dot(moving, direction)))
        stop = braking_distance(current_speed, age)
        boundary_stop = stop - STOP_MARGIN + BOUNDARY_MARGIN
        if check.limit <= stop or boundary <= boundary_stop:
            reason = ("Reserved flight boundary or descent clearance" if boundary <= boundary_stop else
                      "Obstacle in swept volume" if check.hit is not None and check.hit <= stop else
                      "Insufficient observed space")
            return Motion(state="BRAKING" if actual_speed > .055 else "BLOCKED", detail=reason,
                          direction=tuple(direction), scan=check, clearance=clearance)
        speed = min(speed_that_stops(check.limit, STOP_MARGIN, age), speed_that_stops(boundary, BOUNDARY_MARGIN, age))
        scale = min(1., speed / requested_speed)
    yaw_rate = request[3]
    if yaw_rate:
        rotation = yaw_clearance(cloud, xyz)
        if rotation.limit == 0.:
            if requested_speed < .001:
                return Motion(state="BLOCKED", detail="Yaw footprint lacks verified space", scan=rotation, clearance=0.)
            yaw_rate = 0.
    velocity = (*(value * scale for value in request[:3]), yaw_rate)
    limited = scale < .995 or yaw_rate != request[3]
    return Motion(velocity, "LIMITED" if limited else "MOVING",
                  "Reduced command within verified clearance" if limited else "Motion permitted",
                  tuple(direction), check, clearance)
