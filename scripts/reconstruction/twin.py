#!/usr/bin/env python3
"""Export calibration measurements and warehouse template parameters for an offline viewer."""
import argparse
from functools import partial
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np
from scipy.signal import find_peaks
from scipy.spatial import cKDTree

from geometry import GRID, normals, reconstruct
from reconstruct import FRAME, archive_details, encode, locations, pose, read_json, read_ply
from rackonaut_localization.learned_map import load


VOXEL = .12


def axes(yaw):
    c, s = np.cos(yaw), np.sin(yaw)
    return np.array([[c, -s], [s, c]])


def keyframe_voxels(frames, ply):
    """Cap repeat returns to one vote per cell and nearby view-pose group."""
    origins = np.array([frame.position for frame in frames])
    directions = np.array([frame.orientation.apply([1, 0, 0]) for frame in frames])
    _, views = np.unique(np.column_stack((np.floor(origins / .65), np.round(directions * 2))),
                         axis=0, return_inverse=True)
    points = np.vstack([frame.points for frame in frames])
    normal_abs = np.abs(np.vstack([frame.normals for frame in frames]))
    view = np.repeat(views, [len(frame.points) for frame in frames])
    coords = np.floor(points / VOXEL).astype(np.int32)
    cells, inverse = np.unique(coords, axis=0, return_inverse=True)
    group_count = int(views.max()) + 1
    keys = inverse.astype(np.int64) * group_count + view
    pairs, pair_indices, counts = np.unique(keys, return_inverse=True, return_counts=True)
    pair_cells = pairs // group_count
    view_counts = np.bincount(pair_cells, minlength=len(cells))

    def average(values):
        samples = np.bincount(pair_indices, weights=values) / counts
        return np.bincount(pair_cells, weights=samples, minlength=len(cells)) / view_counts

    centers = np.column_stack([average(axis) for axis in points.T])
    normal = np.column_stack([average(axis) for axis in normal_abs.T])
    distance = cKDTree(ply).query(centers)[0]
    keep = (view_counts >= 2) | (distance <= .18)
    return centers[keep], normal[keep], {
        "raw_returns": len(points), "keyframes": len(frames), "pose_groups": group_count,
        "occupied_voxels": len(cells), "retained_voxels": int(keep.sum()),
        "multi_view_voxels": int((view_counts >= 2).sum()),
        "retained_beyond_ply_18cm": int((keep & (distance > .18)).sum()),
    }


def fit_bays(posts, depth):
    # Link front and back posts at the same longitudinal coordinate.
    columns = np.sort(np.asarray(posts)[:, 0])
    groups = np.split(columns, np.flatnonzero(np.diff(columns) > .22) + 1)
    centers = np.array([np.median(group) for group in groups])
    best = None
    for a, b in combinations(centers, 2):
        for periods in range(1, 5):
            pitch = (b - a) / periods
            if not .85 * depth <= pitch <= 4 * depth:
                continue
            index = np.rint((centers - a) / pitch).astype(int)
            residual = np.abs(centers - (a + index * pitch))
            keep = residual <= .17
            used = index[keep]
            if len(np.unique(used)) < 3 or not np.any(np.diff(used) == 1):
                continue
            score = (keep.sum(), np.count_nonzero(np.diff(used) == 1), -residual[keep].mean())
            if best is None or score > best[0]:
                best = score, used, centers[keep]
    if best is None:
        return None
    _, indices, measured = best
    pitch, start = np.polyfit(indices, measured, 1)
    rms = np.sqrt(np.mean((start + pitch * indices - measured) ** 2))
    return float(start), float(pitch), len(measured), float(rms)


def span_supported(points, start, end, depth, heights):
    # Only shells with support on several shelves can extend a detected end.
    if len(points) == 0 or end - start <= .05:
        return False
    u, v, z = points.T
    candidate = z[(u >= start - .05) & (u <= end + .05)
                  & (v >= depth[0] - .06) & (v <= depth[1] + .06)]
    return sum(np.count_nonzero(np.abs(candidate - level) <= .11) >= 4 for level in heights) >= 2


