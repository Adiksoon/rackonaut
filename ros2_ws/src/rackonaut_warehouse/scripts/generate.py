#!/usr/bin/env python3
"""Build the Rackonaut showcase SDF and its optional ArUco placards."""

import argparse
import json
import random
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
DEPTH = 1.2
HALL_CENTER = 13.0
BLUE = (0.055, 0.20, 0.36)
ORANGE = (0.91, 0.33, 0.055)
YELLOW = (0.91, 0.64, 0.09)
CARTONS = [(0.63, 0.42, 0.23), (0.81, 0.62, 0.41), (0.52, 0.35, 0.23),
           (0.28, 0.41, 0.34), (0.67, 0.68, 0.60), (0.35, 0.46, 0.59)]
KRAFT = (0.72, 0.52, 0.32)

# The IDs match the existing backend fixture. The physical layout has two
# levels per bay. The last three cases also have a system-level dimension.
STOCK = (
    ("P001", 20, "match"), ("P003", 21, "wrong_pallet"),
    (None, None, "missing_pallet"), ("P999", 22, "unexpected_pallet"),
    ("P005", None, "unreadable_label"), ("P006", 23, "uninspected"),
    ("P007", None, "uncertain_candidate"), ("P008", 24, "repeat_final_state"),
)
CONTROL_B_STOCK = (
    ("P021", 25, "torn"),
    ("P022", 26, "intact"),
    (None, None, "empty"),
)


def numbers(values):
    return " ".join(f"{v:.5g}" for v in values)


def add(parent, tag, value=None, **attributes):
    item = ET.SubElement(parent, tag, attributes)
    item.text = str(value) if value is not None else None
    return item


def link(world, name, pose=None):
    model = add(world, "model", name=name)
    add(model, "static", "true")
    if pose:
        add(model, "pose", pose)
    return add(model, "link", name="body")


def material(visual, color, texture=None):
    surface = add(visual, "material")
    for parameter in ("ambient", "diffuse"):
        add(surface, parameter, numbers((*color, 1)))
    add(surface, "specular", "0.02 0.02 0.02 1")
    if texture:
        metal = add(add(surface, "pbr"), "metal")
        add(metal, "albedo_map", f"model://rackonaut_warehouse/materials/textures/{texture}.png")
        add(metal, "metalness", 0)
        add(metal, "roughness", 0.9)


def box(parent, name, point, size, color=None, collision=False):
    if color is not None:
        part = add(parent, "visual", name=name)
        add(part, "cast_shadows", "false")
        add(part, "pose", numbers((*point, 0, 0, 0)))
        add(add(add(part, "geometry"), "box"), "size", numbers(size))
        material(part, color)
    if collision:
        part = add(parent, "collision", name=f"{name}_collision")
        add(part, "pose", numbers((*point, 0, 0, 0)))
        add(add(add(part, "geometry"), "box"), "size", numbers(size))


def plane_label(parent, name, point, width, height, yaw=0.0, texture=None):
    visual = add(parent, "visual", name=name)
    add(visual, "pose", numbers((*point, 0, 0, yaw)))
    add(visual, "cast_shadows", "false")
    geometry = add(add(visual, "geometry"), "mesh")
    add(geometry, "uri", "model://rackonaut_warehouse/meshes/placard.obj")
    add(geometry, "scale", numbers((width, 1, height)))
    material(visual, (1, 1, 1), texture or name)


def light(world, name, kind, point, color, direction=None):
    item = add(world, "light", name=name, type=kind)
    add(item, "pose", numbers((*point, 0, 0, 0)))
    add(item, "cast_shadows", "false")
    add(item, "diffuse", numbers((*color, 1)))
    add(item, "specular", "0.07 0.07 0.07 1")
    if direction:
        add(item, "direction", numbers(direction))
    else:
        falloff = add(item, "attenuation")
        for key, value in (("range", 17), ("constant", 0.8), ("linear", 0.03), ("quadratic", 0.009)):
            add(falloff, key, value)


def world_base():
    sdf = ET.Element("sdf", version="1.8")
    world = add(sdf, "world", name="rackonaut")
    physics = add(world, "physics", name="showcase_physics", type="ignored")
    add(physics, "max_step_size", 0.004)
    add(physics, "real_time_factor", 1)
    add(world, "gravity", "0 0 -9.81")
    scene = add(world, "scene")
    add(scene, "ambient", "0.58 0.60 0.63 1")
    add(scene, "background", "0.76 0.82 0.90 1")
    for system, filename in (("Physics", "physics"), ("UserCommands", "user-commands"),
                             ("SceneBroadcaster", "scene-broadcaster"), ("Sensors", "sensors")):
        plugin = add(world, "plugin", filename=f"ignition-gazebo-{filename}-system",
                     name=f"ignition::gazebo::systems::{system}")
        if system == "Sensors":
            add(plugin, "render_engine", "ogre2")
    light(world, "diffuse_roof_light", "directional", (0, 0, 9), (.69, .68, .66), (-.24, .1, -1))
    for index, x in enumerate((1, 11.5, 22, 30)):
        light(world, f"high_bay_{index}", "point", (x, 0, 7.9), (.63, .65, .68))
    return sdf, world


def hall(world, source):
    structure = link(world, "warehouse_shell")
    box(structure, "floor", (HALL_CENTER, 0, -.12), (42, 29.5, .24),
        (.40, .42, .43) if source == "procedural" else None, collision=True)
    if source == "tevy":
        visual = add(structure, "visual", name="tevy_steel_warehouse")
        add(visual, "pose", f"{HALL_CENTER} 0 0 0 0 0")
        add(visual, "cast_shadows", "false")
        mesh = add(add(visual, "geometry"), "mesh")
        add(mesh, "uri", "model://rackonaut_warehouse/meshes/steel_warehouse_lod1.dae")
    shell_color = (.55, .58, .61) if source == "procedural" else None
    for side in (-1, 1):
        box(structure, f"side_{side}", (HALL_CENTER, side * 12.5, 4.4), (40, .18, 8.8),
            shell_color, collision=True)
        box(structure, f"end_{side}", (HALL_CENTER + side * 20, 0, 4.4), (.18, 25, 8.8),
            shell_color, collision=True)
    if source == "procedural":
        box(structure, "roof", (HALL_CENTER, 0, 8.9), (40, 25, .18), (.27, .33, .40))
        for index, x in enumerate(range(-4, 32, 5)):
            box(structure, f"rafter_{index}", (x, 0, 8.6), (.24, 24.8, .28), BLUE)
            for side in (-1, 1):
                box(structure, f"column_{index}_{side}", (x, side * 12.25, 4.35),
                    (.29, .24, 8.7), BLUE)


