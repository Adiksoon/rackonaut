"""Robust point-to-plane registration against sampled installation surfaces."""

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

MAX_POINTS = 620
SURFACE_STEP = .125
MAX_RESIDUAL = .21


def voxel_sample(points, size, limit):
    if not len(points):
        return points
    _, indices = np.unique(np.floor(points / size).astype(np.int32), axis=0, return_index=True)
    if len(indices) > limit:
        indices.sort()
        indices = indices[np.linspace(0, len(indices) - 1, limit, dtype=int)]
    return points[indices]


def box_surfaces(boxes):
    surfaces, normals = [], []
    for box in boxes:
        center, width = np.asarray(box[:3]), np.asarray(box[3:])
        low, high = center - width/2, center + width/2
        for axis in range(3):
            axes = [i for i in range(3) if i != axis]
            first, second = (np.linspace(low[i], high[i], max(2, int(np.ceil(width[i] / SURFACE_STEP))+1))
                             for i in axes)
            grid, mesh = np.meshgrid(first, second)
            face = np.zeros((grid.size, 3))
            face[:, axes[0]], face[:, axes[1]] = grid.ravel(), mesh.ravel()
            for direction, boundary in ((-1., low[axis]), (1., high[axis])):
                face[:, axis] = boundary
                normal = np.zeros_like(face)
                normal[:, axis] = direction
                surfaces.append(face.copy())
                normals.append(normal)
    return np.vstack(surfaces), np.vstack(normals)


def triangle_surfaces(triangles):
    surfaces, normals = [], []
    for a, b, c in np.asarray(triangles).reshape(-1, 3, 3):
        cross = np.cross(b-a, c-a)
        norm = np.linalg.norm(cross)
        if norm < 1.e-8:
            continue
        count = max(1, int(np.ceil(norm / (2 * SURFACE_STEP**2))))
        i = np.arange(count)
        u = np.sqrt((i+.5)/count)[:, None]
        v = np.mod(i*.61803398875, 1.)[:, None]
        face = (1.-u)*a + u*(1.-v)*b + u*v*c
        edges = [start + np.linspace(0., 1., max(2, int(np.ceil(np.linalg.norm(end-start)/SURFACE_STEP))))[:, None]
                 * (end-start) for start, end in ((a, b), (b, c), (c, a))]
        sampled = np.vstack((face, *edges))
        surfaces.append(sampled)
        normals.append(np.broadcast_to(cross/norm, sampled.shape))
    return np.vstack(surfaces), np.vstack(normals)


@dataclass(frozen=True)
class Fit:
    xyz: np.ndarray
    attitude: Rotation
    overlap: float
    rms: float
    sigma: np.ndarray
    weakest: float
    inliers: int


class SurfaceRegistration:
    iterations = 7
    regularization = (.009, .009, .008, .012, .012, .018)

    def __init__(self, points, normals):
        self.points, self.normals = points, normals
        self.tree = cKDTree(points)

    def features(self, sensor_points):
        distance = np.linalg.norm(sensor_points, axis=1)
        return voxel_sample(sensor_points[(distance >= .098) & (distance <= 5.8)], .11, MAX_POINTS)

    def support(self, distance, residual, normals, mapped, beam_range):
        close = distance < MAX_RESIDUAL
        weights = np.minimum(1., .022 / np.maximum(np.abs(residual[close]), 1.e-6))
        weights *= np.maximum(.15, 1. - distance[close] / MAX_RESIDUAL)
        return close, weights

    def match(self, points, origin, orientation):
        if len(points) < 65:
            return None
        position, attitude = np.copy(origin), orientation
        regularization = np.diag(self.regularization)
        beam_range = np.linalg.norm(points, axis=1)
        for _ in range(self.iterations):
            mapped = attitude.apply(points)
            world = mapped + position
            distance, indices = self.tree.query(world)
            support, normals = self.points[indices], self.normals[indices]
            residual = np.sum((world - support) * normals, axis=1)
            close, weights = self.support(distance, residual, normals, mapped, beam_range)
            count = np.count_nonzero(close)
            if count < 55:
                return None
            residual, normals = residual[close], normals[close]
            jacobian = np.column_stack((normals, np.cross(mapped[close], normals)))
            weighted = jacobian.T * weights
            information = weighted @ jacobian / count
            rhs = weighted @ residual / count
            correction = -np.linalg.solve(information + regularization, rhs)
            # Limit each correction so weak features cannot move the fit to a
            # different repeating frame in a single iteration.
            translation = correction[:3]
            translation *= min(1., .07 / max(1.e-6, np.linalg.norm(translation)))
            position += translation
            attitude = Rotation.from_rotvec(correction[3:]) * attitude
            if np.linalg.norm(correction) < .0006:
                break
        divergence = np.linalg.norm(position - origin)
        changed = (attitude * orientation.inv()).magnitude()
        if divergence > .30 or changed > .20:
            return None
        rms = float(np.sqrt(np.average(residual**2, weights=weights)))
        weakest = float(np.linalg.eigvalsh(information)[0])
        covariance = np.linalg.inv(information + np.eye(6)*.0015)
        sigma = np.sqrt(np.diag(covariance))[:3] * max(.003, rms / np.sqrt(38.))
        return Fit(position, attitude, count / len(points), rms, sigma, weakest, int(count))


class StaticMap(SurfaceRegistration):
    def __init__(self, boxes, triangles=()):
        points, normals = box_surfaces(boxes)
        if triangles:
            faces, face_normals = triangle_surfaces(triangles)
            points, normals = np.vstack((points, faces)), np.vstack((normals, face_normals))
        super().__init__(points, normals)