def fit_rack(row, ground, detail, detail_normals):
    lo, hi = np.asarray(row["bounds_uv"], dtype=float)
    rotation = axes(row["yaw_rad"])
    samples = np.column_stack((detail[:, :2] @ rotation, detail[:, 2]))
    planes = samples[detail_normals[:, 2] >= .85]
    observed = np.array([level["z"] for level in row["levels"]])
    refined = observed.copy()
    level_votes = []
    for index, height in enumerate(observed):
        u, v, z = planes.T
        near = (u >= lo[0]) & (u <= hi[0]) & (v >= lo[1] - .08) & (v <= hi[1] + .08)
        local = planes[near & (np.abs(z - height) < .115)]
        level_votes.append(len(local))
        if len(local) >= 18 and np.ptp(local[:, 0]) >= .45 * (hi[0] - lo[0]):
            refined[index] = np.median(local[:, 2])

    # A shared pitch straightens shelves while keeping any distinct measured pattern.
    index = np.rint((refined - refined[0]) / np.median(np.diff(refined)))
    step, phase = np.polyfit(index, refined, 1)
    lattice = phase + index * step
    levels = lattice if np.max(np.abs(lattice - refined)) < .105 else refined

    score = None
    lower_u, upper_u = lo[0], hi[0]
    if row["posts"]:
        score = fit_bays(row["posts"], hi[1] - lo[1])
    if score:
        anchor, pitch, _, _ = score
        limits = anchor + np.rint((np.array([lower_u, upper_u]) - anchor) / pitch) * pitch
        maximum = min(.45 * pitch, .85)
        if 0 < lower_u - limits[0] <= maximum and span_supported(
                planes, limits[0], lower_u, [lo[1], hi[1]], observed):
            lower_u = limits[0]
        if 0 < limits[1] - upper_u <= maximum and span_supported(
                planes, upper_u, limits[1], [lo[1], hi[1]], observed):
            upper_u = limits[1]
        # Round close end frames while retaining the entire measured envelope.
        stations = anchor + np.arange(np.ceil((lower_u - anchor) / pitch),
                                      np.floor((upper_u - anchor) / pitch) + 1) * pitch
        interior = stations[(stations - lower_u > .24 * pitch) & (upper_u - stations > .24 * pitch)]
        posts = np.r_[lower_u, interior, upper_u]
    else:
        # Generic display bays provide a usable template with an unknown pitch.
        slots = max(1, round((upper_u - lower_u) / (2 * (hi[1] - lo[1]))))
        posts = np.linspace(lower_u, upper_u, slots + 1)

    observed_base, observed_top = row["vertical_extent_m"]
    base = ground if ground is not None and -.10 <= observed_base - ground <= .65 else observed_base
    top = observed_top
    if row["posts"]:
        top = max(levels[-1], float(np.quantile(np.asarray(row["posts"])[:, 3], .85)))
    # A box-template extrusion can include overhead clearance only if there is
    # measured post height. A deck at the top still terminates at its own level.
    bounds = [[float(lower_u), float(lo[1])], [float(upper_u), float(hi[1])]]
    length = float(upper_u - lower_u)
    depth = float(hi[1] - lo[1])
    coverage = []
    for level in row["levels"]:
        area = sum((u1-u0) * (v1-v0) for u0, v0, u1, v1 in level["patches_uv"])
        coverage.append(min(1., area / (length * depth)))
    return {
        "id": row["id"], "yaw_rad": row["yaw_rad"], "bounds_uv": bounds,
        "position_m": [*((np.mean(bounds, axis=0)) @ rotation.T), float(base)],
        "dimensions_m": [length, depth, float(top - base)],
        "vertical_extent_m": [float(base), float(top)], "levels_m": levels.tolist(),
        "observed_bounds_uv": row["bounds_uv"], "observed_vertical_extent_m": row["vertical_extent_m"],
        "end_extension_m": [float(lo[0] - lower_u), float(upper_u - hi[0])],
        "observed_levels_m": observed.tolist(), "stations_u": posts.tolist(),
        "post_pitch_m": score[1] if score else None,
        "quality": {"post_evidence": score[2] if score else 0, "post_residual_m": score[3] if score else None,
                    "deck_area_support_fraction": coverage, "npz_level_voxels": level_votes,
                    "support_points": row["support_points"], "regular_levels": bool(levels is lattice)},
    }