def paint(world, rows, aisle_width, pad=(0., 0.)):
    marks = link(world, "safety_markings_and_launch_pad")
    box(marks, "matte_concrete_top", (HALL_CENTER, 0, .007), (39.65, 24.65, .010), (.25, .27, .29))
    for joint in range(-3, 31, 5):
        box(marks, f"slab_joint_{joint}", (joint, 0, .012), (.026, 24.6, .004), (.19, .21, .23))
    for index, y in enumerate(rows):
        for side in (-1, 1):
            stripe_y = y + side * (aisle_width / 2 - .16)
            box(marks, f"line_{index}_{side}", (14.1, stripe_y, .017), (27.7, .105, .015), YELLOW)
    x, y = pad
    box(marks, "takeoff_pad", (x, y, .016), (2.65, 2.1, .021), (.03, .19, .23))
    for side in (-1, 1):
        box(marks, f"pad_border_long_{side}", (x, y + side * 1.035, .028), (2.63, .075, .015), YELLOW)
        box(marks, f"pad_border_short_{side}", (x + side * 1.29, y, .028), (.075, 2.12, .015), YELLOW)
        box(marks, f"pad_H_leg_{side}", (x + side * .29, y, .032), (.10, .65, .016), (.85, .90, .95))
    box(marks, "pad_H_crossbar", (x, y, .032), (.59, .11, .016), (.85, .90, .95))
    for x in range(4, 25, 3):
        box(marks, f"center_dash_{x}", (x, 0, .017), (.65, .055, .009), (.80, .80, .75))
    box(marks, "dock_area", (-1.5, -9.4, .017), (6.8, 3.9, .015), (.20, .28, .31))
    for index in range(8):
        box(marks, f"dock_bar_{index}", (-4.7 + index * .9, -7.38, .027), (.40, .12, .016), YELLOW)


def quality_carton(parent, key, x, y, z, shape):
    """Build the carton above the unchanged skid and behind the pallet placard."""
    def part(name, offset, size, colour):
        box(parent, f"{key}_quality_{name}", tuple(a + b for a, b in zip((x, y, z), offset)), size, colour)

    def surface(name, colour):
        visual = add(parent, "visual", name=f"{key}_quality_{name}")
        add(visual, "pose", numbers((x, y, z, 0, 0, 0)))
        add(visual, "cast_shadows", "false")
        mesh = add(add(visual, "geometry"), "mesh")
        add(mesh, "uri", f"model://rackonaut_warehouse/meshes/quality/{name}.obj")
        material(visual, colour)

    if shape == "torn":
        part("body", (0, .387, .41), (.86, .606, .82), KRAFT)
        for side in (-1, 1):
            part(f"side_{side}", (side * .418, .042, .41), (.024, .084, .82), KRAFT)
        part("lid", (0, .042, .810), (.86, .084, .02), KRAFT)
        part("cavity", (0, .074, .68), (.69, .012, .27), (.24, .125, .065))
        for index in range(3):
            part(f"corrugation_{index}", (0, .066, .612 + .048 * index), (.66, .004, .009), (.34, .19, .095))
        surface("torn-face", KRAFT)
        surface("torn-rim", (.93, .71, .45))
    elif shape == "crushed":
        surface("crushed-carton", KRAFT)
        surface("crushed-fold", (.33, .21, .125))
    else:
        part("body", (0, .345, .41), (.86, .69, .82), KRAFT)

    for side in (-1, 1):
        part(f"tape_{side}", (side * .342, -.004, .265), (.027, .008, .53), (.79, .66, .46))


def cargo(parent, key, x, y, deck, rng, detailed=False, collision=False, quality_shape=None):
    box(parent, f"{key}_skid", (x, y, deck + .075), (1.08, .84, .12), (.43, .26, .13))
    if detailed:
        for side in (-1, 0, 1):
            box(parent, f"{key}_runner_{side}", (x + side * .43, y, deck + .03),
                (.12, .84, .053), (.32, .19, .09))
    width = .86 if detailed else rng.uniform(.70, 1.05)
    height = .82 if detailed else rng.uniform(.46, .91)
    color = rng.choice(CARTONS)
    if quality_shape is not None:
        box(parent, f"{key}_load", (x, y, deck + .13 + height / 2), (width, .69, height), collision=collision)
        quality_carton(parent, key, x, y - .345, deck + .13, quality_shape)
        return
    box(parent, f"{key}_load", (x, y, deck + .13 + height / 2), (width, .69, height),
        color, collision=collision)
    if detailed or rng.random() < .30:
        tape = (.80, .72, .51) if color[0] > .49 else (.59, .68, .58)
        for side in (-1, 1):
            box(parent, f"{key}_band_{side}", (x + side * width / 3, y - .348, deck + .13 + height / 2),
                (.035, .008, height), tape)


