"""Exercise the fixture API over real loopback HTTP and close its server."""

import json
import socket
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
OPENER = build_opener(ProxyHandler({}))


@contextmanager
def running_api():
    config = uvicorn.Config("backend.mock_api:app", log_level="warning", ws="none")
    server = uvicorn.Server(config)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        worker = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        worker.start()
        try:
            deadline = time.monotonic() + 8
            while not server.started and worker.is_alive() and time.monotonic() < deadline:
                time.sleep(0.025)
            if not server.started:
                raise RuntimeError("Fixture API did not start.")
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            worker.join(timeout=5)
            if worker.is_alive():
                raise RuntimeError("Fixture API did not stop.")


def request(base_url, path, code=200, *, method="GET", payload=None, body=None, headers=None):
    headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(base_url + path, data=body, headers=headers, method=method)
    try:
        result = OPENER.open(req, timeout=4)
    except HTTPError as error:
        result = error
    with result as response:
        raw = response.read()
        if response.status != code:
            raise RuntimeError(f"{method} {path}: expected HTTP {code}, received {response.status}: {raw!r}")
        if response.headers.get_content_type() == "application/json":
            raw = json.loads(raw)
        return raw, response.headers


def load(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def expect(actual, expected, name):
    if actual != expected:
        raise RuntimeError(f"{name}: expected {expected!r}, received {actual!r}.")


def exercise(base_url):
    spec = load("contracts/openapi.json")
    inventory = load("test_data/expected_inventory.json")
    fixtures = load("test_data/inspection_scenarios.json")
    examples = load("test_data/api_examples.json")

    for path, expected in examples["get_responses"].items():
        actual, _ = request(base_url, path)
        expect(actual, expected, path)
    actual, _ = request(base_url, "/api/inventory/expected")
    expect(actual, inventory, "GET expected inventory")
    actual, _ = request(base_url, "/openapi.json")
    expect(actual, spec, "GET OpenAPI")

    history, _ = request(base_url, "/api/observations")
    expected_history = [event["observation"] for case in fixtures["scenarios"] for event in case["events"]]
    expect({item["observation_id"]: item for item in history},
           {item["observation_id"]: item for item in expected_history}, "GET fixture observation history")
    expect(len(history), len(expected_history), "Unique fixture observations")

    sample = examples["post_request"]["body"]
    path = examples["post_request"]["path"]
    for status in (201, 200):
        actual, _ = request(base_url, path, status, method="POST", payload=sample)
        expect(actual, sample, f"POST observation HTTP {status}")
    actual, _ = request(base_url, path + f"?inspection_id={sample['inspection_id']}")
    expect(actual, [sample], "GET unique observation after retry")
    summary, _ = request(base_url, "/api/summary" + f"?inspection_id={sample['inspection_id']}")
    result = next(slot for slot in summary["slots"] if slot["slot_id"] == sample["slot_id"])
    expect(result["outcome"], "pending", "GET result for a new custom observation")

    invalid_cases = (
        (409, {**sample, "timestamp": "2026-11-25T12:45:00Z"}, "observation_conflict"),
        (404, {**sample, "observation_id": "OBS-UNKNOWN-SLOT", "slot_id": "Z-99-99"}, "unknown_slot"),
        (422, {**sample, "occupancy": "empty"}, "invalid_observation"),
        (422, {**sample, "timestamp": "2026-02-30T12:00:00Z"}, "invalid_observation"),
        (422, {**sample, "observation_id": "OBS-EXAMPLE\n"}, "invalid_observation"),
    )
    for status, payload, reason in invalid_cases:
        actual, _ = request(base_url, path, status, method="POST", payload=payload)
        expect(actual["detail"]["code"], reason, f"POST observation HTTP {status}")
    request(base_url, path, 400, method="POST", body=b"{", headers={"Content-Type": "application/json"})
    request(base_url, path, 415, method="POST", body=b"{}")
    request(base_url, "/api/summary?inspection_id=invalid", 422)

    origin = "http://localhost:5173"
    _, headers = request(base_url, path, method="OPTIONS", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    })
    expect(headers.get("access-control-allow-origin"), origin, "Local dashboard CORS")
    _, headers = request(base_url, "/health", headers={"Origin": "https://example.org"})
    expect(headers.get("access-control-allow-origin"), None, "Non-loopback dashboard CORS")

    return f"{len(fixtures['scenarios'])} scenarios, {len(history)} unique events"


if __name__ == "__main__":
    # The server imports the checked-out app even when this file is invoked by path.
    sys.path.insert(0, str(ROOT))
    with running_api() as endpoint:
        cases = exercise(endpoint)
        print(f"API-01 PASS | {endpoint} | POST 201, retry 200, conflicts and validation exercised")
        print(f"API-02 PASS | {cases} | GET inventory, observations, discrepancies, summary, OpenAPI and CORS")
    print("API shutdown PASS | owned Uvicorn server stopped")
