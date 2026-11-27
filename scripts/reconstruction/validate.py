#!/usr/bin/env python3
"""Compare completed reconstruction bundles against project warehouse visuals."""
import argparse
from base64 import b64decode
from hashlib import sha256
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

from rackonaut_control.reconstruction.geometry import reconstruct
from rackonaut_control.reconstruction.reconstruct import MARKERS, Inspector, load_markers, read_json


def xyz(element):
    pose = element.find("pose")
    if pose is None:
        return np.zeros(3)
    values = np.fromstring(pose.text,sep=" ")
    if (len(values) != 6 or np.any(values[3:]) or pose.get("relative_to")
            or pose.get("frame")):
        raise ValueError("Expected the generated, axis-aligned Rackonaut warehouse world.")
    return values[:3]


def reference(world, assets):
    detector = Inspector(*load_markers(MARKERS))
    rows, markers = {}, {}
    for model in ET.parse(world).findall("world/model"):
        name = model.get("name")
        if not re.fullmatch(r"rack_row_\d+",name):
            continue
        lower, upper, levels = [], [], []
        for link in model.findall("link"):
            parent = xyz(model)+xyz(link)
            for visual in link.findall("visual"):
                key = visual.get("name")
                if key.startswith(("post_","deck_")):
                    p = parent+xyz(visual)
                    half = np.fromstring(visual.findtext("geometry/box/size"),sep=" ")/2
                    if key.startswith("post_"):
                        lower.append(p-half)
                        upper.append(p+half)
                    else:
                        levels.append(round(float(p[2]+half[2]), 6))
                elif assets and re.fullmatch(r"slot_\d+",key):
                    texture = assets / "materials/textures" / f"{key}.png"
                    image = cv2.imread(str(texture))
                    if image is None:
                        continue
                    for tag in detector.detect(image):
                        if tag.kind == "slot":
                            # The generated unit placard lies in world XZ with
                            # increasing U to +X and increasing V to +Z.
                            u,v = (tag.corners.mean(axis=0)+.5)/image.shape[1::-1]
                            label = parent+xyz(visual)
                            size = np.fromstring(visual.findtext("geometry/mesh/scale"),sep=" ")
                            marker = label + size * np.array([u-.5,0.,.5-v])
                            markers[tag.name] = {"row":name, "placard":label, "marker":marker}
        if not lower or not levels:
            raise ValueError(f"Cannot verify reference uprights and levels for {name}.")
        rows[name] = (np.min(lower,axis=0), np.max(upper,axis=0), sorted(set(levels)))
    if not rows:
        raise ValueError("No reference rack rows were found.")
    return rows,markers


def metres(row):
    lo,hi = np.asarray(row["bounds_uv"])
    theta = row["yaw_rad"]
    c,s = np.cos(theta),np.sin(theta)
    basis = np.array([[c,-s],[s,c]])
    return (lo+hi)/2 @ basis.T, hi-lo, basis


def angle_error(theta, target=0.):
    return abs(float(np.degrees((theta-target+np.pi/2)%np.pi-np.pi/2)))


