# Inspection HTTP contract

[OpenAPI 3.1](openapi.json) defines v1.0.0 of the HTTP API and the `Observation` component defines schema version `1.0`. The fixture server serves the same document at `/openapi.json`, validates incoming observations against its schema and provides Swagger UI at `/docs`. The HTTP interface uses JSON over loopback during development. See the [backend onboarding guide](../docs/onboarding/BACKEND.md) for Windows and Linux setup.

## Recording observations

| Field | Meaning |
| --- | --- |
| `schema_version` | Required. Use `1.0`. |
| `inspection_id` | Required. `INS-...` scopes an inspection and its event history. |
| `observation_id` | Required. `OBS-...` identifies one capture result within that inspection. Generate a new ID for a new capture and preserve it on transport retries. |
| `slot_id` | Required. `A-01-02` means aisle A, bay 01, level 02. Must exist in the expected inventory. |
| `pallet_id` | Required. A readable ID such as `P001`, or JSON `null` when a readable ID is unavailable. |
| `occupancy` | Required. `occupied`, `empty` or `uncertain`. |
| `label_status` | Required. Use `readable` or `unreadable` for occupied, `not_applicable` for empty, and `unknown` for uncertain. |
| `timestamp` | Required. UTC capture time in RFC 3339 with `Z`, with optional three fractional digits. |

All fields are required in v1.0 and extra fields are rejected. Occupied plus unreadable uses `pallet_id: null`. Uninspected slots have no submitted observation and appear as `uninspected` in the summary. Empty slots require an explicit capture reporting `empty`. An uncertain result remains a review item, and a pallet with an unreadable label still occupies a slot.

Assign timestamps in UTC when acquiring the observation. During simulation, the producer records the wall-clock UTC associated with capture. Operating ROS topics continue to use their original simulation stamps. A replay preserves the original observation timestamp. The fixture timestamps are synthetic.

Mount a visible slot ID followed by a separate pallet label. Associate an image observation with the slot marker inside the same bay and image region or track the same calibrated region across adjacent frames. If the slot cannot be identified, omit the event and leave the slot uninspected. A known slot with inconclusive image evidence can publish `uncertain`. Gazebo poses, model identities and fixture observations are validation references. Actual detections should come from the camera pipeline.

A repeated POST with the same inspection ID, observation ID and payload returns HTTP 200 with the stored event. Reuse of that key with a changed payload returns HTTP 409. A new capture at the same slot creates another event with a different ID. The summary uses the latest capture timestamp for each slot, breaking equal-time ties by lexicographically greatest observation ID. Late arrival cannot replace a newer capture.

## Routes

| Method and path | Result |
| --- | --- |
| `GET /health` | HTTP 200 with service status and mode. |
| `GET /api/inventory/expected` | HTTP 200 with expected slot and pallet pairs. A null pallet ID here means the inventory expects an empty slot. |
| `POST /api/observations` | HTTP 201 for a new event or 200 for an identical retry. Returns the accepted observation. |
| `GET /api/observations` | HTTP 200 with unique events in capture order. |
| `GET /api/discrepancies` | HTTP 200 with wrong, missing or unexpected pallets, unreadable labels and uncertain readings. |
| `GET /api/summary` | HTTP 200 with counts and a result for every expected slot. |

Pass `inspection_id` as a query parameter to the observations, discrepancies and summary GET routes. The fixture default is `INS-001`. The fixture server returns `pending` for custom observations and preassigned outcomes for the supplied scenarios. `pending` and `uninspected` are excluded from the discrepancy count. A valid inspection ID with no events starts with all slots uninspected.

Requests must use `Content-Type: application/json`. Error status 400 means malformed JSON, 404 means unknown slot, 409 means an observation identity conflict, 415 means an unsupported media type, and 422 means the body or inspection ID failed validation. Errors return `{"detail":{"code":"...","message":"..."}}`. Fix 400, 404, 409, 415 and 422 responses before retrying. An unchanged observation may be retried after a transport timeout.

## Examples

[Fixture examples](../test_data/api_examples.json) contain a POST body and GET results for health, discrepancies and summary. [Expected inventory](../test_data/expected_inventory.json) and the events in the [inspection scenarios](../test_data/inspection_scenarios.json) supply the remaining example responses.

After starting the mock, run these commands from the repository root on Linux or WSL.

```bash
curl -sS http://127.0.0.1:8000/api/summary
.venv-backend/bin/python -c "import json; print(json.dumps(json.load(open('test_data/api_examples.json', encoding='utf-8'))['post_request']['body']))" \
  | curl -sS -i -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1:8000/api/observations
```

Use PowerShell on Windows.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/summary
$sample = Get-Content test_data/api_examples.json -Raw | ConvertFrom-Json
$body = $sample.post_request.body | ConvertTo-Json -Compress
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/observations -ContentType application/json -Body $body
```

Bind development API and dashboard services to loopback. For a browser dashboard, the mock allows `localhost` and `127.0.0.1` origins with HTTP or HTTPS and optional ports. Keep the API base URL configurable and refresh results with ordinary GET requests.

## Functional Mock SAP profile

Launch `backend.sap_api:app --factory` for computed outcomes on the same v1 routes. The functional profile covers eleven locations and returns health mode `mock_sap`. It calculates the outcome from the most recent observation and the expected inventory. Its additional business, photo and verification routes are documented separately. [Warehouse Intelligence integration](../docs/SAP_BUSINESS_INTELLIGENCE.md)
