"""Fit rack envelopes to repeated, measured horizontal surfaces."""

from dataclasses import dataclass
from itertools import combinations

import numpy as np
from scipy.ndimage import binary_dilation, gaussian_filter1d, label
from scipy.signal import find_peaks
from scipy.spatial import cKDTree

# map.ply is already a 0.16 m voxel map. The coarser analysis grid tolerates
# a missing voxel between returns and is never used to add points to the cloud.
GRID = .24
Z_BIN = .08
Z_BAND = .13
MIN_LENGTH = 2.5
MIN_CELLS = 24


@dataclass
class Surface:
    xyz: np.ndarray
    lo: np.ndarray
    hi: np.ndarray
    cells: int
    height: float


def normals(points):
    distances, indices = cKDTree(points).query(points, k=12)
    neighbours = points[indices]
    centred = neighbours - neighbours.mean(axis=1, keepdims=True)
    values, directions = np.linalg.eigh(centred.transpose(0, 2, 1) @ centred / 12)
    reliable = (distances[:, -1] <= .55) & (values[:, 0] < .22 * values[:, 1]) & (values[:, 1] > .004)
    return directions[:, :, 0], reliable


def horizontal_axes(directions):
    vertical = directions[np.abs(directions[:, 2]) < .25]
    if len(vertical) < 40:
        return None
    angles = np.arctan2(vertical[:, 1], vertical[:, 0])
    axial = np.exp(4j * angles)
    coarse = np.angle(axial.mean()) / 4
    deviations = ((angles - coarse + np.pi / 4) % (np.pi / 2)) - np.pi / 4
    aligned = np.abs(deviations) < np.deg2rad(12)
    if aligned.sum() < 40 or aligned.mean() < .34:
        return None
    return coarse + np.median(deviations[aligned])


def raster_components(xy):
    cells = np.floor(xy / GRID).astype(int)
    start = cells.min(axis=0)
    local = cells - start
    shape = local.max(axis=0) + 1
    if np.prod(shape, dtype=np.int64) > 2_000_000:
        raise ValueError("Point cloud extent is too large for the reconstruction grid.")
    raster = np.zeros(shape, dtype=bool)
    raster[tuple(local.T)] = True
    # Connect small gaps, then cluster only the original occupied cells.
    groups, count = label(binary_dilation(raster, structure=np.ones((3, 3), dtype=bool)))
    ids = groups[tuple(local.T)]
    for i in range(1, count + 1):
        mask = ids == i
        occupied = len(np.unique(cells[mask], axis=0))
        if occupied >= MIN_CELLS:
            yield mask, occupied


def surfaces(horizontal_points, rotation):
    projected = horizontal_points.copy()
    projected[:, :2] = projected[:, :2] @ rotation
    z = projected[:, 2]
    levels = np.arange(np.floor(z.min() / Z_BIN) * Z_BIN - Z_BIN, z.max() + 2*Z_BIN, Z_BIN)
    votes = gaussian_filter1d(np.histogram(z, bins=levels)[0].astype(float), .85)
    peaks, _ = find_peaks(votes, height=22, prominence=10, distance=4)
    for i in peaks:
        slab = projected[np.abs(z - (levels[i] + Z_BIN/2)) <= Z_BAND]
        if len(slab) < MIN_CELLS:
            continue
        for mask, occupied in raster_components(slab[:, :2]):
            sample = slab[mask]
            lo, hi = np.quantile(sample[:, :2], [.02, .98], axis=0)
            length, depth = hi-lo
            if length >= MIN_LENGTH and .25 <= depth <= 3. and length >= 2.4*depth:
                yield Surface(sample, lo, hi, occupied, float(np.median(sample[:, 2])))


def overlap(a, b):
    common = np.minimum(a.hi, b.hi) - np.maximum(a.lo, b.lo)
    return common / np.minimum(a.hi-a.lo, b.hi-b.lo)


def repeated_stacks(levels):
    for first, middle, last in combinations(sorted(levels, key=lambda s: s.height), 3):
        pitch = (last.height-first.height)/2
        if pitch < .58 or abs((middle.height-first.height)-pitch) > max(.12, .12*pitch):
            continue
        stack = (first, middle, last)
        if not all(np.all(overlap(a,b) >= [.53,.37]) for a,b in combinations(stack,2)):
            continue
        common = np.min([s.hi for s in stack], axis=0) - np.max([s.lo for s in stack], axis=0)
        if common[0] < 1.75:
            continue
        score = common[0] * np.cbrt(np.prod([s.cells for s in stack], dtype=float))
        yield score, stack


def extend_stack(stack, candidates):
    pitch = (stack[-1].height - stack[0].height)/2
    slots = {i: level for i, level in enumerate(stack)}
    for level in sorted(candidates, key=lambda item: -item.cells):
        offset = (level.height - stack[0].height)/pitch
        index = round(offset)
        if (index not in slots and abs(offset-index) <= .12
                and all(np.all(overlap(level, other) >= [.53,.37]) for other in stack)):
            slots[index] = level
    return [slots[i] for i in range(min(slots), max(slots)+1) if i in slots]


