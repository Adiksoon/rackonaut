"""Seal validated calibration archives and select them at the physical dock."""

import json
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from rackonaut_avoidance.sensor import (FRAME as LIDAR_FRAME, FULL_ROUTE_RANGE, HEIGHT, MAX_RANGE,
                                       MIN_RANGE, OFFSET, TOPIC as LIDAR, WIDTH)
from rackonaut_energy.aerial import Network
from rackonaut_energy.model import Model
from rackonaut_localization.learned_map import MAP_FILE, load as load_map
from rackonaut_localization.node import IMU, IMU_FRAME
from rackonaut_localization.warehouse_config import (ACTIVE, CONFIG_ID, FORMAT, FRAME, PHOTO, REQUIRED, STORE,
                                                    active_identifier, digest, file_hash, read, verified_package)
from rackonaut_mission.learned import forecast, ordered_targets

from .teaching import atomic_write, session_path


def write_json(path, value):
    atomic_write(path, (json.dumps(value, indent=2, allow_nan=False) + "\n").encode())


class WarehouseArchive:
    def __init__(self, directory, route_review, layout, sensor_mode):
        self.directory = Path(directory)
        self.review = route_review
        self.store = self.directory / STORE
        self.safety = {"aerial": layout.get("aerial"), "fields": layout.get("safety_fields"),
                       "laser_fields": layout.get("laser_fields"), "sensor_mode": sensor_mode}
        self.sensors = {"lidar": {"topic": LIDAR, "frame": LIDAR_FRAME, "width": WIDTH, "height": HEIGHT,
                                  "range_m": [MIN_RANGE, FULL_ROUTE_RANGE], "position_m": OFFSET.tolist(),
                                  "collision_range_m": MAX_RANGE},
                        "imu": {"topic": IMU, "frame": IMU_FRAME},
                        "camera": {"topic": "/rackonaut/camera/image_raw", "frame": "rackonaut_camera_optical_frame"}}

    def active_id(self):
        return active_identifier(self.directory)

    def list(self):
        output = []
        for folder in sorted(self.store.glob("WH-*")):
            if not CONFIG_ID.fullmatch(folder.name) or folder.is_symlink():
                continue
            try:
                item = read(folder / "manifest.json")
                output.append({"configuration_id": folder.name, "mapping_id": item["mapping_id"],
                               "name": item["name"], "revision": item["revision"]})
            except (OSError, ValueError, KeyError, TypeError):
                output.append({"configuration_id": folder.name, "name": "Unreadable warehouse manifest"})
        return output

    def seal(self, session, name):
        source = self.review.state(session)
        route = source["route"]
        if source["status"] != "approved" or not route or "localization_sha256" not in route["inputs"]:
            raise RuntimeError("Approve the current route from a completed full-range SLAM calibration.")
        locations = source["locations"]
        photos = {location["reference_image"] for location in locations}
        if any(not PHOTO.fullmatch(photo) for photo in photos):
            raise ValueError("The calibration contains an invalid camera reference.")
        self.store.mkdir(exist_ok=True, parents=True)
        with TemporaryDirectory(dir=self.store) as scratch:
            folder = Path(scratch) / "warehouse"
            folder.mkdir()
            for filename in sorted((REQUIRED - {"safety.json", "sensors.json"}) | photos):
                target = folder / filename
                target.parent.mkdir(exist_ok=True, parents=True)
                copyfile(session_path(self.review.root, session, *filename.split("/")), target)
            write_json(folder / "safety.json", self.safety)
            write_json(folder / "sensors.json", self.sensors)
            dock, _ = load_map(folder / MAP_FILE)
            manifest = {"schema_version": FORMAT, "mapping_id": session, "frame": FRAME, "name": name,
                        "revision": route["location_revision"], "dock": dock.tolist(),
                        "route_sha256": source["route_sha256"],
                        "files": {path.relative_to(folder).as_posix(): file_hash(path)
                                  for path in sorted(folder.rglob("*")) if path.is_file()}}
            identifier = "WH-" + digest(manifest)[:32].upper()
            write_json(folder / "manifest.json", {**manifest, "configuration_id": identifier})
            destination = self.store / identifier
            if not destination.exists():
                folder.replace(destination)
        return self.verify(identifier)

    def verify(self, identifier):
        folder, manifest = verified_package(self.directory, identifier)
        source = self.review.state(manifest["mapping_id"])
        route = source["route"]
        if (source["status"] != "approved" or not route or manifest["route_sha256"] != source["route_sha256"]
                or route["location_revision"] != manifest["revision"] or read(folder / "route.json") != route
                or manifest["files"]["map.ply"] != route["inputs"].get("map_sha256")
                or manifest["files"][MAP_FILE] != route["inputs"].get("localization_sha256")):
            raise RuntimeError("The approved calibration route or its map has changed.")
        if read(folder / "safety.json") != self.safety or read(folder / "sensors.json") != self.sensors:
            raise RuntimeError("The warehouse uses a different sensor or Safety profile.")
        location_file = read(folder / "locations.json")
        photos = {location["reference_image"] for location in source["locations"]}
        if (location_file != self.review.teaching.manifest(manifest["mapping_id"])
                or manifest["files"].keys() != REQUIRED | photos
                or source["validation"] != read(folder / "route-validation.json")):
            raise RuntimeError("The route, location manifest and camera evidence do not match the archive.")
        return {"manifest": manifest, "route": route, "locations": source["locations"],
                "validation": source["validation"], "raw_positions": source["raw_positions"],
                "route_sha256": source["route_sha256"], "status": source["status"], "mapping_id": manifest["mapping_id"]}

    def activate(self, identifier):
        config = self.verify(identifier)
        write_json(self.directory / ACTIVE, {"schema_version": FORMAT, "configuration_id": identifier})
        return config

    def plan(self, request, telemetry):
        identifier = self.active_id()
        if not identifier or identifier != request.get("configuration_id"):
            raise RuntimeError("Select the active learned warehouse before planning a mission.")
        config = self.verify(identifier)
        manifest, graph = config["manifest"], config["route"]
        if request.get("revision") != manifest["revision"]:
            raise RuntimeError("Reload the active warehouse and choose locations at its current revision.")
        selected = request.get("record_ids")
        if not isinstance(selected, list) or not selected or any(not isinstance(item, str) for item in selected):
            raise ValueError("Choose taught inventory locations.")
        profile = self.safety["aerial"]
        targets, zones = ordered_targets(graph, set(selected), Network(profile))
        stops = [slot for _, _, slot, _, _ in targets if slot]
        pad = {key: profile["pad"][key] for key in ("x", "y", "z", "yaw_deg")}
        model = Model(**telemetry["model"]) if telemetry else Model()
        poses = [pose for _, pose, _, _, _ in targets]
        last_stop = max(i for i, (_, _, slot, _, _) in enumerate(targets) if slot)
        budget = forecast(model, (*manifest["dock"], 0.), poses, len(stops), last_stop)
        required = budget["required_percent"]
        budget.update(minimum_percent=required,
                      can_start=bool(telemetry and telemetry["fresh"] and telemetry["budget_verified"]
                                     and telemetry["percent"] >= required))
        return {"mode": "learned", "quality": False, "adaptive": False, "slots": stops,
                "required_zones": list(zones), "points": [node["position_m"] for node in graph["nodes"]],
                "energy": budget,
                "route": {"pad": pad, "aerial": profile, "energy_zones": list(zones),
                          "energy_crossing_x": profile["nodes"]["entry_A"][0],
                          "learned": {"configuration_id": identifier, "revision": manifest["revision"],
                                      "approval_sha256": manifest["route_sha256"], "graph": graph,
                                      "record_ids": sorted(set(selected))}}}
