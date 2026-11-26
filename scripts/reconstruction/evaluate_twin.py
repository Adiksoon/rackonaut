#!/usr/bin/env python3
"""Freeze template exports before running an independent SDF comparison."""
import argparse
from base64 import b64decode
from hashlib import sha256
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET

import numpy as np

from rackonaut_control.reconstruction.geometry import reconstruct
from rackonaut_control.reconstruction.reconstruct import generate, read_json
from rackonaut_control.reconstruction.twin import axes, completion, generate_twin
from validate import angle_error, compare, reference, xyz


def freeze(directory, camera, cases):
    bundles = {}
    for label, archive in cases:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", label):
            raise ValueError("Case labels must contain only alphanumerics, underscores or hyphens.")
        display_label = label.upper().replace("GOAL", "GOAL ")
        baseline, baseline_seconds = generate(archive, camera, display_label)
        variants = {}
        for source in ("ply", "combined"):
            if source == "combined" and not (archive / "localization.npz").is_file():
                continue
            packet, seconds = generate_twin(archive, camera, display_label, source)
            if {key: value for key, value in packet.items() if key != "enhanced"} != baseline:
                raise ValueError(f"{label} {source} changed the original measured output.")
            path = directory / f"{label}-{source}.json"
            with path.open("x", encoding="utf-8") as output:
                json.dump(packet, output, allow_nan=False, ensure_ascii=False, separators=(",", ":"))
                output.write("\n")
            digest = sha256(path.read_bytes()).hexdigest()
            variants[source] = (packet, seconds, digest)
            print(f"{label} {source}: {seconds:.2f}s {digest}", flush=True)
        bundles[label] = (baseline, baseline_seconds, variants)
    return bundles


def reference_profiles(world):
    profiles = {}
    for model in ET.parse(world).findall("world/model"):
        name = model.get("name")
        if not re.fullmatch(r"rack_row_\d+", name):
            continue
        columns, decks = set(), set()
        for link in model.findall("link"):
            for visual in link.findall("visual"):
                key = visual.get("name")
                if key.startswith("post_"):
                    columns.add(round(float((xyz(model) + xyz(link) + xyz(visual))[0]), 5))
                if key.startswith("deck_"):
                    z = float((xyz(model) + xyz(link) + xyz(visual))[2])
                    height = np.fromstring(visual.findtext("geometry/box/size"), sep=" ")[2]
                    decks.add((round(z - height/2, 6), round(z + height/2, 6)))
        profiles[name] = (np.diff(sorted(columns)), sorted(decks))
    return profiles


def model_metrics(packet, measured, world, markers, profiles):
    twin = packet["enhanced"]
    matched = {row["row"]: row["world_row"] for row in measured["matched"]}
    rows = []
    for row in twin["rows"]:
        tag = matched.get(row["id"])
        entry = {
            "id": row["id"], "reference_row": tag, "position_m": row["position_m"],
            "dimensions_m": row["dimensions_m"], "yaw_rad": row["yaw_rad"],
            "levels_m": row["levels_m"], "pitch_m": row["post_pitch_m"],
            "post_stations": len(row["stations_u"]), "end_extension_m": row["end_extension_m"],
            "quality": row["quality"],
        }
        if tag:
            low, high, _ = world[tag]
            pitches, planes = profiles[tag]
            entry.update({
                "length_fraction": row["dimensions_m"][0] / (high - low)[0],
                "across_centre_error_m": abs(row["position_m"][1] - (high[1] + low[1])/2),
                "yaw_error_deg": angle_error(row["yaw_rad"]),
                "dimension_errors_m": (np.asarray(row["dimensions_m"]) - (high-low)).tolist(),
                "pitch_error_m": (row["post_pitch_m"] - float(np.median(pitches))) if row["post_pitch_m"] else None,
                "level_top_errors_m": [float(z - min((top for _, top in planes), key=lambda v: abs(v-z)))
                                       for z in row["levels_m"]],
                "level_nearest_face_errors_m": [float(z - min(np.ravel(planes), key=lambda v: abs(v-z)))
                                                for z in row["levels_m"]],
                "measured_level_nearest_face_errors_m": [float(z - min(np.ravel(planes), key=lambda v: abs(v-z)))
                                                         for z in row["observed_levels_m"]],
            })
        rows.append(entry)
    labels = []
    for item in twin["locations"]:
        row = matched.get(item.get("rack_id"))
        target = markers.get(item["id"])
        record = {k: v for k,v in item.items() if k in {"id", "status", "reason", "level"}}
        if target and "position_m" in item:
            record.update(correct_row=row == target["row"], error_to_aruco_m=float(
                np.linalg.norm(np.asarray(item["position_m"]) - target["marker"])))
        labels.append(record)
    return {"source": twin["source"], "rows": rows, "locations": labels, "keyframes": twin["keyframes"],
            "floor": twin["floor"], "walls": len(twin["walls"]), "aisles": len(twin["aisles"]),
            "dock": twin["dock"] is not None, "route_edges": len(twin["route_edges_m"]),
            "route_source": twin["route_source"]}


