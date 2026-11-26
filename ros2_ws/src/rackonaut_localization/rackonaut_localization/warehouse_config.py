"""Integrity checks shared by the archive service and the dock localizer."""

import hashlib
import json
import re
from pathlib import Path


CONFIG_ID = re.compile(r"WH-[0-9A-F]{32}")
SESSION_ID = re.compile(r"CAL-[0-9A-F]{32}")
PHOTO = re.compile(r"locations/CAP-[0-9A-F]{32}/reference\.jpg")
STORE = "warehouse-configurations"
ACTIVE = "active-warehouse.json"
FORMAT = 1
FRAME = "rackonaut_odom"
REQUIRED = {"map.ply", "localization.npz", "result.json", "locations.json", "trajectory.jsonl",
            "route.json", "route-validation.json", "safety.json", "sensors.json"}


def digest(value):
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def file_hash(path):
    with path.open("rb") as stream:
        checksum = hashlib.sha256()
        for buffer in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(buffer)
        return checksum.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verified_package(root, identifier):
    if not isinstance(identifier, str) or not CONFIG_ID.fullmatch(identifier):
        raise ValueError("Invalid learned warehouse identifier.")
    store = Path(root) / STORE
    folder = store / identifier
    manifest_file = folder / "manifest.json"
    if folder.is_symlink() or manifest_file.is_symlink():
        raise ValueError("The learned warehouse archive must use local files.")
    manifest = read(manifest_file)
    if not isinstance(manifest, dict):
        raise ValueError("Invalid learned warehouse manifest.")
    attributes = {key: value for key, value in manifest.items() if key != "configuration_id"}
    if (manifest.get("configuration_id") != identifier or "WH-" + digest(attributes)[:32].upper() != identifier
            or manifest.get("schema_version") != FORMAT or manifest.get("frame") != FRAME
            or not SESSION_ID.fullmatch(str(manifest.get("mapping_id")))):
        raise ValueError("Warehouse manifest integrity check failed.")
    files = manifest.get("files")
    if not isinstance(files, dict) or not REQUIRED <= files.keys() or len(files) <= len(REQUIRED):
        raise ValueError("The learned warehouse archive is incomplete.")
    for name, expected in files.items():
        if name not in REQUIRED and not PHOTO.fullmatch(name):
            raise ValueError("Unexpected file in the learned warehouse manifest.")
        path = folder / name
        if path.resolve() != folder.resolve() / name or not path.is_file() or file_hash(path) != expected:
            raise ValueError(f"Warehouse file integrity check failed for {name}.")
    return folder, manifest


def active_identifier(root):
    path = Path(root) / ACTIVE
    try:
        value = read(path)
    except FileNotFoundError:
        return None
    if (not isinstance(value, dict) or value.get("schema_version") != FORMAT
            or not CONFIG_ID.fullmatch(str(value.get("configuration_id")))):
        raise ValueError("The active warehouse selection is invalid.")
    return value["configuration_id"]