def rack(world, index, y, args, rng, inspection, rows):
    parent = link(world, f"rack_row_{index + 1}")
    top = args.rack_height
    x_first = 5.5
    pitch = args.bay_pitch
    count = 4 if args.profile == "pilot" else args.bays
    levels = [.45 + level * (top - 1.50) / (args.levels - 1) for level in range(args.levels)]
    face = y - DEPTH / 2
    aisle_b = args.control and index == 1
    collision_row = inspection or aisle_b
    for post in range(count + 1):
        x = x_first + (post - .5) * pitch
        for edge in (-1, 1):
            box(parent, f"post_{post}_{edge}", (x, y + edge * DEPTH / 2, top / 2),
                (.12, .12, top), BLUE, collision=collision_row)
        box(parent, f"guard_{post}", (x, face - .04, .23), (.19, .18, .46), YELLOW)
    for bay in range(count):
        x = x_first + bay * pitch
        for level, deck in enumerate(levels):
            key = f"b{bay + 1}_l{level + 1}"
            box(parent, f"deck_{key}", (x, y, deck - .052), (pitch - .1, DEPTH, .105),
                ORANGE, collision=collision_row)
            box(parent, f"beam_{key}", (x, face - .025, deck - .054),
                (pitch - .15, .11, .13), ORANGE)
            local_index = bay * 2 + level
            in_scope = level < 2 and ((inspection and bay < 4) or (aisle_b and local_index < len(CONTROL_B_STOCK)))
            if not in_scope:
                for place in (-1, 1):
                    if rng.random() < args.fill:
                        cargo(parent, f"decor_{key}_{place}", x + place * .56, y, deck, rng)
                continue
            slot_index = local_index + (len(STOCK) if aisle_b else 0)
            pallet, tag, scenario = (CONTROL_B_STOCK if aisle_b else STOCK)[local_index]
            slot_id = f"B-{bay + 1:02d}-{level + 1:02d}" if aisle_b else f"A-01-{local_index + 1:02d}"
            label_x = x - .66
            box(parent, f"label_mount_{key}", (label_x, face + .035, deck + .16),
                (.61, .11, .40), BLUE)
            plane_label(parent, f"slot_{slot_index:02}", (label_x, face - .024, deck + .16), .58, .36)
            row = {"slot_id": slot_id, "physical_bay": bay + 1, "physical_level": level + 1,
                   "pallet_id": pallet, "slot_aruco_id": slot_index, "pallet_aruco_id": tag,
                   "scenario": scenario, "slot_label_xyz_m": [round(label_x, 3), round(face - .024, 3), round(deck + .16, 3)]}
            if args.control:
                row["bay_center_xyz_m"] = [round(value, 3) for value in (x, y, deck)]
                pose = [x - .04, face - 1.95, deck + .34, 90.]
                # Use the verified view of the partly obstructed A-01-07.
                if slot_id == "A-01-07":
                    pose = [13.4, -.33, .87, 90.]
                row["viewpoint"] = [round(value, 3) for value in pose]
            if pallet:
                shape = None
                if args.quality:
                    shape = scenario if aisle_b else {1: "torn", 3: "crushed"}.get(local_index, "intact")
                cargo(parent, f"inspection_{key}", x + .26, face + .47, deck, rng, detailed=True,
                      collision=True, quality_shape=shape)
                label = f"pallet_{tag}" if tag is not None else "label_unreadable"
                plane_label(parent, f"pallet_label_{key}", (x + .26, face + .115, deck + .49),
                            .55, .33, texture=label)
                if args.adaptive and slot_id == "A-01-01":
                    # A hanging placard masks the pallet tag head-on. Its setback
                    # from the label lets an offset camera see around it.
                    box(parent, "hanging_placard_a01", (x + .06, face - .72, deck + .42),
                        (.165, .045, .16), (.23, .29, .34), collision=True)
                    box(parent, "placard_stem_a01", (x + .06, face - .72, deck + .70),
                        (.025, .035, .42), BLUE)
                if scenario == "uncertain_candidate":
                    box(parent, "partially_occluded_pallet_07", (x + .43, face + .09, deck + .54),
                        (.33, .052, .64), (.34, .33, .29))
            rows.append(row)
    if not collision_row:
        first_x = x_first - pitch / 2
        last_x = x_first + (count - .5) * pitch
        box(parent, "row_collision", ((first_x + last_x) / 2, y, top / 2),
            (last_x - first_x, DEPTH, top), collision=True)


def signs(world, rows, inspection_y):
    decor = link(world, "signs_and_shipping_staging")
    plane_label(decor, "rackonaut", (1.3, inspection_y - .73, 4.3), 3.15, .87)
    for aisle, y in enumerate(rows):
        sign = 1 if len(rows) == 1 else aisle
        plane_label(decor, f"aisle_{sign}", (2.35, y, 4.55), 1.25, .48, yaw=-1.5708)
    for index, (x, y) in enumerate(((-2.4, -8.2), (-.6, -9.5), (1.1, -10.1), (3.0, -9.3))):
        cargo(decor, f"staged_{index}", x, y, .01, random.Random(index + 28), detailed=True)


def safety_posts(aisles, rack_end, aerial=None):
    entries = [(name, side, x, y + 2.03, y, yaw)
               for name, y in zip(("B", "A"), aisles)
               for side, x, yaw in (("west", 3.45, -1.5708), ("east", rack_end + .55, 1.5708))]
    entries.append(("T", "pad", -1.6, 1.55, 0., -1.5708))
    if aerial:
        dx, dy, _ = aerial["nodes"]["dock"]
        entries.append(("D", "tech", dx + 1.46, dy + .63, dy, 0.))
    return entries


SIGNAL_STACK = (
    ("foot", .065, (.40, .40, .13), (.13, .15, .17)),
    ("pole", .88, (.13, .13, 1.65), (.16, .19, .22)),
    ("housing", 2.04, (.35, .35, .72), (.055, .063, .077)),
    # The lenses are visible from either approach and in an overhead view.
    ("red", 2.27, (.39, .39, .17), (.075, .083, .09)),
    ("yellow", 2.04, (.39, .39, .17), (.075, .083, .09)),
    ("green", 1.81, (.39, .39, .17), (.075, .083, .09)),
    ("cap", 2.41, (.45, .45, .07), (.105, .12, .14)),
)


