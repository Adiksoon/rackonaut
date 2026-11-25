"""Create routes from published camera viewpoints and the front transfer corridor."""

from itertools import groupby
from math import dist


def selection_list(selection, key, choices):
    values = selection.get(key, [])
    if not isinstance(values, list) or any(not isinstance(item, str) or item not in choices for item in values):
        raise ValueError(f"Select supported {key} on the warehouse map.")
    return set(values)


def plan(layout, selection):
    mode = selection.get("mode")
    quality = selection.get("quality", False)
    if not isinstance(quality, bool):
        raise ValueError("Quality inspection must be enabled or disabled.")
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
    return {"mode": mode, "quality": quality, "slots": ordered, "points": points, "route": route,
            "distance": round(sum(dist(first, second) for first, second in zip(points, points[1:])), 1)}
