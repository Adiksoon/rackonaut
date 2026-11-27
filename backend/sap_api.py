"""Functional Mock SAP profile for the shared inventory API and business views."""

from base64 import b64decode
from binascii import Error
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from .mock_api import INVENTORY as BASE_INVENTORY
from .intelligence import build
from .mock_api import capture_time, check_inspection, create_app, error, read_json
from .sap_store import SapStore

INVENTORY = {**BASE_INVENTORY, "locations": [
    *BASE_INVENTORY["locations"], *read_json("test_data/control_inventory_extension.json")["locations"]
]}
EXPECTED = {row["pallet_id"]: row["slot_id"] for row in INVENTORY["locations"] if row["pallet_id"]}
PRODUCTS = {row["hu_id"]: {**row, "expected_slot": EXPECTED.get(row["hu_id"])}
            for row in read_json("test_data/mock_sap_products.json")["handling_units"]}
QUALITY_ID = re.compile(r"Q-[A-F0-9]{32}")
UTC = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{3})?Z")
PNG = b"\x89PNG\r\n\x1a\n"
MAX_UPLOAD = 12 * 1024 * 1024


def bundle(payload):
    try:
        report, images = payload["report"], payload["images"]
        quality_id = report["quality_id"]
        inspection = report["inspection_id"]
        check_inspection(inspection)
        if (not QUALITY_ID.fullmatch(quality_id) or report["quality_schema_version"] != "0.1"
                or report["status"] not in {"DAMAGED", "OK", "CAPTURED"}
                or not isinstance(report["reason"], str) or not 1 <= len(report["reason"]) <= 1024
                or not UTC.fullmatch(report["timestamp"]) or not UTC.fullmatch(report["observation_timestamp"])
                or capture_time(report) < capture_time({"timestamp": report["observation_timestamp"]})
                or report["images"] != {"original": "camera.png", "annotated": "annotated.png"}):
            raise ValueError
        raw = tuple(b64decode(images[kind], validate=True) for kind in ("original", "annotated"))
        if any(not photo.startswith(PNG) or len(photo) > 4 * 1024 * 1024 for photo in raw):
            raise ValueError
        for name in ("slot_id", "observation_id"):
            if not isinstance(report[name], str):
                raise ValueError
        if report["pallet_id"] is not None and not isinstance(report["pallet_id"], str):
            raise ValueError
        if report["status"] == "CAPTURED" and (
                report.get("occupancy") not in {"occupied", "empty", "uncertain"}
                or capture_time(report) != capture_time({"timestamp": report["observation_timestamp"]})):
            raise ValueError
        return report, raw
    except (KeyError, TypeError, ValueError, Error) as exc:
        raise error(422, "invalid_quality", "Supply linked quality metadata and the two PNG images.") from exc


def create_sap_app(database):
    store = SapStore(INVENTORY, database)
    app = create_app(INVENTORY, store=store, mode="mock_sap")

    @app.get("/api/business/products")
    def products():
        return {"source": "mock_sap", "synthetic": True, "handling_units": list(PRODUCTS.values())}

    @app.get("/api/business/summary")
    def intelligence(inspection_id: str):
        check_inspection(inspection_id)
        with store.connect() as db:
            db.execute("BEGIN")
            return build(store, PRODUCTS, db, inspection_id)

    @app.post("/api/business/quality")
    async def upload(request: Request):
        if request.headers.get("content-type", "").partition(";")[0].strip().lower() != "application/json":
            raise error(415, "unsupported_media_type", "Use Content-Type: application/json.")
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_UPLOAD:
                raise error(413, "quality_too_large", "The quality bundle exceeds the upload limit.")
        try:
            value = json.loads(data)
        except (ValueError, UnicodeError) as exc:
            raise error(400, "malformed_json", "Send a JSON quality bundle.") from exc
        report, photos = bundle(value)
        return JSONResponse({"quality_id": report["quality_id"]}, status_code=store.record_quality(report, *photos))

    @app.get("/api/business/quality/{inspection}/{quality}/{kind}.png")
    def photo(inspection: str, quality: str, kind: str):
        check_inspection(inspection)
        if not QUALITY_ID.fullmatch(quality) or kind not in {"original", "annotated"}:
            raise error(404, "unknown_quality", "No such evidence image.")
        return Response(store.photo(inspection, quality, kind), media_type="image/png")

    @app.post("/api/business/issues/{issue_id}/verify")
    def verify(issue_id: str, payload: dict):
        inspection, revision = payload.get("inspection_id"), payload.get("revision")
        check_inspection(inspection)
        with store.connect(write=True) as db:
            data = build(store, PRODUCTS, db, inspection)
            item = next((entry for entry in data["issues"] if entry["issue_id"] == issue_id), None)
            if item is None:
                raise error(404, "unknown_issue", "No active issue with that ID in this inspection.")
            if revision != item["revision"]:
                raise error(409, "outdated_issue", "Refresh the evidence before acknowledging the issue.")
            stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            db.execute("INSERT OR IGNORE INTO verification VALUES (?,?,?,?)", (inspection, issue_id, revision, stamp))
        return {"issue_id": issue_id, "status": "VERIFIED"}

    return app


def app():
    path = os.environ.get("RACKONAUT_SAP_DB", ".rackonaut-data/warehouse.sqlite3")
    return create_sap_app(Path(path))
