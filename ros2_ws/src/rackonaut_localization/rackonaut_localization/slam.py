"""A bounded scan-to-submap target built exclusively from accepted LiDAR keyframes."""

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from .registration import SurfaceRegistration, voxel_sample


@dataclass(frozen=True)
class Keyframe:
    position: np.ndarray
    orientation: Rotation
    points: np.ndarray
    normals: np.ndarray


def measured_surfaces(points):
    radius = np.linalg.norm(points, axis=1)
    sample = voxel_sample(points[(radius >= .098) & (radius <= 5.8)], .095, 1800)
    if len(sample) < 65:
        return sample[:0], sample[:0]
    distance, neighbors = cKDTree(sample).query(sample, k=14)
    local = sample[neighbors]
    centered = local - local.mean(axis=1, keepdims=True)
    values, axes = np.linalg.eigh(centered.transpose(0, 2, 1) @ centered / local.shape[1])
    planar = ((distance[:, -1] < .46) & (values[:, 1] > .0004)
              & (values[:, 0] < .20 * values[:, 1]))
    return sample[planar], axes[planar, :, 0]


class MeasuredRegistration:
    def __init__(self):
        self.keyframes = []
        self.keyframe_count = 0
        self.target = None

    def consider(self, raw, offset, position, orientation):
        if self.keyframes:
            previous = self.keyframes[-1]
            if (np.linalg.norm(position - previous.position) < .24
                    and (orientation * previous.orientation.inv()).magnitude() < .17):
                return False
        points, normals = measured_surfaces(raw)
        if len(points) < 85:
            return False
        frame = Keyframe(position.copy(), orientation, orientation.apply(points + offset) + position,
                         orientation.apply(normals))
        self.keyframes.append(frame)
        self.keyframe_count += 1
        if len(self.keyframes) > 14:
            self.keyframes.pop(1)
        # Retain the installation observations for revisits without making
        # distant keyframes a local matching candidate.
        local = [entry for entry in self.keyframes if np.linalg.norm(entry.position - position) <= 4.]
        combined = np.vstack([entry.points for entry in local])
        normals = np.vstack([entry.normals for entry in local])
        _, indices = np.unique(np.floor(combined / .075).astype(np.int32), axis=0, return_index=True)
        self.target = SurfaceRegistration(combined[indices], normals[indices])
        return True

    def match(self, raw, offset, position, orientation):
        if self.target is None:
            return None
        return self.target.match(self.target.features(raw) + offset, position, orientation)