def modifications(packet):
    points = np.frombuffer(b64decode(packet["points_f32le"]), dtype="<f4").reshape(-1, 3).astype(float)
    row = packet["rows"][0]
    uv = points[:, :2] @ axes(row["yaw_rad"])
    low, high = np.asarray(row["bounds_uv"])
    band = (uv[:, 1] >= low[1] - .35) & (uv[:, 1] <= high[1] + .35)
    band &= points[:, 2] < row["vertical_extent_m"][1] + .3
    whole = band & (uv[:, 0] >= low[0] - 2) & (uv[:, 0] <= high[0] + 2)
    hole = band & (np.abs(uv[:, 0] - (low[0] + high[0]) / 2) < .31)
    rotated = points.copy()
    rotated[:, :2] = points[:, :2] @ axes(np.deg2rad(27)).T + [8., -4.]
    empty = np.empty((0, 3))
    result = []
    for title, source in (("central strip removed", points[~hole]), ("one row removed", points[~whole]),
                          ("low-only map", points[points[:, 2] < np.quantile(points[:, 2], .2)+1.25]),
                          ("rotation 27 degrees with translation", rotated)):
        started_rows, _ = reconstruct(source)
        for i, candidate in enumerate(started_rows, 1):
            candidate["id"] = f"R{i:02d}"
        model = completion(source, started_rows, empty, empty)
        result.append({"case": title, "points": len(source), "rows": len(model["rows"]),
                       "yaw_deg_mod_180": [float(np.degrees(row["yaw_rad"])) for row in model["rows"]],
                       "lengths_m": [row["dimensions_m"][0] for row in model["rows"]],
                       "levels": [len(row["levels_m"]) for row in model["rows"]],
                       "pitches_m": [row["post_pitch_m"] for row in model["rows"]],
                       "minimum_deck_support_fraction": min(
                           (min(row["quality"]["deck_area_support_fraction"]) for row in model["rows"]), default=None)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", nargs=2, metavar=("LABEL", "CALIBRATION"), action="append", required=True)
    parser.add_argument("--camera-calibration", type=Path, required=True)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--warehouse-assets", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    camera = read_json(args.camera_calibration)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    bundles = freeze(args.output_dir, camera, [(label, Path(folder)) for label, folder in args.case])
    archive = next((baseline for baseline, _, _ in bundles.values() if baseline["rows"]), None)
    stress = modifications(archive) if archive else []
    # Only the completed exports go into the independent reference comparison.
    world, markers = reference(args.world, args.warehouse_assets)
    profiles = reference_profiles(args.world)
    outputs = {}
    for label, (original, baseline_seconds, variants) in bundles.items():
        measured = compare(original, world, markers)
        measured["export_seconds"] = baseline_seconds
        measured["byte_equivalent_in_template_bundle"] = True
        case = {"measured_model": measured}
        for source, (packet, seconds, digest) in variants.items():
            result = model_metrics(packet, measured, world, markers, profiles)
            result.update(export_seconds=seconds, bundle_sha256=digest)
            case[source] = result
        outputs[label] = case
    with (args.output_dir / "validation.json").open("x", encoding="utf-8") as output:
        json.dump({"cases": outputs, "modified_ply": stress}, output, indent=2, allow_nan=False)
        output.write("\n")


if __name__ == "__main__":
    main()
