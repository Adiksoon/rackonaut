"""Derive monitored zones from the lines the configured drone will fly."""

from math import isfinite


def overlaps(point, bounds, margin=0.):
    x, y = point[:2]
    left, bottom, right, top = bounds
    return left - margin <= x <= right + margin and bottom - margin <= y <= top + margin


def crosses(start, end, bounds):
    lower, upper = 0., 1.
    for a, b, minimum, maximum in zip(start, end, bounds[:2], bounds[2:]):
        delta = b - a
        if not delta:
            if a < minimum or a > maximum:
                return False
            continue
        entry, exit = sorted(((minimum - a) / delta, (maximum - a) / delta))
        lower, upper = max(lower, entry), min(upper, exit)
        if lower > upper:
            return False
    return True


def route_zones(points, fields):
    # A complete request includes the outbound and return legs of each
    # adaptive viewpoint. The expanded path reserves their union up front.
    if (not isinstance(points, list) or not 3 <= len(points) <= 224
            or any(not isinstance(p, list) or len(p) != 3
                   or not all(isinstance(v, (int, float)) and isfinite(v) for v in p) for p in points)):
        raise ValueError("Safety needs the complete planned flight path.")
    zones = [key for key, bounds in fields.items()
             if any(crosses(a, b, bounds) for a, b in zip(points, points[1:]))]
    if "T" not in zones or not any(key in zones for key in ("A", "B")):
        raise ValueError("The planned route must pass through the apron and an inspection aisle.")
    return zones