def safety_infrastructure(world, aisles, rack_end, virtual_sensor=True, dock_view=False, aerial=None):
    # The fields meet at x=3.4, before the front faces at x=4.1.
    fields = {"A": [3.4, -2.4, rack_end + 1.1, 2.4],
              "B": [3.4, -8.4, rack_end + 1.1, -3.6],
              "T": [-1.4, -8.4, 3.4, 2.4]}
    for name, side, x, y, centre, yaw in safety_posts(aisles, rack_end, aerial):
        post = link(world, f"safety_{name.lower()}_{side}")
        for part, z, size, color in SIGNAL_STACK:
            box(post, part, (x, y, z), size, color)
        if name in {"A", "B"}:
            plane_label(post, "aisle", (x, y - .56, 1.63), .88, .34,
                        yaw=yaw, texture={"A": "aisle_1", "B": "aisle_0"}[name])
            plane_label(post, "warning", (x, y - .58, 1.26), 1.05, .43, yaw=yaw, texture="safety_notice")
        for stripe in range(9):
            box(post, f"threshold_{stripe}", (x, centre - 1.9 + .46 * stripe, .032),
                (.52, .36, .015), YELLOW if stripe % 2 == 0 else (.065, .074, .084))

    worker = add(world, "model", name="safety_worker")
    add(worker, "static", "true")
    add(worker, "pose", "3.68 3.9 0 0 0 0")
    body = add(worker, "link", name="body")
    navy, fabric, vest = (.06, .10, .16), (.16, .23, .31), (.90, .63, .045)
    silver, boots = (.84, .89, .92), (.04, .05, .07)
    for side in (-1, 1):
        y = side * .12
        box(body, f"boot_{side}", (.043, y, .088), (.30, .16, .15), boots)
        box(body, f"leg_{side}", (0, y, .45), (.17, .17, .64), navy)
        box(body, f"sleeve_{side}", (0, side * .27, 1.19), (.19, .11, .43), fabric)
        box(body, f"arm_band_{side}", (0, side * .28, 1.10), (.20, .115, .06), silver)
        box(body, f"hand_{side}", (0, side * .28, .95), (.10, .10, .13), (.56, .36, .23))
        box(body, f"vest_band_{side}", (0, y, 1.25), (.264, .055, .32), silver)
    box(body, "vest", (0, 0, 1.20), (.252, .41, .44), vest)
    box(body, "reflective_belt", (0, 0, 1.06), (.266, .421, .058), silver)
    for name, z, size, colour in (("head", 1.58, (.125, .108, .142), (.58, .38, .25)),
                                  ("hard_hat", 1.69, (.154, .13, .091), (.98, .75, .065))):
        part = add(body, "visual", name=name)
        add(part, "pose", f"0 0 {z} 0 0 0")
        add(add(add(part, "geometry"), "ellipsoid"), "radii", numbers(size))
        material(part, colour)
    box(body, "brim", (.047, 0, 1.66), (.30, .27, .026), vest)
    box(body, "person_envelope", (0, 0, .89), (.30, .53, 1.77), collision=True)
    if virtual_sensor or aerial:
        pose = add(worker, "plugin", filename="ignition-gazebo-pose-publisher-system",
                   name="ignition::gazebo::systems::PosePublisher")
        for tag, value in (("publish_link_pose", "false"), ("publish_model_pose", "true"), ("publish_nested_model_pose", "true"),
                           ("use_pose_vector_msg", "true"), ("update_frequency", 15)):
            add(pose, tag, value)

    overview = link(world, "safety_overview")
    camera = add(overview, "sensor", name="warehouse_access", type="camera")
    view = "-5.2 -3.2 7.1 0 0.66 0.03" if dock_view else "-2.3 -3.2 7.4 0 0.59 0.03"
    add(camera, "pose", "11.5 1.25 8.15 0 .49 3.14" if aerial else view)
    add(camera, "always_on", "true")
    add(camera, "update_rate", 5 if virtual_sensor else 3)
    add(camera, "topic", "/rackonaut_safety/overview")
    optics = add(camera, "camera")
    add(optics, "horizontal_fov", 1.83 if aerial else 1.56)
    image = add(optics, "image")
    add(image, "width", 800)
    add(image, "height", 450)
    add(image, "format", "R8G8B8")
    clip = add(optics, "clip")
    add(clip, "near", .15)
    add(clip, "far", 43)
    return fields


def scanner_infrastructure(world, flight_profile=False):
    scanners = {
        "A": {"pose": [3.10, -1.92, .115, .58], "field": [3.50, -1.56, 15.0, 1.60], "arc": [-.92, .96]},
        "B": {"pose": [3.10, -7.92, .115, .58], "field": [3.50, -7.56, 11.0, -4.40], "arc": [-.92, .96]},
        "T": {"pose": [2.77, 1.85, .115, -1.5708], "field": [1.45, -7.50, 2.95, 1.05], "arc": [-1.20, 1.20]},
    }
    for zone, config in scanners.items():
        name = f"safety_scan_{zone.lower()}"
        x, y, z, yaw = config["pose"]
        config.update(topic=f"/rackonaut/safety/scan/{zone.lower()}", frame=f"{name}/body/scan", samples=512)
        mount = link(world, name)
        box(mount, "mount", (x, y, .038), (.13, .13, .076), (.09, .13, .18))
        box(mount, "scanner", (x, y, .138), (.14, .14, .097), (.055, .22, .29))
        box(mount, "lens", (x, y, .157), (.15, .15, .027), (.10, .87, .93))
        lidar = add(mount, "sensor", name="scan", type="gpu_lidar")
        add(lidar, "pose", numbers((x, y, z, 0, 0, yaw)))
        add(lidar, "topic", config["topic"])
        add(lidar, "always_on", "true")
        add(lidar, "update_rate", 5 if flight_profile and zone in {"A", "B"} else 4)
        add(lidar, "visualize", "true")
        ray = add(lidar, "lidar")
        horizontal = add(add(ray, "scan"), "horizontal")
        for tag, value in (("samples", config["samples"]), ("resolution", 1),
                           ("min_angle", config["arc"][0]), ("max_angle", config["arc"][1])):
            add(horizontal, tag, value)
        limits = add(ray, "range")
        for tag, value in (("min", .12), ("max", 15), ("resolution", .008)):
            add(limits, tag, value)
    return scanners


