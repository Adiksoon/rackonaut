"""Local, in-memory HTTP fixture server for the Rackonaut contract."""

import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


CONTRACT = read_json("contracts/openapi.json")
INVENTORY = read_json("test_data/expected_inventory.json")
FIXTURES = read_json("test_data/inspection_scenarios.json")
INSPECTION_SPEC = CONTRACT["components"]["parameters"]["InspectionId"]["schema"]
DEFAULT_INSPECTION = INSPECTION_SPEC["default"]
INSPECTION_VALIDATOR = Draft202012Validator(INSPECTION_SPEC)
OBSERVATION_VALIDATOR = Draft202012Validator(CONTRACT["components"]["schemas"]["Observation"])
OUTCOMES = tuple(CONTRACT["components"]["schemas"]["Summary"]["properties"]["outcomes"]["properties"])
DISCREPANCIES = {"wrong_pallet", "missing_pallet", "unexpected_pallet", "unreadable_label", "uncertain"}
EXPECTED_BY_SLOT = {item["slot_id"]: item["pallet_id"] for item in INVENTORY["locations"]}


def error(status, code, message):
    return HTTPException(status, detail={"code": code, "message": message})


def capture_time(observation):
    return datetime.fromisoformat(observation["timestamp"][:-1] + "+00:00")


def check_inspection(inspection_id):
    if not INSPECTION_VALIDATOR.is_valid(inspection_id):
        raise error(422, "invalid_inspection_id", "Use an INS- identifier such as INS-001.")


def check_observation(payload):
    issue = next(OBSERVATION_VALIDATOR.iter_errors(payload), None)
    if issue:
        field = ".".join(map(str, issue.absolute_path)) or "body"
        raise error(422, "invalid_observation", f"{field} violates {issue.validator} in the observation contract.")
    try:
        capture_time(payload)
    except ValueError as exc:
        raise error(422, "invalid_observation", "timestamp must be a valid UTC date and time.") from exc


def event_key(observation):
    return observation["inspection_id"], observation["observation_id"]


class InventoryStore:
    def __init__(self, inventory):
        self.expected = {item["slot_id"]: item["pallet_id"] for item in inventory["locations"]}

    def slots(self, history):
        latest = {event["slot_id"]: event for event in history}
        return [
            {"slot_id": slot, "expected_pallet_id": expected,
             "observed_pallet_id": event["pallet_id"] if (event := latest.get(slot)) else None,
             "observation_id": event["observation_id"] if event else None,
             "outcome": self.outcome(expected, event) if event else "uninspected"}
            for slot, expected in self.expected.items()
        ]


class FixtureStore(InventoryStore):
    def __init__(self, inventory=INVENTORY):
        super().__init__(inventory)
        self.events = {}
        self.fixture_events = {}
        for scenario in FIXTURES["scenarios"]:
            for event in scenario["events"]:
                observation = event["observation"]
                key = event_key(observation)
                self.events[key] = observation
                self.fixture_events[key] = event

    def record(self, observation):
        key = event_key(observation)
        previous = self.events.get(key)
        if previous is not None:
            if previous != observation:
                raise error(409, "observation_conflict", "This inspection already has this observation_id.")
            return 200
        if observation["slot_id"] not in self.expected:
            raise error(404, "unknown_slot", "slot_id does not exist in the expected inventory.")
        self.events[key] = observation
        return 201

    def history(self, inspection_id):
        events = (event for event in self.events.values() if event["inspection_id"] == inspection_id)
        return sorted(events, key=lambda event: (capture_time(event), event["observation_id"]))

    def outcome(self, _expected, event):
        fixture = self.fixture_events.get(event_key(event))
        return fixture["fixture_outcome"] if fixture else "pending"


def create_app(inventory=INVENTORY, *, store=None, mode="fixture"):
    app = FastAPI(title=CONTRACT["info"]["title"], version=CONTRACT["info"]["version"], redoc_url=None)
    app.openapi = lambda: CONTRACT
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(?:localhost|127\.0\.0\.1)(?::[0-9]+)?",
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    if store is None:
        store = FixtureStore(inventory)

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": mode}

    @app.get("/api/inventory/expected")
    async def expected_inventory():
        return inventory

    @app.post("/api/observations")
    async def submit_observation(request: Request):
        media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
        if media_type != "application/json":
            raise error(415, "unsupported_media_type", "Use Content-Type: application/json.")
        try:
            payload = await request.json()
        except ValueError as exc:
            raise error(400, "malformed_json", "The request body must be valid JSON.") from exc
        check_observation(payload)
        return JSONResponse(payload, status_code=store.record(payload))

    @app.get("/api/observations")
    async def observations(inspection_id: str = DEFAULT_INSPECTION):
        check_inspection(inspection_id)
        return store.history(inspection_id)

    @app.get("/api/discrepancies")
    async def discrepancies(inspection_id: str = DEFAULT_INSPECTION):
        check_inspection(inspection_id)
        return [slot for slot in store.slots(store.history(inspection_id)) if slot["outcome"] in DISCREPANCIES]

    @app.get("/api/summary")
    async def summary(inspection_id: str = DEFAULT_INSPECTION):
        check_inspection(inspection_id)
        history = store.history(inspection_id)
        slots = store.slots(history)
        counts = dict.fromkeys(OUTCOMES, 0)
        for slot in slots:
            counts[slot["outcome"]] += 1
        return {
            "inspection_id": inspection_id,
            "slots_total": len(slots),
            "slots_observed": len(slots) - counts["uninspected"],
            "observations_total": len(history),
            "discrepancy_count": sum(counts[outcome] for outcome in DISCREPANCIES),
            "outcomes": counts,
            "slots": slots,
        }

    return app


app = create_app()
