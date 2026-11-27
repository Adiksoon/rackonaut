"""A bounded scan-to-submap target built exclusively from accepted LiDAR keyframes."""

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation
from rackonaut_avoidance.sensor import FULL_ROUTE_RANGE

from .registration import SurfaceRegistration, voxel_sample


@dataclass(frozen=True)
class Keyframe:
    position: np.ndarray
    orientation: Rotation
    points: np.ndarray
    normals: np.ndarray


def measured_surfaces(sample, neighbors_count=14, maximum_distance=.46, flatness=.20):
    if len(sample) < 65:
        return sample[:0], sample[:0]
    distance, neighbors = cKDTree(sample).query(sample, k=neighbors_count)
    local = sample[neighbors]
    centered = local - local.mean(axis=1, keepdims=True)
    values, axes = np.linalg.eigh(centered.transpose(0, 2, 1) @ centered / local.shape[1])
    planar = ((distance[:, -1] < maximum_distance) & (values[:, 1] > .0004)
              & (values[:, 0] < flatness * values[:, 1]))
    return sample[planar], axes[planar, :, 0]


def group_voxels(voxels):
    # Stable lexicographic order preserves the oldest point in each voxel.
    order = np.lexsort(voxels.T[::-1])
    ordered = voxels[order]
    first_in_group = np.r_[True, np.any(ordered[1:] != ordered[:-1], axis=1)]
    membership = np.empty(len(voxels), dtype=np.intp)
    membership[order] = np.cumsum(first_in_group) - 1
    return order[first_in_group], membership


def planar_voxel_support(points, normals, first, membership, weight):
    """Redistribute samples along the oldest observed plane in each voxel."""
    origin, plane = points[first], normals[first]
    reference = plane[membership]
    delta = points - origin[membership]
    alignment = np.abs(np.einsum("ij,ij->i", normals, reference))
    separation = np.abs(np.einsum("ij,ij->i", delta, reference))
    # A voxel can straddle a shelf edge or contain two parallel surfaces.
    same_plane = (alignment >= .94) & (separation <= .035)
    groups = membership[same_plane]
    counts = np.bincount(groups, minlength=len(first))
    offset = np.column_stack([np.bincount(groups, weights=axis[same_plane], minlength=len(first)) / counts
                              for axis in delta.T])
    # Preserve the plane offset even if newer keyframes carry a small pose error.
    offset -= np.einsum("ij,ij->i", offset, plane)[:, None] * plane
    return origin + weight * offset


class MeasuredRegistration:
    spacing = .24
    turn_spacing = .17
    frame_limit = 14
    discard_index = 1
    map_voxel = .075
    centroid_weight = 0.
    surface_type = SurfaceRegistration

    def __init__(self):
        self.keyframes = []
        self.keyframe_count = 0
        self.target = None

    def consider(self, raw, offset, position, orientation):
        if self.keyframes:
            previous = self.keyframes[-1]
            if (np.linalg.norm(position - previous.position) < self.spacing
                    and (orientation * previous.orientation.inv()).magnitude() < self.turn_spacing):
                return False
        points, normals = self.surfaces(raw)
        if len(points) < 85:
            return False
        frame = Keyframe(position.copy(), orientation, orientation.apply(points + offset) + position,
                         orientation.apply(normals))
        self.keyframes.append(frame)
        self.keyframe_count += 1
        if len(self.keyframes) > self.frame_limit:
            self.keyframes.pop(self.redundant_frame())
        self.rebuild_target(position)
        return True

    def redundant_frame(self):
        return self.discard_index

    def rebuild_target(self, position):
        local = self.local_frames(position)
        if not local:
            self.target = None
            return
        combined = np.vstack([entry.points for entry in local])
        normals = np.vstack([entry.normals for entry in local])
        voxels = np.floor(combined / self.map_voxel).astype(np.int32)
        if self.centroid_weight:
            indices, membership = group_voxels(voxels)
            support = planar_voxel_support(combined, normals, indices, membership, self.centroid_weight)
        else:
            _, indices = np.unique(voxels, axis=0, return_index=True)
            support = combined[indices]
        self.target = self.surface_type(support, normals[indices])

    def match(self, raw, offset, position, orientation):
        if self.target is None:
            return None
        return self.target.match(self.target.features(raw) + offset, position, orientation)

    def surfaces(self, raw):
        radius = np.linalg.norm(raw, axis=1)
        return measured_surfaces(voxel_sample(raw[(radius >= .098) & (radius <= 5.8)], .095, 1800))

    def local_frames(self, position):
        return [entry for entry in self.keyframes if np.linalg.norm(entry.position - position) <= 4.]


