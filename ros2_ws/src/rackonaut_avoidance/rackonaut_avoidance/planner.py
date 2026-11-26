"""Short measured maneuvers inside the reserved global flight envelope."""

from dataclasses import dataclass
from itertools import product
from math import ceil, dist, pi

import numpy as np

RADIUS = .48
HALF_HEIGHT = .17
LOOKAHEAD = 1.50
HOLD_LIMIT = 7.
MANEUVER_LIMIT = 48.
CAUTION_SCALE = .48
DETOUR_SCALE = .65

ANGLES = np.arange(8) * pi / 4
RING = [(r * np.cos(a), r * np.sin(a), z) for r, z in ((.42, 0.), (.29, -.14), (.29, .14))
        for a in ANGLES]
STENCIL = np.array([*RING, (.10, 0., 0.), (-.10, 0., 0.), (0., .10, .10), (0., -.10, -.10)])
NEIGHBORS = tuple(step for step in product((-1, 0, 1), repeat=3) if any(step))


def xyz(p):
    return tuple(round(float(v), 3) for v in p[:3])


def obstacle_groups(points):
    cells = {tuple(x) for x in np.floor(points / .17).astype(int)}
    groups = 0
    while cells:
        groups += 1
        pending = [cells.pop()]
        while pending:
            x, y, z = pending.pop()
            for dx, dy, dz in NEIGHBORS:
                neighbor = x+dx, y+dy, z+dz
                if neighbor in cells:
                    cells.remove(neighbor)
                    pending.append(neighbor)
    return groups


@dataclass
class Sweep:
    hit: float | None
    unknown: float | None
    points: np.ndarray

    @property
    def confirmed(self):
        return self.hit is None and self.unknown is None

    @property
    def limit(self):
        return min(value for value in (self.hit, self.unknown, float("inf")) if value is not None)


def sweep(cloud, start, target, extent, pad=False):
    """Check the leading swept volume and the observed rays that support it."""
    start, target = np.asarray(start[:3]), np.asarray(target[:3])
    delta = target - start
    length = float(np.linalg.norm(delta))
    if length < .065:
        return Sweep(None, None, np.empty((0, 3)))
    reach = min(length, extent)
    stations = np.linspace(min(.075, reach), reach, max(1, ceil(reach / .085)))
    centers = start + stations[:, None] * (delta / length)
    points = cloud.hits
    lower = np.minimum(start, centers[-1]) - [RADIUS, RADIUS, HALF_HEIGHT]
    upper = np.maximum(start, centers[-1]) + [RADIUS, RADIUS, HALF_HEIGHT]
    nearby = points[((points >= lower) & (points <= upper)).all(axis=1)]
    if pad:
        # Dock contact is the only planned intersection with the floor/landing mark.
        nearby = nearby[nearby[:, 2] > .065]
    offsets = nearby[None, :, :] - centers[:, None, :]
    intrusions = ((offsets[:, :, 0] ** 2 + offsets[:, :, 1] ** 2 <= RADIUS ** 2)
                  & (np.abs(offsets[:, :, 2]) <= HALF_HEIGHT))
    hits = np.flatnonzero(intrusions.any(axis=1))
    first_hit = float(stations[hits[0]]) if len(hits) else None
    hit_points = nearby[intrusions.any(axis=0)]
    near = cloud.near
    if len(near) and (not pad or np.any(near[:, 2] > -.45)):
        # A ray with a return inside the near limit cannot establish clearance.
        first_hit = 0.
    samples = centers[:, None, :] + STENCIL[None, :, :]
    already_here = samples - start
    occupied_by_drone = ((already_here[..., 0] ** 2 + already_here[..., 1] ** 2 < .36 ** 2)
                         & (np.abs(already_here[..., 2]) < .16))
    covered = cloud.observed(samples.reshape(-1, 3)).reshape(samples.shape[:2]) | occupied_by_drone
    if pad:
        covered |= samples[:, :, 2] <= .085
    unknown = np.flatnonzero(~covered.all(axis=1))
    return Sweep(first_hit, float(stations[unknown[0]]) if len(unknown) else None, hit_points)


@dataclass(frozen=True)
class Decision:
    target: tuple | None
    scale: float
    advance: bool = False
    fault: str = ""