def calibrated_layout(dock, route, trace, floor, rows):
    pad = None
    if dock is not None:
        first = route["nodes"][0] if route and route["nodes"] else None
        yaw = pose(first)[1].as_euler("zyx")[0] if first and first["type"] == "DOCK" else None
        pad = {"position_m": dock, "yaw_rad": yaw}
    edges = []
    if route:
        positions = {node["id"]: pose(node)[0].tolist() for node in route["nodes"]}
        edges = [[positions[edge["from"]], positions[edge["to"]]] for edge in route["edges"]]
    if not edges and trace:
        samples = np.asarray(trace, dtype=float)
        if samples.ndim != 2 or samples.shape[1] != 3 or not np.isfinite(samples).all():
            raise ValueError("The recorded calibration trajectory has invalid samples.")
        edges = np.stack((samples[:-1], samples[1:]), axis=1).tolist()
    aisles = []
    if floor:
        for left, right in combinations(rows, 2):
            if abs(np.sin(left["yaw_rad"] - right["yaw_rad"])) > .04:
                continue
            yaw = left["yaw_rad"]
            bounds = np.asarray(right["bounds_uv"])
            uv = np.array([[u, v] for u in bounds[:, 0] for v in bounds[:, 1]])
            aligned = uv @ axes(right["yaw_rad"]).T @ axes(yaw)
            a, b = sorted((np.asarray(left["bounds_uv"]), np.array([aligned.min(0), aligned.max(0)])),
                          key=lambda limits: limits[0, 1])
            start, end = max(a[0, 0], b[0, 0]), min(a[1, 0], b[1, 0])
            if end - start >= 1.5 and b[0, 1] - a[1, 1] >= .75:
                # Only the immediate open strip between reconstructed neighbours.
                middle = (a[1, 1] + b[0, 1]) / 2
                center = np.array([(start + end) / 2, middle]) @ axes(yaw).T
                if any(other is not left and other is not right
                       and np.all((center @ axes(other["yaw_rad"]) >= other["bounds_uv"][0])
                                  & (center @ axes(other["yaw_rad"]) <= other["bounds_uv"][1]))
                       for other in rows):
                    continue
                aisles.append({"yaw_rad": yaw, "bounds_uv": [[float(start), float(a[1, 1])],
                                                            [float(end), float(b[0, 1])]], "z_m": floor["z_m"]})
    return pad, edges, aisles


def floor_and_walls(points, directions, reliable, yaw, dock):
    ground_band = (dock[2] if dock else np.quantile(points[:, 2], .06)) + .24
    flat = reliable & (np.abs(directions[:, 2]) >= .9) & (points[:, 2] <= ground_band)
    ground = points[flat]
    if len(ground) < 120:
        return None, []
    basis = axes(yaw)
    floor_uv = ground[:, :2] @ basis
    lo, hi = np.quantile(floor_uv, [.015, .985], axis=0)
    z0 = float(np.median(ground[:, 2]))
    floor = {"yaw_rad": yaw, "bounds_uv": [lo.tolist(), hi.tolist()], "z_m": z0, "support_points": len(ground)}
    local = points[:, :2] @ basis
    local_normal = directions[:, :2] @ basis
    walls = []
    for axis in (0, 1):
        along = 1 - axis
        vertical = reliable & (np.abs(local_normal[:, axis]) > .92) & (points[:, 2] > z0 + .20)
        for edge in (lo[axis], hi[axis]):
            candidate = vertical & (np.abs(local[:, axis] - edge) <= 1.2)
            offsets = local[candidate, axis]
            if len(offsets) < 90:
                continue
            bins = np.arange(edge - 1.25, edge + 1.30, .08)
            counts = np.histogram(offsets, bins)[0]
            peaks = find_peaks(np.r_[0, counts, 0], height=36, distance=3)[0] - 1
            if not len(peaks):
                continue
            peak = bins[peaks[counts[peaks].argmax()]] + .04
            narrow = candidate & (np.abs(local[:, axis] - peak) < .11)
            lows, highs = np.quantile(local[narrow, along], [.04, .96])
            bottom, top = np.quantile(points[narrow, 2], [.06, .94])
            if highs - lows < 3 or top - bottom < 1.8 or bottom > z0 + 1.3:
                continue
            fixed = float(np.median(local[narrow, axis]))
            covered = np.unique(np.floor((local[narrow, along] - lows) / .35).astype(int))
            # An edge span needs distributed support, rather than just two clusters.
            if len(covered) < .65 * (highs - lows) / .35:
                continue
            endpoints = np.empty((2, 2))
            endpoints[:, axis] = fixed
            endpoints[:, along] = [lows, highs]
            walls.append({"endpoints_xy": (endpoints @ basis.T).tolist(), "z_m": z0,
                          "display_height_m": min(.50, .22 * float(top - bottom)),
                          "observed_z_m": [float(bottom), float(top)], "support_points": int(narrow.sum())})
    return floor, walls


def completion(points, rows, detail, detail_normals, dock=None, route=None, trace=None):
    if len(points) >= 120:
        directions, reliable = normals(points)
        floor, walls = floor_and_walls(points, directions, reliable, rows[0]["yaw_rad"] if rows else 0., dock)
    else:
        floor, walls = None, []
    ground = floor["z_m"] if floor else None
    templates = [fit_rack(row, ground, detail, detail_normals) for row in rows]
    pad, route_edges, aisle = calibrated_layout(dock, route, trace, floor, templates)
    return {"rows": templates, "floor": floor, "walls": walls, "aisles": aisle,
            "dock": pad, "route_edges_m": route_edges,
            "route_source": ("archived_graph" if route and route["edges"] else "recorded_trajectory") if route_edges else None}