def upright_segments(points, lo, hi, heights):
    posts = []
    for face in (lo[1], hi[1]):
        side = points[(np.abs(points[:, 1]-face) < .22) &
                      (points[:,0] >= lo[0]-.16) & (points[:,0] <= hi[0]+.16) &
                      (points[:,2] >= heights[0]-.30) & (points[:,2] <= heights[-1]+np.median(np.diff(heights)))]
        if not len(side):
            continue
        centres = np.arange(lo[0]-.16, hi[0]+.20, .12)
        spans = []
        for centre in centres:
            nearby = side[np.abs(side[:,0]-centre) < .12]
            if len(nearby) < 10:
                spans.append(0)
                continue
            bins = np.unique(np.floor(nearby[:,2]/GRID).astype(int))
            spans.append(len(bins) if np.max(np.diff(bins), initial=0) <= 4 else 0)
        peaks = find_peaks(np.r_[0, spans, 0], height=9, distance=4)[0]-1
        for index in peaks:
            nearby = side[np.abs(side[:,0]-centres[index]) < .12]
            bottom, top = np.quantile(nearby[:,2], [.03,.97])
            if top-bottom < max(1.3, (heights[-1]-heights[0])*.55) or top < heights[-1]+.30:
                continue
            posts.append([np.median(nearby[:,0]), np.median(nearby[:,1]), bottom, top])
    return posts


def rack_geometry(stack, local_points, theta):
    heights = np.array([s.height for s in stack])
    all_points = np.vstack([s.xyz for s in stack])
    lo, hi = np.quantile(all_points[:, :2], [.012, .988], axis=0)
    posts = upright_segments(local_points, lo, hi, heights)
    if posts:
        # The deepest returns need not be a rack rear. Use the estimated post
        # envelope only where the two sides independently have support.
        post_array = np.asarray(posts)
        front = post_array[np.abs(post_array[:,1]-lo[1]) < .25,1]
        rear = post_array[np.abs(post_array[:,1]-hi[1]) < .25,1]
        if len(front) and len(rear):
            lo[1], hi[1] = np.median(front), np.median(rear)
    # Draw one strip per consecutive occupied depth interval. Empty cells
    # stay empty even where the plane envelope reaches across them.
    levels = []
    for s in stack:
        cells = np.unique(np.floor(s.xyz[:,:2]/GRID).astype(int),axis=0)
        patches = []
        for u in np.unique(cells[:,0]):
            depths = cells[cells[:,0] == u,1]
            for chunk in np.split(depths, np.flatnonzero(np.diff(depths) > 1)+1):
                low = np.maximum(lo,[u*GRID,chunk[0]*GRID])
                high = np.minimum(hi,[(u+1)*GRID,(chunk[-1]+1)*GRID])
                if np.all(high > low):
                    patches.append([*low, *high])
        levels.append({"z": s.height, "patches_uv": patches, "cells": s.cells})
    base = float(min((p[2] for p in posts), default=heights[0]))
    top = float(max((p[3] for p in posts), default=heights[-1]))
    return {"yaw_rad": theta % np.pi, "bounds_uv": [lo.tolist(), hi.tolist()], "levels": levels,
            "posts": posts, "vertical_extent_m": [min(base, heights[0]), max(top, heights[-1])],
            "height_supported_by_posts": bool(posts), "support_points": len(all_points)}


def partial_racks(planes, complete, local, theta):
    """Fit two observed shelves only when measured posts and a local rack pitch agree."""
    pitches = [float(np.median(np.diff([level.height for level in stack]))) for stack in complete]
    if not pitches:
        return
    accepted = [stack[1] for stack in complete]
    for low, high in combinations(sorted(planes, key=lambda plane: plane.height), 2):
        step = high.height - low.height
        common_length = min(low.hi[0], high.hi[0]) - max(low.lo[0], high.lo[0])
        if (not any(abs(step - pitch) <= max(.12, .12*pitch) for pitch in pitches)
                or common_length < 2 * MIN_LENGTH or not np.all(overlap(low, high) >= [.70, .65])
                or any(np.all(overlap(low, plane) >= [.45, .35]) for plane in accepted)):
            continue
        geometry = rack_geometry((low, high), local, theta)
        posts = np.asarray(geometry["posts"])
        if len(posts) < 4 or np.ptp(posts[:, 0]) < .45 * common_length:
            continue
        near, far = np.asarray(geometry["bounds_uv"])[:, 1]
        if not all(np.count_nonzero(np.abs(posts[:, 1] - side) <= .23) >= 2 for side in (near, far)):
            continue
        geometry["partial"] = True
        accepted.append(low)
        yield geometry


def reconstruct(points, include_partial=False):
    if len(points) < 120:
        return [], {"reason": "Too few measured points."}
    directions, reliable = normals(points)
    horizontal = points[reliable & (np.abs(directions[:,2]) > .91)]
    vertical = points[reliable & (np.abs(directions[:,2]) < .25)]
    angle = horizontal_axes(directions[reliable])
    if angle is None or len(horizontal) < 80:
        return [], {"reason": "No reliable alignment of measured planes."}
    rows, candidates = [], 0
    for theta in (angle, angle + np.pi/2):
        # Keep the projected basis and serialized yaw consistent.
        theta %= np.pi
        c, s = np.cos(theta), np.sin(theta)
        rotation = np.array([[c,-s],[s,c]])
        planes = list(surfaces(horizontal, rotation))
        members = sorted(repeated_stacks(planes), key=lambda row: -row[0])
        candidates += len(members)
        local = points.copy()
        local[:,:2] = local[:,:2] @ rotation
        selected = []
        for _, stack in members:
            if any(np.all(overlap(stack[1], prev[1]) >= [.45,.35]) for prev in selected):
                continue
            selected.append(stack)
            rows.append(rack_geometry(extend_stack(stack, planes), local, theta))
        if include_partial:
            rows.extend(partial_racks(planes, selected, local, theta))
    return rows, {"horizontal_points": len(horizontal), "vertical_points": len(vertical),
                  "repeated_stacks": candidates}
