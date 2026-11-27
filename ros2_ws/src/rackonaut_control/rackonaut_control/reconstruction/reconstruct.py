#!/usr/bin/env python3
"""Export a visualization-only Rackonaut calibration bundle."""
import argparse
from base64 import b64encode
from hashlib import sha256
import json
from pathlib import Path
import re
from time import perf_counter

from ament_index_python.packages import get_package_share_path
import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from rackonaut_localization.learned_map import FRAME, load, read_ply
from rackonaut_perception.vision import Inspector, load_markers

from .geometry import GRID, reconstruct


MARKERS = get_package_share_path("rackonaut_warehouse") / "config/control_markers.json"
PHOTO = re.compile(r"locations/CAP-[0-9A-F]{32}/reference\.jpg")


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def encode(data):
    return b64encode(data).decode("ascii")


def display_points(measured):
    if len(measured) <= 80000:
        return measured
    return measured[np.linspace(0, len(measured) - 1, 80000, dtype=int)]


def pose(record):
    origin = np.asarray(record["position_m"], dtype=float)
    attitude = np.asarray(record["orientation_xyzw"], dtype=float)
    if (origin.shape != (3,) or attitude.shape != (4,) or not np.isfinite(origin).all()
            or not np.isclose(np.linalg.norm(attitude), 1., atol=.001)):
        raise ValueError("Invalid calibrated viewpoint.")
    return origin, Rotation.from_quat(attitude)


def projected_hits(origin, ray, points, rows):
    for row in rows:
        theta = row["yaw_rad"]
        c,s = np.cos(theta),np.sin(theta)
        rotation = np.array([[c,-s],[s,c]])
        lo,hi = np.asarray(row["bounds_uv"])
        u,v = origin[:2] @ rotation
        du,dv = ray[:2] @ rotation
        # Consider only the entering face of a row outside the camera.
        if v < lo[1] and dv > .18:
            face = lo[1]
        elif v > hi[1] and dv < -.18:
            face = hi[1]
        else:
            continue
        distance = (face-v)/dv
        along = u+distance*du
        height = origin[2]+distance*ray[2]
        if not .25 <= distance <= 8 or not lo[0] <= along <= hi[0]:
            continue
        heights = [(i, level) for i,level in enumerate(row["levels"],1) if abs(height-level["z"]) <= .32]
        if not heights:
            continue
        hit = origin + distance*ray
        near = points[np.linalg.norm(points - hit, axis=1) <= .32]
        local = near[:,:2] @ rotation
        face_returns = local[np.abs(local[:,1]-face) <= .19,1]
        if len(face_returns) < 4:
            continue
        # A vertical beam may be measured even when its shelf is occluded.
        # Keep an independently supported face assignment and omit the level
        # unless measured shelf cells also cover the local neighbourhood.
        supported_levels = [i for i, level in heights
                            if any(p[0]-2*GRID <= along <= p[2]+2*GRID for p in level["patches_uv"])]
        distance = (np.median(face_returns)-v)/dv
        hit = origin + distance*ray
        yield {"rack_id": row["id"], "level": supported_levels[0] if len(supported_levels)==1 else None,
               "position_m": hit.tolist(), "distance_m": float(distance), "support_nearby": len(face_returns)}