def scanner_props(world):
    forklift = link(world, "safety_forklift", "1.95 7.9 0 0 0 0")
    yellow, steel, rubber = (.92, .58, .05), (.16, .20, .25), (.043, .049, .055)
    box(forklift, "chassis", (-.25, 0, .41), (1.46, .83, .53), yellow, collision=True)
    box(forklift, "counterweight", (-.91, 0, .55), (.27, .86, .49), yellow)
    box(forklift, "seat", (-.34, 0, .86), (.40, .41, .16), rubber)
    box(forklift, "seatback", (-.55, 0, 1.02), (.10, .40, .27), rubber)
    box(forklift, "roof", (-.23, 0, 1.88), (1.21, .89, .09), steel)
    for side in (-1, 1):
        y = side * .41
        for x in (-.64, .28):
            part = add(forklift, "visual", name=f"tire_{side}_{x}")
            add(part, "pose", numbers((x, y, .27, 1.5708, 0, 0)))
            cylinder = add(add(part, "geometry"), "cylinder")
            add(cylinder, "radius", .265)
            add(cylinder, "length", .19)
            material(part, rubber)
            box(forklift, f"wheel_collision_{side}_{x}", (x, y, .17), (.32, .20, .34), collision=True)
            box(forklift, f"cage_{side}_{x}", (x, y, 1.25), (.077, .072, 1.19), steel)
        box(forklift, f"mast_{side}", (.59, y * .65, 1.03), (.13, .096, 1.82), steel)
        box(forklift, f"fork_{side}", (1.01, y * .59, .136), (.90, .10, .079), steel, collision=True)
    box(forklift, "fork_carriage", (.63, 0, .71), (.08, .64, .11), steel)
    box(forklift, "beacon", (-.20, 0, 1.97), (.12, .15, .10), YELLOW)

    pallet = link(world, "safety_pallet", "2.0 9.8 0 0 0 0")
    for x in (-.43, 0., .43):
        box(pallet, f"runner_{x}", (x, 0, .073), (.096, .79, .126), (.48, .30, .15), collision=True)
    for y in (-.31, -.155, 0., .155, .31):
        box(pallet, f"deck_{y}", (0, y, .148), (1.02, .121, .038), (.60, .42, .23), collision=True)


def twin_geometry(world, signals):
    """Export static display geometry without inventory or defect ground truth."""
    parts = {}
    for model in world.findall("model"):
        name = model.attrib["name"]
        for component in model.findall("link/visual"):
            part = component.attrib["name"]
            if name.startswith("rack_row_"):
                category = next((key for key in ("post", "guard", "deck", "beam", "label_mount", "decor")
                                 if part.startswith(key + "_")), None)
            elif name == "safety_markings_and_launch_pad":
                category = "marking"
            elif name == "signs_and_shipping_staging":
                category = "decor" if part.startswith("staged_") else None
            else:
                continue
            size = component.findtext("geometry/box/size")
            if category and size:
                xyz = list(map(float, component.findtext("pose").split()[:3]))
                dimensions = list(map(float, size.split()))
                color = list(map(float, component.findtext("material/diffuse").split()[:3]))
                parts.setdefault(category, []).append([*xyz, *dimensions, *color])
    shell = []
    for part in world.findall("model[@name='warehouse_shell']/link/collision"):
        if not part.attrib["name"].startswith(("side_", "end_")):
            continue
        coordinates = part.findtext("pose").split()[:3]
        dimensions = part.findtext("geometry/box/size").split()
        shell.append(list(map(float, coordinates + dimensions)))
    return {"parts": parts, "shell": shell, "signal_parts": [
        [name, center, *size] for name, center, size, _ in SIGNAL_STACK
    ], "signals": [
        {"zone": zone, "position": [x, y, 0.]}
        for zone, _, x, y, _, _ in signals
    ]}


def charging_station(world, offset=(0., 0.)):
    dock = link(world, "rackonaut_dock")
    navy, cyan, steel = (.045, .095, .145), (.08, .68, .72), (.25, .34, .43)
    parts = [
        ("landing_surface", (0, 0, .022), (2.47, 1.89, .010), navy),
        ("backplate", (-1.22, 0, .09), (.14, 2.26, .18), steel),
        ("charger_console", (-1.16, .86, .41), (.34, .39, .82), navy),
        ("console_cap", (-1.16, .86, .835), (.38, .43, .07), steel),
        ("red", (-1.16, .86, .895), (.08, .28, .055), (.075, .083, .09)),
        ("yellow", (-1.16, .86, .96), (.08, .28, .055), (.075, .083, .09)),
        ("green", (-1.16, .86, 1.025), (.08, .28, .055), (.075, .083, .09)),
    ]
    for side in (-1, 1):
        parts.extend([
            (f"guide_{side}", (0, side * 1.10, .057), (2.47, .06, .04), cyan),
            (f"coupler_{side}", (-.52, side * .51, .034), (.34, .16, .01), steel),
            (f"home_{side}", (side * .29, 0, .041), (.1, .65, .006), (.85, .90, .95)),
        ])
    parts.append(("home_crossbar", (0, 0, .041), (.59, .11, .006), (.85, .90, .95)))
    ox, oy = offset
    if offset != (0., 0.):
        parts = [(name, (x + ox, y + oy, z), size, color) for name, (x, y, z), size, color in parts]
    for name, point, size, color in parts:
        box(dock, name, point, size, color)
    plane_label(dock, "branding", (-1.16 + ox, .657 + oy, .47), .30, .19, texture="rackonaut")
    return {"parts": [[*point, *size, *color] for _, point, size, color in parts],
            "locator": [-1.16 + ox, .86 + oy, 1.72]}