def estimated_hit(rows, tree, origin, ray):
    candidates = []
    for row in rows:
        basis = axes(row["yaw_rad"])
        u, v = origin[:2] @ basis
        du, dv = ray[:2] @ basis
        lo, hi = np.asarray(row["observed_bounds_uv"])
        if v < lo[1] and dv > .23:
            face = lo[1]
        elif v > hi[1] and dv < -.23:
            face = hi[1]
        else:
            continue
        distance = (face - v) / dv
        along = u + distance * du
        hit = origin + distance * ray
        if not .25 <= distance <= 8 or not lo[0] <= along <= hi[0]:
            continue
        levels = [(i, z) for i, z in enumerate(row["levels_m"], 1) if abs(hit[2] - z) <= .27]
        if len(levels) != 1:
            continue
        candidates.append((row, distance, hit, levels[0][0]))
    if len(candidates) != 1:
        return None
    row, distance, hit, index = candidates[0]
    nearby = tree.query_ball_point(hit, .62)
    if len(nearby) < 4 or tree.query(hit)[0] > .31:
        return None
    return {"rack_id": row["id"], "level": index, "position_m": hit.tolist(),
            "distance_m": float(distance), "support_nearby": len(nearby),
            "reason": "Decoded marker ray meets a unique fitted rack face near recorded returns."}


def generate_twin(folder, camera, label, source):
    started = perf_counter()
    manifest = read_json(folder / "locations.json")
    if manifest["frame"] != FRAME:
        raise ValueError(f"Expected measured frame {FRAME}.")
    path = folder / "map.ply"
    measured = read_ply(path)
    points = measured.astype(float)
    if np.abs(points).max() > 10000:
        raise ValueError("Measured coordinates exceed the supported local frame extent.")
    rows, quality = reconstruct(points)
    for i, row in enumerate(rows, 1):
        row["id"] = f"R{i:02d}"
    npz = folder / "localization.npz"
    dock_npz, frames = load(npz) if npz.is_file() else (None, None)
    archive, camera_frame = archive_details(folder, manifest, frames)
    if camera and camera_frame and camera["frame"] != camera_frame:
        raise ValueError("The selected camera profile disagrees with the archived sensor frame.")
    route = read_json(folder / "route.json") if (folder / "route.json").is_file() else None
    result = read_json(folder / "result.json") if (folder / "result.json").is_file() else {}
    if result and (result["frame"] != FRAME or result["mapping_id"] != archive["mapping_id"]):
        raise ValueError("The recorded dock belongs to another map or coordinate frame.")
    dock = result.get("dock")
    if dock is not None and (np.asarray(dock).shape != (3,) or not np.isfinite(dock).all()):
        raise ValueError("The recorded dock pose is invalid.")
    detail, detail_normals = np.empty((0, 3)), np.empty((0, 3))
    evidence = None
    if source == "combined" and frames:
        if dock is not None and not np.allclose(dock, dock_npz, atol=.15):
            raise ValueError("Archived dock anchors disagree.")
        dock = dock if dock is not None else dock_npz.tolist()
        detail, detail_normals, evidence = keyframe_voxels(frames, points)
    if dock is None and route and route["nodes"] and route["nodes"][0]["type"] == "DOCK":
        dock = pose(route["nodes"][0])[0].tolist()
    twin = completion(points, rows, detail, detail_normals, dock, route, result.get("trajectory"))
    baseline = locations(folder, manifest, camera, rows, points)
    fitted = locations(folder, manifest, camera, rows, points,
                       partial(estimated_hit, twin["rows"], cKDTree(np.vstack((points, detail)))))
    twin.update(source="ply+npz" if evidence else "ply", keyframes=evidence, locations=fitted)
    return {"version": 1, "label": label, "archive": archive, "point_count": len(measured),
            "map_sha256": sha256(path.read_bytes()).hexdigest(), "points_f32le": encode(measured.tobytes()),
            "grid_m": GRID, "rows": rows, "quality": quality, "locations": baseline, "enhanced": twin}, perf_counter() - started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--label")
    parser.add_argument("--camera-calibration", type=Path)
    parser.add_argument("--source", choices=("ply", "combined"), default="combined")
    args = parser.parse_args()
    try:
        camera = read_json(args.camera_calibration) if args.camera_calibration else None
        result, seconds = generate_twin(args.archive, camera, args.label or args.archive.name, args.source)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
        print(f'{result["point_count"]} points · {len(result["enhanced"]["rows"])} rack rows'
              f' · {result["enhanced"]["source"]} · {seconds:.2f} s')
    except (OSError, ValueError, KeyError, cv2.error) as error:
        parser.exit(1, f"Digital twin export failed: {error}\n")


if __name__ == "__main__":
    main()