class Navigator:
    def __init__(self):
        self.mode = "UNKNOWN"
        self.reason = "Waiting for live onboard lidar"
        self.goal = None
        self.stage = ""
        self.cloud = None
        self.position = None
        self.direction = (0., 0., 0.)
        self.checked_distance = 0.
        self.sweep = Sweep(None, None, np.empty((0, 3)))
        self.hold_at = None
        self.stopped_at = None
        self.attempt = None
        self.records = []
        self.target = None
        self.route = []
        self.added_energy = None
        self.detours = 0

    def reset(self, goal, stage):
        self.goal, self.stage = goal, stage
        self.hold_at = self.stopped_at = self.attempt = None
        self.target = None
        self.route = []
        self.added_energy = None
        self.detours = 0

    def set_state(self, mode, reason):
        self.mode, self.reason = mode, reason

    def fail(self, reason, mode="RECOVERY_REQUIRED"):
        self.set_state(mode, reason)
        return Decision(None, 0., fault=reason)

    def step(self, cloud, p, goal, stage, speed, now, allow_detour, allowed, budget, pad=False):
        self.cloud, self.position = cloud, p
        if goal != self.goal or stage != self.stage:
            self.reset(goal, stage)
        if cloud is None:
            return self.fail("Onboard lidar stopped advancing", "FAULT")
        target = self.target or goal
        delta = np.asarray(target[:3]) - p[:3]
        length = np.linalg.norm(delta)
        self.checked_distance = min(float(length), LOOKAHEAD)
        self.direction = xyz(delta / length) if length > .025 else (0., 0., 0.)
        self.sweep = sweep(cloud, p, target, LOOKAHEAD, pad)
        scan_delay = max(.28, .12 + now - cloud.received)
        stop_distance = .28 + scan_delay * speed + speed**2 / (2 * .80)
        if self.attempt and self.attempt.get("start") is not None:
            return self.follow(p, speed, now, stop_distance, allowed, budget)
        if self.sweep.limit > stop_distance and (
                self.hold_at is None or self.sweep.confirmed):
            self.hold_at = self.stopped_at = self.attempt = None
            if self.sweep.limit < LOOKAHEAD:
                self.set_state("CAUTION", "Limited verified distance along the active leg")
                return Decision(goal, CAUTION_SCALE, True)
            self.set_state("CLEAR", "Swept path verified by onboard lidar" if length >= .065
                           else "Holding the reached waypoint")
            return Decision(goal, 1., True)
        return self.hold(p, speed, now, allow_detour, allowed, budget)

    def hold(self, p, speed, now, allow_detour, allowed, budget):
        blocked = self.sweep.hit is not None
        if self.hold_at is None:
            self.hold_at = now
            self.attempt = {"detected": now, "blocked_at": xyz(p), "sim_detected": self.cloud.time,
                            "receipt_to_brake_ms": round((now-self.cloud.received)*1000),
                            "previous_speed": round(speed, 3), "stage": self.stage,
                            "reason": "measured obstacle" if blocked else "unobserved space"}
            self.records.append(self.attempt)
        if speed > .075 or now - self.hold_at < .22:
            self.set_state("BRAKING", "Obstacle in swept volume" if blocked else "Insufficient observed space")
            return Decision(None, 0.)
        if self.stopped_at is None:
            self.stopped_at = now
            self.attempt.update(stopped_at=xyz(p), reaction_s=round(now - self.hold_at, 3),
                                stopping_distance=round(dist(p[:3], self.attempt["blocked_at"]), 3))
        if allow_detour and self.detours < 2 and now - self.stopped_at >= .22:
            self.set_state("REPLANNING", "Checking observed offsets within the reservation")
            if decision := self.plan(p, now, allowed, budget):
                return decision
        elif not allow_detour:
            self.set_state("BLOCKED" if blocked else "UNKNOWN",
                           "The shaft or tunnel has no permitted lateral bypass")
        if now - self.hold_at > HOLD_LIMIT:
            return self.fail("Route blocked; no measured, reserved bypass or verified return path")
        return Decision(None, 0.)

    def confirmed(self, p, q, allowed):
        return allowed(p, q) and sweep(self.cloud, p, q, dist(p[:3], q[:3])).confirmed

    def plan(self, p, now, allowed, budget):
        axis = np.asarray(self.goal[:2]) - p[:2]
        length = np.linalg.norm(axis)
        if length < .68 or abs(self.goal[2] - p[2]) > .24:
            return None
        axis /= length
        for shift in ((-axis[1]*.87, axis[0]*.87, 0.), (axis[1]*.87, -axis[0]*.87, 0.), (0., 0., .78)):
            offset = tuple(p[i] + shift[i] for i in range(3)) + (p[3],)
            forward = (offset[0] + axis[0]*.38, offset[1] + axis[1]*.38, offset[2], p[3])
            if not self.confirmed(p, offset, allowed) or not self.confirmed(offset, forward, allowed):
                continue
            extra = budget(p, [offset, forward], self.goal, dist(p[:3], offset[:3]))
            if extra is None:
                continue
            self.detours += 1
            self.target, self.added_energy = offset, extra
            self.route = [p, offset]
            self.attempt.update(start=now, replan_s=round(now-self.stopped_at, 3), origin=xyz(p),
                                axis=tuple(axis), offset=shift, steps=0, reached=[], additional_percent=extra)
            self.set_state("AVOIDING", "Moving to a measured clearance offset")
            return Decision(offset, DETOUR_SCALE)
        return None

    def follow(self, p, speed, now, stop_distance, allowed, budget):
        a = self.attempt
        if now - a["start"] > MANEUVER_LIMIT or not allowed(p, self.target):
            return self.fail("Local bypass exceeded its time or reservation")
        if self.sweep.limit <= stop_distance:
            return self.fail("The selected bypass became blocked or unobserved")
        if dist(p[:3], self.target[:3]) > .074 or speed > .092:
            return Decision(self.target, DETOUR_SCALE)

        a["reached"].append(xyz(p))
        if a.get("rejoining"):
            samples = [a["origin"], *a["reached"]]
            a.update(rejoined_at=xyz(p), elapsed_s=round(now-a["detected"], 3),
                     additional_m=round(sum(dist(x, y) for x, y in zip(samples, samples[1:]))
                                        - dist(samples[0], samples[-1]), 3))
            self.attempt = self.target = self.hold_at = self.stopped_at = None
            self.set_state("CLEAR", "Nominal route restored")
            return Decision(p, 0.)

        axis = np.asarray(a["axis"])
        origin = a["origin"]
        along = float(np.dot(np.asarray(p[:2]) - origin[:2], axis))
        total = float(np.dot(np.asarray(self.goal[:2]) - origin[:2], axis))
        if a["steps"] >= 1:
            distance = min(total, along + .32)
            fraction = min(1., max(0., distance / total))
            joined = (origin[0]+distance*axis[0], origin[1]+distance*axis[1],
                      origin[2]+fraction*(self.goal[2]-origin[2]), p[3])
            if self.confirmed(p, joined, allowed) and budget(p, [joined], self.goal, 0.) is not None:
                a["rejoining"] = True
                self.target = joined
                self.route.append(joined)
                self.set_state("RETURNING_TO_ROUTE", "Rejoining the measured nominal path")
                return Decision(joined, DETOUR_SCALE)
        if a["steps"] < 5:
            for step in (.86, .60, .34):
                progress = min(step, total + .06 - along)
                if progress < .25:
                    continue
                forward = (p[0]+progress*axis[0], p[1]+progress*axis[1], self.route[1][2], p[3])
                if self.confirmed(p, forward, allowed) and budget(p, [forward], self.goal, .55) is not None:
                    a["steps"] += 1
                    self.target = forward
                    self.route.append(forward)
                    self.set_state("AVOIDING", "Advancing past the obstacle within the measured volume")
                    return Decision(forward, DETOUR_SCALE)
        return self.fail("No observed continuation around the obstacle")

    def snapshot(self, now):
        cloud = self.cloud
        nearby = np.empty((0, 3))
        if cloud is not None and self.position is not None:
            local = cloud.hits[np.linalg.norm(cloud.hits - self.position[:3], axis=1) < 4.0]
            spacing = max(1, ceil(len(local)/240))
            nearby = local[::spacing]
        obstruction = self.sweep.points if cloud else np.empty((0, 3))
        clearance = (float(np.linalg.norm(obstruction - self.position[:3], axis=1).min())
                     if len(obstruction) else None)
        return {"state": self.mode, "reason": self.reason, "direction": self.direction,
                "scan_age_ms": round((now-cloud.received)*1000) if cloud else None,
                "scan_stamp": round(cloud.time, 3) if cloud else None, "origin": xyz(cloud.origin) if cloud else None,
                "obstacle_distance": round(clearance, 3) if clearance is not None else None,
                "obstacle_returns": len(obstruction), "obstacles": obstacle_groups(obstruction),
                "verified_distance": round(min(self.sweep.limit, self.checked_distance), 3) if cloud else 0.,
                "point_cloud": [xyz(point) for point in nearby],
                "hazard_points": [xyz(point) for point in obstruction[::max(1, ceil(len(obstruction)/60))]],
                "maneuver": [xyz(point) for point in self.route], "extra_percent": self.added_energy,
                "extra_distance": self.records[-1].get("additional_m") if self.records else None,
                "events": self.records}