def aerial_infrastructure(world, aisles, rack_height):
    height, deck, trunk, drop_x = 6.70, .79, 2.1, 5.1
    dx, dy = -4.7, 10.3
    if height - .62 <= rack_height or height + .64 >= 7.9:
        raise ValueError("The overhead corridor does not fit between racks and lights.")
    nodes = {"dock": [dx, dy, .05], "shaft": [dx, dy, height], "junction": [trunk, dy, height]}
    gates, aisles_3d = {}, {}
    edges = [["dock", "shaft", "shaft"], ["shaft", "junction", "tunnel"]]
    for name, center in zip(("B", "A"), aisles):
        y = round(center + .45, 3)
        nodes.update({f"trunk_{name}": [trunk, y, height], f"entry_{name}": [drop_x, y, height],
                      f"foot_{name}": [drop_x, y, deck]})
        gates[name] = [drop_x - .8, y - .8, drop_x + .8, y + .8]
        aisles_3d[name] = [3.58, y - 1.30 if name == "A" else y - 1.55, .61, 15.03, y + 1.12, 3.22]
        edges.extend([[f"trunk_{name}", f"entry_{name}", "tunnel"],
                      [f"entry_{name}", f"foot_{name}", name]])
    edges.extend([["junction", "trunk_A", "tunnel"], ["trunk_A", "trunk_B", "tunnel"]])
    tech = [dx - 1.48, dy - 1.38, dx + 1.43, dy + 1.42]

    frame = link(world, "protected_flight_infrastructure")
    parts = []
    mesh = []
    steel, edge, wire, cyan = (.12, .18, .23), (.90, .42, .10), (.24, .43, .50), (.06, .72, .80)

    def part(point, size, color, collision=False, screen=False):
        name = f"screen_{len(mesh)}" if screen else f"steel_{len(parts)}"
        box(frame, name, point, size, color, collision)
        if screen:
            frame.find(f"visual[@name='{name}']").append(ET.Element("transparency"))
            frame.find(f"visual[@name='{name}']/transparency").text = ".80"
        (mesh if screen else parts).append([*point, *size, *color])

    for zone, x, y, lower in (("D", dx, dy, .06), *[(n, drop_x, nodes[f"entry_{n}"][1], 1.18) for n in ("A", "B")]):
        for a in (-1, 1):
            for b in (-1, 1):
                part((x + a*.91, y + b*.91, (height + .59 + lower) / 2),
                     (.10, .10, height + .59 - lower), edge, collision=True)
        for z in (lower + .06, 2.30, 4.28, height - .6, height + .59):
            for side in (-1, 1):
                part((x, y + side*.91, z), (1.84, .08, .08), steel)
                # Leave the +X exit open on the launch tower and the −X entry on a descent.
                if z < height - 1.:
                    part((x + side*.91, y, z), (.08, 1.84, .08), steel)
        for side in (-1, 1):
            part((x, y + side*.91, (lower + height - .68) / 2),
                 (1.78, .035, height - .68 - lower), wire, collision=True, screen=True)
        # Floor marks show the base of the monitored descent without obstructing the scans.
        for side in (-1, 1):
            part((x, y + .95 * side, .025), (1.8, .07, .015), cyan)
            part((x + .95 * side, y, .025), (.07, 1.8, .015), cyan)
        plane_label(frame, f"aerial_notice_{zone}", (x - .86, y - .98, 2.20),
                    .78, .32, texture="safety_notice")

    for first, last, kind in edges:
        if kind != "tunnel":
            continue
        start, end = nodes[first], nodes[last]
        axis = 0 if start[0] != end[0] else 1
        along = end[axis] - start[axis]
        midpoint = [(a + b) / 2 for a, b in zip(start, end)]

        def position(span, side, z):
            return (midpoint[0] + span, midpoint[1] + side, z) if axis == 0 else (midpoint[0] + side, midpoint[1] + span, z)

        def sizes(length, width, tall):
            return (length, width, tall) if axis == 0 else (width, length, tall)

        # Set back screens at every node so joins and shaft openings remain clear.
        length = abs(along) - 1.86
        if length <= .05:
            continue
        for side in (-1, 1):
            for z in (height - .60, height + .58):
                part(position(0, side*.91, z), sizes(length, .09, .09), steel)
            part(position(0, side*.91, height), sizes(length, .032, 1.10), wire, collision=True, screen=True)
        part(position(0, 0, height - .60), sizes(length, 1.78, .035), wire, collision=True, screen=True)
        for step in range(max(2, int(length / .66)) + 1):
            span = -.5*length + length*step/max(2, int(length / .66))
            for side in (-1, 1):
                part(position(span, side*.91, height), sizes(.067, .075, 1.24), edge)
            part(position(span, 0, height - .60), sizes(.067, 1.90, .064), wire)
            part(position(span, 0, height + .59), sizes(.067, 1.90, .064), steel)
        part(position(0, -.88, height + .61), sizes(length, .034, .028), cyan)
        for center in ((-length / 4, length / 4) if length > 3. else (0.,)):
            direction = 1 if along > 0 else -1
            for index in range(-3, 4):
                part(position(center + direction * (.15 - abs(index) * .095), index * .085, height - .57),
                     sizes(.104, .092, .012), cyan)

    return {"nodes": nodes, "edges": edges, "gates": gates, "inspection_volumes": aisles_3d,
            "technical": tech, "parts": parts, "screens": mesh,
            "pad": {"x": dx, "y": dy, "z": .05, "yaw_deg": 0., "width": 2.65, "height": 2.1}}


