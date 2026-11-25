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


def link(world, name):
    model = add(world, "model", name=name)
    add(model, "static", "true")
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


def paint(world, rows, aisle_width):
    marks = link(world, "safety_markings_and_launch_pad")
    box(marks, "matte_concrete_top", (HALL_CENTER, 0, .007), (39.65, 24.65, .010), (.25, .27, .29))
    for joint in range(-3, 31, 5):
        box(marks, f"slab_joint_{joint}", (joint, 0, .012), (.026, 24.6, .004), (.19, .21, .23))
    for index, y in enumerate(rows):
        for side in (-1, 1):
            stripe_y = y + side * (aisle_width / 2 - .16)
            box(marks, f"line_{index}_{side}", (14.1, stripe_y, .017), (27.7, .105, .015), YELLOW)
    box(marks, "takeoff_pad", (0, 0, .016), (2.65, 2.1, .021), (.03, .19, .23))
    for side in (-1, 1):
        box(marks, f"pad_border_long_{side}", (0, side * 1.035, .028), (2.63, .075, .015), YELLOW)
        box(marks, f"pad_border_short_{side}", (side * 1.29, 0, .028), (.075, 2.12, .015), YELLOW)
        box(marks, f"pad_H_leg_{side}", (side * .29, 0, .032), (.10, .65, .016), (.85, .90, .95))
    box(marks, "pad_H_crossbar", (0, 0, .032), (.59, .11, .016), (.85, .90, .95))
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
    paint(world, aisles, args.aisle_width)
    rows = []
    rng = random.Random(args.seed)
    for index, y in enumerate(positions):
        rack(world, index, y, args, rng, index == inspection, rows)
    signs(world, aisles, positions[inspection])
    ET.indent(sdf, space="  ")
    ET.ElementTree(sdf).write(args.output, encoding="utf-8", xml_declaration=True)
    if args.layout:
        layout = {
            "floor": {"x": HALL_CENTER - 20, "y": -12.5, "width": 40, "height": 25},
            "racks": [{"x": 5.5 - args.bay_pitch / 2, "y": y - DEPTH / 2,
                       "width": args.bays * args.bay_pitch, "height": DEPTH,
                       "bays": args.bays} for y in positions],
            "aisles": [{"id": name, "y": y, "functional": name != "C"} for name, y in zip(("B", "A", "C"), aisles)],
            "pad": {"x": 0., "y": 0., "z": .05, "yaw_deg": 0., "width": 2.65, "height": 2.1},
            "takeoff_z": .79,
            "crossing_x": 2.1,
            "slots": {item["slot_id"]: {"label": item["slot_label_xyz_m"], "viewpoint": item["viewpoint"],
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


def write_labels(control=False):
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
    parser.add_argument("--layout", type=Path)
    parser.add_argument("--marker-map", type=Path)
    args = parser.parse_args()
    if (args.quality or args.control) and args.output.resolve() in (ROOT / "worlds/showcase.sdf", ROOT / "worlds/pilot.sdf"):
        parser.error("--quality and --control require a separate --output path")
    if (args.layout or args.marker_map) and not args.control:
        parser.error("--layout and --marker-map require --control")
    if args.control and (args.profile != "showcase" or args.aisles != 3 or args.aisle_width != 4.8
                         or args.bay_pitch != 2.8 or args.rack_height != 5.7 or args.levels != 3 or args.truth):
        parser.error("--control uses the default three-aisle geometry and separate layout data")
    if args.bays < 4 or args.levels < 2 or not 0 <= args.fill <= 1:
        parser.error("The fixture needs at least four bays, two levels and fill between zero and one.")
    if args.bay_pitch < 2.65 or args.aisle_width < 3 or args.rack_height < 3.5:
        parser.error("Rack or aisle dimensions would leave too little clearance for the inspection fixture.")
    if args.labels:
        write_labels(args.control)
    generate(args)


if __name__ == "__main__":
    main()