def locations(folder, manifest, camera, rows, points, estimate=None):
    detector = Inspector(*load_markers(MARKERS)) if camera else None
    output = []
    for record in manifest.get("locations", []):
        origin, attitude = pose(record)
        name = record["storage_location_id"]
        item = {"id": name, "viewpoint_m": origin.tolist(), "status": "unplaced"}
        output.append(item)
        photo = record["reference_image"]
        path = folder / photo
        image = None
        if PHOTO.fullmatch(photo) and path.is_file() and path.stat().st_size < 1_000_000:
            data = path.read_bytes()
            image = cv2.imdecode(np.frombuffer(data,dtype=np.uint8),cv2.IMREAD_COLOR)
            if image is not None:
                item["photo_jpeg"] = encode(data)
        if not detector or camera["frame"] != record.get("camera_frame"):
            item["reason"] = "Camera calibration is unavailable for this frame."
            continue
        if image is None or tuple(image.shape[1::-1]) != tuple(camera["size_px"]):
            item["reason"] = "The recorded photo does not match the calibrated camera."
            continue
        matches = [tag for tag in detector.detect(image) if tag.kind == "slot" and tag.name == name]
        if len(matches) != 1:
            item["reason"] = "The photo does not contain one decoded ArUco marker for this location."
            continue
        xy = matches[0].corners.mean(axis=0)
        fx,fy,cx,cy = camera["intrinsics"]
        optical = np.array([(xy[0]-cx)/fx,(xy[1]-cy)/fy,1.])
        local_rotation = Rotation.from_quat(camera["orientation_in_body_xyzw"])
        origin = origin + attitude.apply(camera["position_in_body_m"])
        ray = attitude.apply(local_rotation.apply(optical/np.linalg.norm(optical)))
        hits = list(projected_hits(origin,ray,points,rows))
        item["marker_pixel"] = xy.tolist()
        if len(hits) == 1:
            item.update(hits[0], status="projected", camera_origin_m=origin.tolist())
        elif not hits and estimate and (hit := estimate(origin, ray)):
            item.update(hit, status="estimated", camera_origin_m=origin.tolist())
        else:
            item["reason"] = ("The marker ray intersects more than one supported rack face."
                              if hits else "No observed rack face supports the marker ray.")
    return output


def archive_details(folder, manifest, keyframes=None):
    meta = {"mapping_id": manifest["mapping_id"], "frame": manifest["frame"]}
    camera_frame = None
    if (folder / "sensors.json").is_file():
        sensors = read_json(folder / "sensors.json")
        meta["lidar"] = sensors["lidar"]
        camera_frame = sensors["camera"]["frame"]
    if (folder / "localization.npz").is_file():
        frames = keyframes if keyframes is not None else load(folder / "localization.npz")[1]
        meta["keyframes"] = len(frames)
        meta["keyframe_returns"] = sum(len(frame.points) for frame in frames)
    if (folder / "route.json").is_file():
        route = read_json(folder / "route.json")
        if route["frame"] != FRAME or route["mapping_id"] != meta["mapping_id"]:
            raise ValueError("The route belongs to another map or coordinate frame.")
        meta["route_waypoints"] = len(route["nodes"])
    return meta,camera_frame


def generate(folder, camera, label):
    started = perf_counter()
    manifest = read_json(folder / "locations.json")
    if manifest["frame"] != FRAME:
        raise ValueError(f"Expected measured frame {FRAME}.")
    archive,camera_frame = archive_details(folder,manifest)
    if camera and camera_frame and camera["frame"] != camera_frame:
        raise ValueError("The selected camera profile disagrees with the archived sensor frame.")
    path = folder / "map.ply"
    measured = read_ply(path)
    points = measured.astype(float)
    if np.abs(points).max() > 10000:
        raise ValueError("Measured coordinates exceed the supported local frame extent.")
    result_file = folder / "result.json"
    result = read_json(result_file) if result_file.is_file() else {}
    rows,quality = reconstruct(points, include_partial=result.get("multi_sortie") is True)
    for i,row in enumerate(rows,1):
        row["id"] = f"R{i:02d}"
    measured = display_points(measured)
    return {"version":1, "label":label, "archive":archive, "point_count":len(measured),
            "map_sha256":sha256(path.read_bytes()).hexdigest(),
            "points_f32le":encode(measured.tobytes()), "grid_m":GRID,
            "rows":rows, "quality":quality,
            "locations":locations(folder,manifest,camera,rows,points)}, perf_counter()-started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--label")
    parser.add_argument("--camera-calibration", type=Path, help="Verified camera profile for projecting ArUco markers.")
    args = parser.parse_args()
    try:
        camera = read_json(args.camera_calibration) if args.camera_calibration else None
        result,seconds = generate(args.archive,camera,args.label or args.archive.name)
        # Write to a separate local path. Refuse to overwrite any input file.
        with args.output.open("x",encoding="utf-8") as stream:
            json.dump(result,stream,ensure_ascii=False,separators=(",",":"),allow_nan=False)
            stream.write("\n")
        print(f"{result['point_count']} points · {len(result['rows'])} rack candidates · {seconds:.2f} s")
    except (OSError, ValueError, KeyError, cv2.error) as error:
        parser.exit(1,f"Archive reconstruction failed: {error}\n")


if __name__ == "__main__":
    main()