def compare(bundle, references, markers):
    points = np.frombuffer(b64decode(bundle["points_f32le"]),dtype="<f4").reshape(-1,3).astype(float)
    measured = cKDTree(points)
    rows = bundle["rows"]
    truth = list(references)
    centers = np.asarray([metres(row)[0] for row in rows]).reshape(-1,2)
    target = np.asarray([(lo[:2]+hi[:2])/2 for lo,hi,_ in references.values()])
    # Match by cross-row position. The full-length centroid is biased towards
    # unobserved bays and unsuitable as the row association criterion.
    distance = np.abs(centers[:,None,1]-target[None,:,1])
    matched, assignments = [], {}
    for i,j in zip(*linear_sum_assignment(distance)):
        row = rows[i]
        if distance[i,j] > 1.5 or angle_error(row["yaw_rad"]) > 12:
            continue
        key = truth[j]
        lo,hi,levels = references[key]
        centre,dim,basis = metres(row)
        ob,oe = np.asarray(row["bounds_uv"])
        bounds = np.asarray([[u,v] for u in (ob[0],oe[0]) for v in (ob[1],oe[1])]) @ basis.T
        start,end = bounds[:,0].min(),bounds[:,0].max()
        if min(end,hi[0])-max(start,lo[0]) < .50*(end-start):
            continue
        assignments[row["id"]] = key
        patches = []
        errors = []
        for level in row["levels"]:
            z = level["z"]
            errors.append(z-min(levels,key=lambda v:abs(v-z)))
            for a,b,c,d in level["patches_uv"]:
                xy=np.array([(a+c)/2,(b+d)/2]) @ basis.T
                patches.append([*xy,z])
        residual = measured.query(patches)[0]
        depth, length = float(dim[1]),float(dim[0])
        matched.append({"row":row["id"], "world_row":key,
                        "centre_error_xy_m": (centre-target[j]).tolist(),
                        "yaw_error_deg":angle_error(row["yaw_rad"]),
                        "dimensions_observed_m":[length,depth,float(np.diff(row["vertical_extent_m"])[0])],
                        "dimensions_reference_m":(hi-lo).tolist(),
                        "length_fraction":length/(hi[0]-lo[0]),
                        "level_z_errors_m":errors,
                        "patch_centre_to_cloud_p50_m":float(np.median(residual)),
                        "patch_centre_to_cloud_p95_m":float(np.percentile(residual,95))})
    coverage = {}
    for name,(lo,hi,_) in references.items():
        density = np.count_nonzero(((points >= lo-[.16,.16,0]) & (points <= hi+[.16,.16,0])).all(axis=1))
        coverage[name] = {"returns_in_expanded_envelope": int(density), "reconstructed":name in assignments.values()}
    locations = []
    for item in bundle["locations"]:
        name = item["id"]
        marker = markers.get(name)
        result = {k:v for k,v in item.items() if k in {"id","status","reason","rack_id","level"}}
        if marker and item["status"] == "projected":
            hit = np.array(item["position_m"])
            result.update(world_row=assignments.get(item["rack_id"]), correct_row=assignments.get(item["rack_id"])==marker["row"],
                          error_to_marker_m=float(np.linalg.norm(hit-marker["marker"])),
                          error_to_placard_centre_m=float(np.linalg.norm(hit-marker["placard"])))
        locations.append(result)
    return {"archive":bundle["archive"], "points":len(points),"map_sha256":bundle["map_sha256"],
            "detected":len(rows),"world_rows":len(references),"matched":matched,
            "false_positives":len(rows)-len(assignments),"coverage":coverage,"locations":locations}


def perturb(bundle):
    points = np.frombuffer(b64decode(bundle["points_f32le"]),dtype="<f4").reshape(-1,3).astype(float)
    rows = bundle["rows"]
    if not rows:
        return []
    removed = rows[0]
    _,_,basis = metres(removed)
    lo,hi = np.asarray(removed["bounds_uv"])
    in_band = (((points[:,:2] @ basis) >= lo-[2,.35]) & ((points[:,:2] @ basis) <= hi+[2,.35])).all(axis=1)
    without_row = points[~(in_band & (points[:,2] < removed["vertical_extent_m"][1]+.30))]
    low_slice = points[points[:,2] < np.quantile(points[:,2], .2)+1.25]
    angle = np.deg2rad(27)
    c,s = np.cos(angle),np.sin(angle)
    shifted = points.copy()
    shifted[:,:2] = (points[:,:2] @ np.array([[c,s],[-s,c]])) + [8.,-4.]
    results = []
    for name,sample in (("remove one observed row",without_row),("partial low scan",low_slice),
                        ("rotate 27 degrees and translate",shifted)):
        found,detail = reconstruct(sample)
        results.append({"case":name,"points":len(sample),"rows":len(found),
                        "yaw_deg_mod_180":[float(np.degrees(row["yaw_rad"])) for row in found],
                        "detail":detail})
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world",type=Path,required=True)
    parser.add_argument("--warehouse-assets",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("bundles",type=Path,nargs="+")
    args=parser.parse_args()
    references,markers=reference(args.world,args.warehouse_assets)
    bundles=[read_json(b) for b in args.bundles]
    report={"world_sha256":sha256(args.world.read_bytes()).hexdigest(),
            "archives":[compare(bundle,references,markers) for bundle in bundles],
            "changed_cloud_tests":perturb(max(bundles,key=lambda item:item["point_count"] if item["rows"] else 0))}
    with args.output.open("x",encoding="utf-8") as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
        stream.write("\n")


if __name__=="__main__":
    main()