def avoidance_fixtures(world):
    """Park movable, collidable demonstration props outside the flight network."""
    props = {
        "aisle_box": ((6.95, .45, .82), (.46, .46, .46), (.90, .36, .11)),
        "rack_load": ((7.30, 1.10, .90), (.65, 1.06, .65), KRAFT),
        "hanging_load": ((7.30, .45, 2.66), (.58, .64, .82), (.81, .57, .15)),
        "aisle_block": ((6.95, .45, 1.83), (.34, 3.70, 3.06), (.66, .15, .12)),
        "tunnel_block": ((-1.00, 10.30, 6.70), (.34, 1.78, 1.14), (.76, .19, .12)),
        "descent_block": ((5.10, .45, 3.72), (1.57, 1.57, .26), (.76, .19, .12)),
        "shaft_block": ((-4.70, 10.30, 3.10), (1.57, 1.57, .26), (.76, .19, .12)),
    }
    layout = {}
    for index, (key, (location, size, color)) in enumerate(props.items()):
        park = (27.5 + (index % 2) * 2., -10.7 + (index // 2) * 2.55, size[2] / 2)
        model = link(world, f"avoidance_{key}", numbers((*park, 0, 0, 0)))
        box(model, "load", (0, 0, 0), size, color, collision=True)
        for side in (-1, 1):
            box(model, f"stripe_{side}", (side * (size[0] / 2 + .002), 0, 0),
                (.005, size[1] * .94, min(.10, size[2] / 3)), YELLOW)
        layout[key] = {"park": park, "location": location, "size": size}
    return layout


def generate(args):
    sdf, world = world_base()
    hall(world, args.hall)
    count = 1 if args.profile == "pilot" else args.aisles
    row_pitch = args.aisle_width + DEPTH
    positions = [(index - count / 2) * row_pitch for index in range(count + 1)]
    aisles = [(low + high) / 2 for low, high in zip(positions, positions[1:])]
    if max(abs(y) for y in positions) + DEPTH / 2 >= 12.45:
        raise SystemExit("The selected aisle widths and count exceed the hall width.")
    if 5.5 + (args.bays - .5) * args.bay_pitch >= 32 or args.rack_height >= 8.2:
        raise SystemExit("The selected rack size exceeds the hall envelope.")
    inspection = count // 2 + 1
    aerial = aerial_infrastructure(world, aisles, args.rack_height) if args.aerial else None
    offset = tuple(aerial["nodes"]["dock"][:2]) if aerial else (0., 0.)
    paint(world, aisles, args.aisle_width, offset)
    if args.energy:
        station = charging_station(world, offset)
        if aerial:
            aerial["dock"] = station
        if args.dock_layout:
            args.dock_layout.write_text(json.dumps(station, indent=2) + "\n")
    rows = []
    rng = random.Random(args.seed)
    for index, y in enumerate(positions):
        rack(world, index, y, args, rng, index == inspection, rows)
    signs(world, aisles, positions[inspection])
    rack_end = 5.5 + (args.bays - .5) * args.bay_pitch
    if args.safety:
        fields = safety_infrastructure(world, aisles, rack_end, not args.laser, args.energy, aerial)
        if args.layout:
            args.layout.write_text(json.dumps(fields, indent=2) + "\n")
        if args.laser:
            scanners = scanner_infrastructure(world, args.avoidance)
            scanner_props(world)
            args.laser.write_text(json.dumps(scanners, indent=2) + "\n")
    if args.avoidance:
        props = avoidance_fixtures(world)
        if args.avoidance_layout:
            args.avoidance_layout.write_text(json.dumps(props, indent=2) + "\n")
    if aerial and args.aerial_layout:
        aerial["scene"] = twin_geometry(world, safety_posts(aisles, rack_end, aerial))
        args.aerial_layout.write_text(json.dumps(aerial, separators=(",", ":")) + "\n")
    ET.indent(sdf, space="  ")
    ET.ElementTree(sdf).write(args.output, encoding="utf-8", xml_declaration=True)
    if args.layout and not args.safety:
        layout = {
            "floor": {"x": HALL_CENTER - 20, "y": -12.5, "width": 40, "height": 25},
            "racks": [{"x": 5.5 - args.bay_pitch / 2, "y": y - DEPTH / 2,
                       "width": args.bays * args.bay_pitch, "height": DEPTH,
                       "bays": args.bays} for y in positions],
            "aisles": [{"id": name, "y": y, "functional": name != "C"} for name, y in zip(("B", "A", "C"), aisles)],
            "pad": {"x": 0., "y": 0., "z": .05, "yaw_deg": 0., "width": 2.65, "height": 2.1},
            "takeoff_z": .79,
            "crossing_x": 2.1,
            "scene": twin_geometry(world, safety_posts(aisles, rack_end)),
            "slots": {item["slot_id"]: {"label": item["slot_label_xyz_m"], "viewpoint": item["viewpoint"],
                                     "bay_center": item["bay_center_xyz_m"], "bay_width": args.bay_pitch,
                                     "aisle": item["slot_id"][0], "bay": item["physical_bay"],
                                     "level": item["physical_level"]} for item in sorted(rows, key=lambda r: r["slot_id"])},
        }
        args.layout.write_text(json.dumps(layout, indent=2) + "\n")
    if args.marker_map:
        marker_map = {"dictionary": "DICT_4X4_50",
                      "locations": {str(item["slot_aruco_id"]): item["slot_id"] for item in rows},
                      "pallets": {str(item["pallet_aruco_id"]): item["pallet_id"] for item in rows
                                  if item["pallet_aruco_id"] is not None}}
        args.marker_map.write_text(json.dumps(marker_map, indent=2) + "\n")
    if args.truth:
        expected_data = json.loads((REPO / "test_data/expected_inventory.json").read_text())
        expected = {item["slot_id"]: item["pallet_id"] for item in expected_data["locations"]}
        for item in rows:
            item["expected_pallet_id"] = expected[item["slot_id"]]
        truth = {"source": "simulation_ground_truth", "marker_dictionary": "DICT_4X4_50",
                 "profile": args.profile, "decorative_stock_has_no_inventory_ids": True,
                 "slots": rows}
        args.truth.write_text(json.dumps(truth, indent=2) + "\n")


def write_labels(control=False, safety=False):
    import cv2
    import numpy as np

    directory = ROOT / "materials/textures"
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    font = cv2.FONT_HERSHEY_DUPLEX
    print_blue, print_orange = (84, 46, 20), (32, 111, 220)

    def save(name, image):
        if not cv2.imwrite(str(directory / f"{name}.png"), image):
            raise RuntimeError(f"Could not write {name}")

    def text(image, value, origin, scale, color, weight=3):
        cv2.putText(image, value, origin, font, scale, color, weight, cv2.LINE_AA)

    def card(name, head, value, accent, marker):
        image = np.full((360, 580, 3), 245, np.uint8)
        cv2.rectangle(image, (0, 0), (579, 359), accent, 13)
        if marker is not None:
            pattern = cv2.aruco.drawMarker(dictionary, marker, 264)
            image[48:312, 36:300] = cv2.cvtColor(pattern, cv2.COLOR_GRAY2BGR)
        else:
            cv2.rectangle(image, (36, 48), (299, 311), (90, 90, 90), -1)
            for x in range(-120, 260, 32):
                cv2.line(image[60:300, 48:288], (x, 240), (x + 210, 0), (160, 160, 160), 9)
        text(image, head, (315, 138), .86, accent, 2)
        text(image, value, (312, 218), 1.45, (24, 24, 24))
        text(image, "RACKONAUT", (315, 278), .71, accent, 2)
        save(name, image)

    if safety:
        image = np.full((240, 620, 3), (24, 26, 31), np.uint8)
        cv2.rectangle(image, (4, 4), (615, 235), (23, 187, 245), 13)
        text(image, "DRONE INSPECTION", (42, 98), 1.67, (23, 187, 245), 4)
        text(image, "RED  /  DO NOT ENTER", (45, 172), 1.32, (240, 242, 249), 3)
        save("safety_notice", image)
        return
    if control:
        for i, (pallet, marker, _) in enumerate(CONTROL_B_STOCK):
            slot = len(STOCK) + i
            card(f"slot_{slot:02}", "LOCATION", f"B-{i // 2 + 1:02d}-{i % 2 + 1:02d}", print_blue, slot)
            if marker is not None:
                card(f"pallet_{marker}", "PALLET", pallet, print_orange, marker)
        return
    for index in range(len(STOCK)):
        card(f"slot_{index:02}", "LOCATION", f"A-01-{index + 1:02}", print_blue, index)
    for pallet, marker, _ in STOCK:
        if marker is not None:
            card(f"pallet_{marker}", "PALLET", pallet, print_orange, marker)
    card("label_unreadable", "PALLET", "N/A", print_orange, None)
    for index, name in enumerate(("B", "A", "C")):
        image = np.full((240, 620, 3), print_blue, np.uint8)
        cv2.rectangle(image, (2, 2), (617, 237), (66, 161, 237), 13)
        text(image, f"AISLE  {name}", (95, 160), 3.1, (247, 245, 232), 6)
        save(f"aisle_{index}", image)
    image = np.full((230, 790, 3), print_blue, np.uint8)
    cv2.rectangle(image, (2, 2), (787, 227), (63, 154, 243), 12)
    text(image, "RACKONAUT", (68, 133), 2.9, (245, 246, 244), 6)
    text(image, "WAREHOUSE INSPECTION   /   ZONE A", (74, 190), .86, (190, 212, 228), 2)
    save("rackonaut", image)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "worlds/showcase.sdf")
    parser.add_argument("--truth", type=Path)
    parser.add_argument("--profile", choices=("pilot", "showcase"), default="showcase")
    parser.add_argument("--hall", choices=("tevy", "procedural"), default="tevy")
    parser.add_argument("--aisles", type=int, choices=(1, 3), default=3)
    parser.add_argument("--bays", type=int, default=7)
    parser.add_argument("--levels", type=int, default=3)
    parser.add_argument("--bay-pitch", type=float, default=2.8)
    parser.add_argument("--aisle-width", type=float, default=4.8)
    parser.add_argument("--rack-height", type=float, default=5.7)
    parser.add_argument("--fill", type=float, default=.81)
    parser.add_argument("--seed", type=int, default=26)
    parser.add_argument("--labels", action="store_true")
    parser.add_argument("--quality", action="store_true", help="stage visible carton defects in a separate output world")
    parser.add_argument("--control", action="store_true", help="add the functional aisle B to the three-aisle showcase")
    parser.add_argument("--safety", action="store_true", help="add access control to the control showcase")
    parser.add_argument("--laser", type=Path, help="add GPU LiDAR and write its calibration and fields")
    parser.add_argument("--adaptive", action="store_true", help="stage a recoverable label occlusion")
    parser.add_argument("--energy", action="store_true", help="add the simulated Rackonaut charging station")
    parser.add_argument("--dock-layout", type=Path)
    parser.add_argument("--aerial", action="store_true")
    parser.add_argument("--aerial-layout", type=Path)
    parser.add_argument("--avoidance", action="store_true")
    parser.add_argument("--avoidance-layout", type=Path)
    parser.add_argument("--layout", type=Path)
    parser.add_argument("--marker-map", type=Path)
    args = parser.parse_args()
    if (args.quality or args.control) and args.output.resolve() in (ROOT / "worlds/showcase.sdf", ROOT / "worlds/pilot.sdf"):
        parser.error("--quality and --control require a separate --output path")
    if (args.layout or args.marker_map) and not args.control:
        parser.error("--layout and --marker-map require --control")
    if args.safety and (not args.control or not args.quality or args.marker_map):
        parser.error("--safety requires --control and --quality and publishes separate zone geometry")
    if args.laser and not args.safety:
        parser.error("--laser requires --safety")
    if args.adaptive and not args.safety:
        parser.error("--adaptive requires --safety")
    if (args.energy and not args.safety) or (args.dock_layout and not args.energy):
        parser.error("Dock layout requires an energy showcase with safety.")
    if (args.aerial and not args.energy) or (args.aerial_layout and not args.aerial):
        parser.error("Aerial infrastructure requires an energy showcase.")
    if (args.avoidance and not args.aerial) or (args.avoidance_layout and not args.avoidance):
        parser.error("Obstacle avoidance fixtures require an aerial showcase.")
    if args.control and (args.profile != "showcase" or args.aisles != 3 or args.aisle_width != 4.8
                         or args.bay_pitch != 2.8 or args.rack_height != 5.7 or args.levels != 3 or args.truth):
        parser.error("--control uses the default three-aisle geometry and separate layout data")
    if args.bays < 4 or args.levels < 2 or not 0 <= args.fill <= 1:
        parser.error("The fixture needs at least four bays, two levels and fill between zero and one.")
    if args.bay_pitch < 2.65 or args.aisle_width < 3 or args.rack_height < 3.5:
        parser.error("Rack or aisle dimensions would leave too little clearance for the inspection fixture.")
    if args.labels:
        write_labels(args.control, args.safety)
    generate(args)


if __name__ == "__main__":
    main()
