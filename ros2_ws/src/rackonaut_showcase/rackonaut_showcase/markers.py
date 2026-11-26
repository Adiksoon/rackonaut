"""Lightweight markers based on the installed floor plan and live state."""

from itertools import product
from math import cos, pi, sin

from geometry_msgs.msg import Point
from visualization_msgs.msg import Marker, MarkerArray

FRAME = "rackonaut_odom"
BODY = "rackonaut_base_link"
CYAN = (.27, .83, .98, 1.)
GOLD = (1., .72, .24, 1.)
VIOLET = (.77, .57, 1., 1.)
ROSE = (1., .37, .57, 1.)
WHITE = (.88, .95, 1., 1.)


def marker(ns, number, kind, point=(0., 0., 0.), scale=(1., 1., 1.), color=WHITE, *, text="", frame=FRAME):
    item = Marker()
    item.header.frame_id = frame
    item.frame_locked = frame == BODY
    item.ns, item.id, item.type, item.text = ns, number, kind, text
    item.pose.position = Point(x=float(point[0]), y=float(point[1]), z=float(point[2]))
    item.pose.orientation.w = 1.
    item.scale.x, item.scale.y, item.scale.z = map(float, scale)
    item.color.r, item.color.g, item.color.b, item.color.a = color
    return item


def line(ns, number, coords, width, color, *, frame=FRAME, segments=False):
    item = marker(ns, number, Marker.LINE_LIST if segments else Marker.LINE_STRIP,
                  scale=(width, 0., 0.), color=color, frame=frame)
    item.points = [Point(x=float(x), y=float(y), z=float(z)) for x, y, z, *_ in coords]
    return item


def label(ns, number, xyz, text, color=WHITE, height=.42):
    return marker(ns, number, Marker.TEXT_VIEW_FACING, xyz, (0., 0., height), color, text=text)


def box_lines(bounds, low, high):
    x1, y1, x2, y2 = bounds
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    points = []
    for z in {low, high}:
        points += [(x, y, z) for i in range(4) for x, y in (corners[i], corners[(i+1) % 4])]
    if low != high:
        points += [(x, y, z) for x, y in corners for z in (low, high)]
    return points


def infrastructure(aerial, layout):
    items = []
    for number, group in enumerate(("post", "deck", "beam")):
        points = []
        for x, y, z, width, depth, height, *_ in layout["scene"]["parts"][group]:
            bounds = (x-width/2, y-depth/2, x+width/2, y+depth/2)
            points += box_lines(bounds, z-height/2, z+height/2)
        items.append(line("Reference rack frames", number, points, .019, (.45, .58, .67, .32), segments=True))
    nodes = aerial["nodes"]
    for index, (a, b, kind) in enumerate(aerial["edges"]):
        start, end = nodes[a], nodes[b]
        low = min(start[2], end[2]) - (.57 if kind == "tunnel" else 0.)
        high = max(start[2], end[2]) + .57
        x1, x2 = sorted((start[0], end[0]))
        y1, y2 = sorted((start[1], end[1]))
        bounds = (x1-.88, y1-.88, x2+.88, y2+.88)
        items.append(line("Reference tunnel and shafts", index, box_lines(bounds, low, high),
                          .035, (.67, .55, .91, .51), segments=True))
    for index, (name, value) in enumerate((("Launch shaft / dock D", nodes["shaft"]),
                                          ("Descent A", nodes["entry_A"]), ("Descent B", nodes["entry_B"]))):
        items.append(label("Reference labels", index, (*value[:2], value[2]+.98), name, height=.46))
    x, y, z = nodes["dock"]
    items.append(marker("Reference dock", 0, Marker.CUBE, (x, y, z), (2.65, 2.1, .05), (.2, .75, .82, .58)))
    return MarkerArray(markers=items)


