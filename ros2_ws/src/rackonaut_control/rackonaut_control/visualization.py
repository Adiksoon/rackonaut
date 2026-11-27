"""Build revision-bound visualization artifacts outside the control loop."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Lock
from time import monotonic

from rackonaut_localization.warehouse_config import (
    CONFIG_ID, FRAME, HISTORICAL_VARIANT, SESSION_ID, STORE, active_identifier,
    check_warehouse_variant, digest, file_hash, read, verified_package,
)

from .teaching import atomic_write, session_path


ARTIFACT = "visualization.json"
FORMAT = 1
INPUTS = ("map.ply", "localization.npz", "locations.json", "result.json", "route.json", "sensors.json",
          "manifest.json")


def file_stamp(path):
    try:
        stat = path.stat()
        return stat.st_ino, stat.st_size, stat.st_mtime_ns
    except FileNotFoundError:
        return None


def sources(folder):
    return tuple(file_stamp(folder / name) for name in INPUTS)


class Visualizations:
    def __init__(self, root, camera, warehouse_variant=HISTORICAL_VARIANT):
        self.root = Path(root)
        self.warehouse_variant = warehouse_variant
        self.cameras = {"reference": camera, "x3": camera.with_name("x3-camera.json")}
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="warehouse-visualization")
        self.lock = Lock()
        self.entries = {}

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)

    def get(self, kind, identifier, revision=None, private=False):
        if kind == "warehouse" and CONFIG_ID.fullmatch(str(identifier)):
            folder = self.root / STORE / identifier
        elif kind == "calibration" and SESSION_ID.fullmatch(str(identifier)):
            folder = session_path(self.root / "mapping", identifier)
        else:
            raise FileNotFoundError("No visualization is bound to this selection.")
        stamp = sources(folder)
        if any(stamp[INPUTS.index(key)] is None for key in ("map.ply", "locations.json", "result.json")):
            raise FileNotFoundError("The selected calibration has no complete measured inputs.")
        key = kind, identifier
        with self.lock:
            entry = self.entries.get(key)
            artifact = folder / ARTIFACT
            current = file_stamp(artifact)
            recheck = False
            if entry and entry[1].done():
                recheck = (monotonic() - entry[2] > 20 if entry[1].exception()
                           else entry[1].result()[3] != current)
            if not entry or entry[0] != stamp or recheck:
                task = self.pool.submit(self.build, kind, identifier, folder, stamp)
                entry = self.entries[key] = stamp, task, monotonic()
                # Keep decoded artifacts for recently requested screens only.
                while len(self.entries) > 8:
                    previous = next((k for k, value in self.entries.items() if k != key and value[1].done()), None)
                    if previous is None:
                        break
                    del self.entries[previous]
            task = entry[1]
        if not task.done():
            return None
        try:
            result, operator, service, _ = task.result()
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            raise RuntimeError(f"Warehouse visualization could not be prepared. {error}") from error
        if revision is not None and result["revision"] != revision:
            raise FileNotFoundError("The saved visualization does not match the mission revision.")
        return service if private else operator

    def prime(self, kind, identifier):
        if identifier:
            try:
                self.get(kind, identifier)
            except (OSError, ValueError, RuntimeError):
                # Ready/pending/error are reported by the read API. Visualization
                # availability never changes a calibration or dispatch decision.
                pass

    def camera_for(self, folder):
        result = read(folder / "result.json")
        model = result.get("drone_model", "reference")
        profile = self.cameras.get(model) if isinstance(model, str) else None
        if profile is None or not profile.is_file():
            return None, None
        path = folder / "sensors.json"
        if path.is_file():
            sensors, calibration = read(path), read(profile)
            camera = sensors.get("camera") or {}
            if (sensors.get("drone_model", "reference") != model or not isinstance(camera, dict)
                    or camera.get("frame") != calibration["frame"]
                    or camera.get("position_m", calibration["position_in_body_m"] if model == "reference" else None)
                    != calibration["position_in_body_m"]):
                return None, None
        return model, profile

    def build(self, kind, identifier, folder, stamp):
        if kind == "warehouse":
            _, manifest = verified_package(self.root, identifier)
            mapping = manifest["mapping_id"]
            revision, name = manifest["revision"], manifest["name"]
            source = digest(manifest)
        else:
            manifest = read(folder / "locations.json")
            if manifest["mapping_id"] != identifier or manifest["frame"] != FRAME:
                raise ValueError("The calibration manifest disagrees with its measurement frame.")
            mapping = identifier
            revision, name = manifest["revision"], "Warehouse calibration"
            source = digest({file: file_hash(folder / file) for file in INPUTS if (folder / file).is_file()})
        camera_model, camera = self.camera_for(folder)
        binding = {"format": FORMAT, "configuration_id": identifier if kind == "warehouse" else None,
                   "mapping_id": mapping, "revision": revision, "source_sha256": source,
                   "camera_profile": camera_model, "camera_sha256": file_hash(camera) if camera else None}
        path = folder / ARTIFACT
        try:
            saved = read(path)
        except (FileNotFoundError, ValueError):
            saved = {}
        if isinstance(saved, dict) and saved.get("binding") == binding and self.valid(saved.get("model"), mapping):
            model = saved["model"]
        else:
            with TemporaryDirectory(prefix="rackonaut-twin-", dir=folder) as directory:
                output = Path(directory) / "model.json"
                command = ["nice", "-n", "10", sys.executable, "-m", "rackonaut_control.reconstruction.twin",
                           str(folder), str(output), "--label", name]
                if camera:
                    command.extend(["--camera-calibration", str(camera)])
                done = subprocess.run(command, timeout=45, check=False, capture_output=True, text=True,
                                      env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"})
                if done.returncode:
                    raise ValueError(done.stderr.strip()[-280:] or "Template exporter failed.")
                model = read(output)
            if not self.valid(model, mapping):
                raise ValueError("Invalid warehouse visualization output.")
            if sources(folder) != stamp:
                raise ValueError("Calibration changed while generating its visualization.")
            atomic_write(path, json.dumps({"binding": binding, "model": model},
                                           separators=(",", ":"), allow_nan=False).encode())
        if sources(folder) != stamp:
            raise ValueError("The visualization inputs changed during validation.")
        visuals = model["enhanced"]
        published = {**visuals, "locations": [
            {key: value for key, value in location.items() if key != "photo_jpeg"}
            for location in visuals["locations"]
        ]}
        count = model["point_count"]
        common = {"binding": binding, "name": name, "point_count": count, "points_f32le": model["points_f32le"]}
        operator = self.response({**common, "enhanced": {**published, "route_edges_m": []}})
        service = self.response({**common, "enhanced": visuals})
        return binding, operator, service, file_stamp(path)

    @staticmethod
    def valid(model, mapping):
        if not isinstance(model, dict) or model.get("version") != 1:
            return False
        archive, visuals = model.get("archive"), model.get("enhanced")
        return (isinstance(archive, dict) and archive.get("frame") == FRAME and archive.get("mapping_id") == mapping
                and isinstance(visuals, dict) and isinstance(visuals.get("locations"), list)
                and isinstance(visuals.get("rows"), list) and isinstance(model.get("points_f32le"), str)
                and type(model.get("point_count")) is int and 1 <= model["point_count"] <= 80000)

    @staticmethod
    def response(value):
        body = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
        return body, '"' + sha256(body).hexdigest() + '"'

    def active(self):
        identifier = active_identifier(self.root)
        if identifier:
            check_warehouse_variant(read(self.root / STORE / identifier / "result.json"), self.warehouse_variant)
        return self.get("warehouse", identifier)

    def for_run(self, run):
        route = self.root / "dispatch" / run / "route.json"
        if route.is_file():
            binding = read(route).get("learned")
        else:
            report = self.root / "reports" / run / "run.json"
            binding = read(report).get("mission", {}).get("learned") if report.is_file() else None
        if not binding or not CONFIG_ID.fullmatch(str(binding.get("configuration_id"))) or type(binding.get("revision")) is not int:
            raise FileNotFoundError("This inspection has no recorded learned warehouse revision.")
        return self.get("warehouse", binding["configuration_id"], binding["revision"])
