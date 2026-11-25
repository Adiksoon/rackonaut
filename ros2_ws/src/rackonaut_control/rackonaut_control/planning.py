"""Create routes from published camera viewpoints and the front transfer corridor."""

from itertools import groupby
from math import dist, radians

from rackonaut_energy.model import Model, dock_path, estimate, first_requirement


RETRY_OFFSETS = {
    "unreadable": ((.55, .18, .03, 13.), (-.46, .28, .04, -10.)),
    "uncertain": ((-.38, .08, .10, -9.), (.46, .22, .12, 11.)),
    "missing": ((.32, .04, .12, 9.), (-.34, .12, -.08, -8.)),
    # The reference camera needs both the left-hand slot tag and the whole carton.
    "damage": ((0., .14, 0., 0.),),
}


def retry_views(layout, slot, original):
    location = layout["slots"][slot]
    aisle = location["aisle"]
    left, bottom, right, top = layout["safety_fields"][aisle]
    face = location["label"][1]
    centre = location["label"][0] + .66
    bounds = [max(left + .4, centre - 1.12), bottom + .4,
              min(right - .4, centre + 1.12), min(top - .4, face - 1.40)]
    if layout.get("laser_fields"):
        a, b, c, d = layout["laser_fields"][aisle]["field"]
        bounds = [max(bounds[0], a + .30), max(bounds[1], b + .30),
                  min(bounds[2], c - .30), min(bounds[3], d - .30)]
    x, y, z, yaw = location["viewpoint"]
    views = {}
    for reason, offsets in RETRY_OFFSETS.items():
        poses = []
        for dx, dy, dz, angle in offsets:
            target = dict(x=round(x + dx, 3), y=round(y + dy, 3),
                          z=round(z + dz, 3), yaw_deg=yaw + angle, slot_id=slot)
            if (bounds[0] <= target["x"] <= bounds[2] and bounds[1] <= target["y"] <= bounds[3]
                    and .62 <= target["z"] <= 3.18):
                poses.append(target)
        views[reason] = poses
    if not (bounds[0] <= original["x"] <= bounds[2] and bounds[1] <= original["y"] <= bounds[3]):
        raise ValueError(f"The reference viewpoint for {slot} is outside the adaptive flight envelope.")
    return {"zone": aisle, "bounds": bounds, "views": views}


def selection_list(selection, key, choices):
    values = selection.get(key, [])
    if not isinstance(values, list) or any(not isinstance(item, str) or item not in choices for item in values):
        raise ValueError(f"Select supported {key} on the warehouse map.")
    return set(values)


def plan(layout, selection):
    mode = selection.get("mode")
    quality = selection.get("quality", False)
    adaptive = selection.get("adaptive", False)
    if not isinstance(quality, bool):
        raise ValueError("Quality inspection must be enabled or disabled.")
    if not isinstance(adaptive, bool) or (adaptive and not layout.get("adaptive_world")):
        raise ValueError("Adaptive inspection requires the adaptive warehouse profile.")
    slots = layout["slots"]
    if mode == "full":
        ids = set(slots)
    elif mode == "aisle":
        aisles = {row["id"] for row in layout["aisles"] if row["functional"]}
        selected = selection_list(selection, "aisles", aisles)
        ids = {slot for slot, item in slots.items() if item["aisle"] in selected}
    elif mode == "custom":
        ids = selection_list(selection, "slots", slots)
    else:
        raise ValueError("Select full inventory, an aisle, or individual locations.")
    if not ids:
        raise ValueError("Select at least one inspection location.")

    ordered = sorted(ids, key=lambda slot: (slots[slot]["aisle"], slots[slot]["bay"], slots[slot]["level"]))
    pad = {key: layout["pad"][key] for key in ("x", "y", "z", "yaw_deg")}
    height = layout["takeoff_z"]
    crossing = layout["crossing_x"]
    waypoints = []

    def transfer(y):
        point = {"x": crossing, "y": y, "z": height, "yaw_deg": 0.}
        if not waypoints or waypoints[-1] != point:
            waypoints.append(point)

    previous_y = pad["y"]
    for _, group in groupby(ordered, key=lambda slot: slots[slot]["aisle"]):
        sequence = list(group)
        transfer(previous_y)
        transfer(slots[sequence[0]]["viewpoint"][1])
        for slot in sequence:
            x, y, z, yaw = slots[slot]["viewpoint"]
            waypoints.append({"x": x, "y": y, "z": z, "yaw_deg": yaw, "slot_id": slot})
            previous_y = y
    transfer(previous_y)
    transfer(pad["y"])
    route = {"pad": pad, "takeoff_z": height, "waypoints": waypoints}
    takeoff = {**pad, "z": height}
    points = [[point[axis] for axis in ("x", "y", "z")] for point in (pad, takeoff, *waypoints, takeoff, pad)]
    result = {"mode": mode, "quality": quality, "adaptive": adaptive, "slots": ordered, "points": points, "route": route,
              "distance": round(sum(dist(first, second) for first, second in zip(points, points[1:])), 1)}
    if adaptive:
        route["retries"] = retries = {}
        safety_path = []
        for stop, point in zip((pad, takeoff, *waypoints, takeoff, pad), points):
            safety_path.append(point)
            slot = stop.get("slot_id")
            if slot:
                retries[slot] = retry_views(layout, slot, stop)
                for poses in retries[slot]["views"].values():
                    for pose in poses:
                        safety_path.extend(([pose["x"], pose["y"], pose["z"]], point))
        result["safety_points"] = safety_path
    return result


def energy_forecast(layout, route, telemetry):
    model = Model(**telemetry["model"])
    def pose(row):
        return row["x"], row["y"], row["z"], radians(row["yaw_deg"])

    dock = pose(route["route"]["pad"])
    height, crossing = layout["takeoff_z"], layout["crossing_x"]
    stops = route["route"]["waypoints"]
    slots = [pose(row) for row in stops if row.get("slot_id")]
    inspection = len(slots) * (3.2 if route["quality"] else 2.0)
    travel = [(dock[0], dock[1], height, dock[3]), *(pose(row) for row in stops),
              (dock[0], dock[1], height, dock[3]), dock]
    use, duration = estimate(model, dock, travel, inspection)
    optional = retries = 0.
    views = route["route"].get("retries", {})
    for row in stops:
        slot = row.get("slot_id")
        if slot not in views:
            continue
        nominal = pose(row)
        candidates = [estimate(model, nominal, [pose(alt), nominal], 4.0)
                      for group in views[slot]["views"].values() for alt in group]
        for value, seconds in sorted(candidates, reverse=True)[:2]:
            optional += value
            retries += seconds
    minimum = first_requirement(model, dock, height, crossing, slots[0], 4.)
    returning, _ = estimate(model, slots[-1], dock_path(slots[-1], dock, height, crossing))
    level = telemetry["percent"]
    return {"flight_seconds": round(duration - inspection, 1), "inspection_seconds": round(inspection, 1),
            "adaptive_seconds": round(retries, 1), "adaptive_percent": round(optional, 2),
            "estimated_percent": round(use, 2), "return_percent": round(returning, 2),
            "reserve_percent": model.reserve, "minimum_percent": round(minimum, 2),
            "can_start": level >= minimum, "single_cycle": level >= use + optional + model.reserve}
