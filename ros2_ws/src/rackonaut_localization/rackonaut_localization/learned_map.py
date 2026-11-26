"""Portable LiDAR keyframes captured in the dock-anchored navigation frame."""

from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile

import numpy as np
from scipy.spatial.transform import Rotation

from rackonaut_avoidance.sensor import FULL_ROUTE_RANGE, OFFSET
from .slam import FullRouteRegistration, Keyframe


FORMAT = 1
MAP_FILE = "localization.npz"
FRAME = "rackonaut_odom"
FIELDS = {"version", "dock", "range_m", "offset", "positions", "orientations", "index", "points", "normals"}
LIMIT = 40_000_000
PLY_HEADER = re.compile(rb"ply\nformat binary_little_endian 1\.0\nelement vertex (\d+)\n"
                        rb"property float x\nproperty float y\nproperty float z\nend_header\n")


def save(path, frames, dock):
    if not frames:
        raise ValueError("No measured LiDAR keyframes are available.")
    path = Path(path)
    pending = path.with_suffix(".tmp")
    with pending.open("wb") as stream:
        np.savez(stream, version=FORMAT, dock=np.asarray(dock, dtype="<f8"),
                 range_m=FULL_ROUTE_RANGE, offset=np.asarray(OFFSET, dtype="<f8"),
                 positions=np.asarray([frame.position for frame in frames], dtype="<f8"),
                 orientations=np.asarray([frame.orientation.as_quat() for frame in frames], dtype="<f8"),
                 index=np.asarray([0, *np.cumsum([len(frame.points) for frame in frames])], dtype="<i8"),
                 points=np.vstack([frame.points for frame in frames]).astype("<f4"),
                 normals=np.vstack([frame.normals for frame in frames]).astype("<f4"))
    pending.replace(path)


def load(path):
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            if ({entry.filename for entry in entries} != {field + ".npy" for field in FIELDS}
                    or len(entries) != len(FIELDS) or sum(entry.file_size for entry in entries) > LIMIT):
                raise ValueError("Unexpected learned LiDAR archive content.")
        with np.load(path, allow_pickle=False) as archive:
            version, dock, sensor_range, offset, positions, orientations, index, points, normals = (
                archive[name] for name in ("version", "dock", "range_m", "offset", "positions", "orientations",
                                           "index", "points", "normals"))
    except (BadZipFile, TypeError, EOFError) as error:
        raise ValueError("Could not decode the learned LiDAR map.") from error
    if (version.ndim or version.item() != FORMAT or sensor_range.ndim or sensor_range.item() != FULL_ROUTE_RANGE
            or offset.shape != (3,) or not np.array_equal(offset, OFFSET) or dock.shape != (3,)
            or index.ndim != 1 or not np.issubdtype(index.dtype, np.integer)
            or not 2 <= len(index) <= FullRouteRegistration.frame_limit + 1
            or positions.shape != (len(index)-1, 3) or orientations.shape != (len(index)-1, 4)
            or points.ndim != 2 or points.shape[1] != 3 or normals.shape != points.shape
            or index[0] != 0 or index[-1] != len(points) or any(
                count < 85 or count > 4700 for count in np.diff(index))):
        raise ValueError("The learned LiDAR map does not match the full-route sensor profile.")
    if any(not np.issubdtype(array.dtype, np.floating) or not np.isfinite(array).all()
           for array in (dock, positions, orientations, points, normals)):
        raise ValueError("The learned LiDAR map contains invalid coordinates.")
    if (not np.allclose(np.linalg.norm(orientations, axis=1), 1., atol=1.e-3)
            or not np.allclose(np.linalg.norm(normals, axis=1), 1., atol=1.e-3)
            or np.min(np.linalg.norm(positions - dock, axis=1)) > .18):
        raise ValueError("The learned LiDAR map lacks valid normals, attitudes or dock coverage.")
    frames = tuple(Keyframe(position, Rotation.from_quat(quaternion), points[begin:end], normals[begin:end])
                   for position, quaternion, begin, end in zip(positions, orientations, index, index[1:]))
    return dock, frames


def read_ply(path):
    with path.open("rb") as stream:
        header = b"".join(stream.readline(128) for _ in range(7))
        match = PLY_HEADER.fullmatch(header)
        if not match or not 1 <= int(match[1]) <= 80_000:
            raise ValueError("Unexpected measured PLY format.")
        count = int(match[1])
        payload = stream.read(count * 12 + 1)
    if len(payload) != count * 12:
        raise ValueError("The measured PLY file is incomplete.")
    points = np.frombuffer(payload, dtype="<f4").reshape(-1, 3)
    if not np.isfinite(points).all():
        raise ValueError("The measured PLY contains invalid coordinates.")
    return points