class SurveySurfaces(SurfaceRegistration):
    iterations = 8
    regularization = (.007, .007, .007, .011, .011, .016)

    def features(self, sensor_points):
        radius = np.linalg.norm(sensor_points, axis=1)
        return voxel_sample(sensor_points[(radius >= .098) & (radius <= FULL_ROUTE_RANGE - .05)], .10, 3000)

    def support(self, distance, residual, normals, mapped, beam_range):
        # Distant beams are more sparsely sampled in the tangent plane.
        allowance = np.minimum(.83, .19 + .027 * beam_range)
        close = (distance < allowance) & (np.abs(residual) < .10)
        n = normals[close]
        weights = np.minimum(1., .014 / np.maximum(np.abs(residual[close]), 1.e-6))
        weights *= np.maximum(.15, 1. - distance[close] / allowance[close])
        incidence = np.abs(np.einsum("ij,ij->i", n, mapped[close])) / beam_range[close]
        weights *= np.maximum(.14, incidence) ** .65
        directions = np.argmax(np.abs(n), axis=1)
        counts = np.bincount(directions, minlength=3)
        # Keep the dominant wall or floor from overwhelming transverse returns.
        weights *= np.clip((len(n) / (3 * np.maximum(1, counts[directions]))) ** .32, .45, 2.1)
        return close, weights


class FullRouteRegistration(MeasuredRegistration):
    spacing = .37
    turn_spacing = .20
    frame_limit = 240
    discard_index = 0
    map_voxel = .10
    centroid_weight = .18
    surface_type = SurveySurfaces

    def surfaces(self, raw):
        radius = np.linalg.norm(raw, axis=1)
        sample = voxel_sample(raw[(radius >= .098) & (radius <= FULL_ROUTE_RANGE - .05)], .10, 4700)
        maximum_distance = np.clip(.18 + .17 * np.linalg.norm(sample, axis=1), .35, 2.3)
        return measured_surfaces(sample, neighbors_count=16, maximum_distance=maximum_distance, flatness=.12)

    def local_frames(self, position):
        ranked = sorted(((np.linalg.norm(entry.position - position), index, entry)
                         for index, entry in enumerate(self.keyframes)), key=lambda item: item[:2])
        # Preserve the earliest observation and its normal for each overlapping voxel.
        ordered = sorted((index, entry) for distance, index, entry in ranked[:60] if distance <= 12.)
        return [entry for _, entry in ordered]


class FullWarehouseRegistration(FullRouteRegistration):
    """Retain coverage for all visited areas while matching the same local window."""

    frame_limit = 480

    def redundant_frame(self):
        # Approximate local density in position and viewing direction. Keep
        # the original dock anchor and the most recent frame in every window.
        positions = np.stack([frame.position for frame in self.keyframes])
        rotations = np.stack([frame.orientation.as_quat() for frame in self.keyframes])
        vicinity = np.linalg.norm(positions - positions[-1], axis=1)
        candidates = np.flatnonzero(vicinity[:-1] <= 1.2)
        candidates = candidates[candidates > 0]
        if not len(candidates):
            candidates = np.arange(1, len(positions) - 1)
        distances = np.linalg.norm(positions[candidates, None] - positions[None, :], axis=2)
        same_view = np.abs(rotations[candidates] @ rotations.T) >= .97
        population = np.sum((distances <= .8) & same_view, axis=1)
        return int(candidates[np.argmax(population)]) if population.max() > 1 else len(positions) - 1


class FrozenRegistration(FullRouteRegistration):
    """Match to the saved survey. Live scans can never modify the target."""

    def __init__(self, frames, dock):
        super().__init__()
        self.keyframes = tuple(frames)
        self.keyframe_count = len(self.keyframes)
        self.center = dock.copy()
        self.rebuild_target(dock)

    def consider(self, raw, offset, position, orientation):
        return False

    def match(self, raw, offset, position, orientation):
        if np.linalg.norm(position - self.center) >= .85:
            self.center = position.copy()
            self.rebuild_target(position)
        return super().match(raw, offset, position, orientation)