def aircraft():
    items = [marker("Estimated aircraft", 0, Marker.CUBE, (0., 0., 0.), (.46, .31, .13), CYAN, frame=BODY),
             marker("Estimated aircraft", 1, Marker.ARROW, (.20, 0., .08), (.77, .11, .11), GOLD, frame=BODY)]
    for number, (x, y) in enumerate(product((-.21, .21), repeat=2), 2):
        points = [(x+.095*cos(i*pi/12), y+.095*sin(i*pi/12), .035) for i in range(25)]
        items.append(line("Rotor outlines", number, points, .027, GOLD, frame=BODY))
    return MarkerArray(markers=items)


def reset(items):
    item = Marker()
    item.header.frame_id = FRAME
    item.action = Marker.DELETEALL
    return MarkerArray(markers=[item, *items])


def navigation(mission):
    items = []
    if target := mission.get("target_pose"):
        items.extend((marker("Active waypoint", 0, Marker.SPHERE, target, (.22,.22,.22), GOLD),
                      label("Active waypoint", 1, (*target[:2], target[2]+.37), mission.get("target", ""), GOLD, .27)))
    avoidance = mission.get("avoidance") or {}
    if points := avoidance.get("maneuver"):
        items.append(line("Measured bypass proposal", 0, points, .13, VIOLET))
    if hits := avoidance.get("hazard_points"):
        item = marker("Onboard obstruction returns", 0, Marker.SPHERE_LIST, scale=(.12,.12,.12), color=ROSE)
        item.points = [Point(x=x, y=y, z=z) for x, y, z in hits]
        items.append(item)
    for index, move in enumerate((mission.get("adaptive") or {}).get("moves", [])[-30:]):
        if start := move.get("from"):
            end = move.get("actual") or move.get("target")
            if end:
                items.append(line("Adaptive reposition", index, [start, end], .095, GOLD))
    if position := mission.get("position"):
        items.append(label("Live flight status", 0, (*position[:2], position[2]+.70),
                           f"{mission.get('flight_phase', mission.get('stage', ''))} · {avoidance.get('state', '—')}", WHITE, .27))
    return reset(items)


def safety(state, scanners):
    colors = {"OPEN": (.30, .80, .62, .75), "PREPARING": GOLD, "RESERVED": ROSE, "INTRUSION": (1., .22, .18, 1.),
              "FAULT": (.63, .62, .62, .85)}
    items = []
    for number, (name, zone) in enumerate(state.get("zones", {}).items()):
        x1,y1,x2,y2 = zone["bounds"]
        color = colors.get(zone["state"], WHITE)
        items.append(line("Reservation boundaries", number, box_lines(zone["bounds"], .10, .10),
                          .07, color, segments=True))
        items.append(label("Reservation status", number, ((x1+x2)/2, (y1+y2)/2, .28),
                           f"{name} · {zone['state']}", color, .42))
    laser = state.get("sensor_mode") == "laser"
    if laser:
        for number, (name, record) in enumerate(scanners.items()):
            x,y,z,_ = record["pose"]
            items.append(marker("Stationary laser positions", number, Marker.CYLINDER, (x,y,z), (.22,.22,.27), CYAN))
            items.append(label("Stationary laser status", number, (x,y,z+.45),
                               f"LiDAR {name} · {state['zones'].get(name, {}).get('sensor', 'UNKNOWN')}", CYAN, .27))
            items.append(line("Calibrated detector fields", number, box_lines(record["field"], .22, .22),
                              .047, CYAN, segments=True))
    if "phase" in state:
        source = "LASER FIELDS A/B/T · D VIRTUAL" if laser else "VIRTUAL PRESENCE · NO STATIONARY RETURNS"
        items.append(label("Safety profile", 0, (12., 9., .6), f"{source} · {state['phase']}", height=.55))
    return reset(items)


def recovery(row):
    items = []
    for index, (key, color) in enumerate((("planned", GOLD), ("flown", ROSE))):
        if points := row.get(key):
            items.append(line(f"Recovery {key}", index, points, .13, color))
    if position := (row.get("stopped") or {}).get("position"):
        items.append(marker("Recovery stop", 0, Marker.SPHERE, position, (.40,.40,.40), ROSE))
        items.append(label("Recovery stop", 1, (*position[:2], position[2]+.85),
                           f"{row.get('phase', '')}\n{row.get('cause', '')}", WHITE, .37))
    return reset(items)
