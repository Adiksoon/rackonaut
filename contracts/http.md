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

## Local storage location teaching

The loopback Control Center exposes the session below through its existing authenticated Service cookie. Camera timestamps are ROS time. Recorded poses use the measured `rackonaut_odom` frame, with XYZ in metres and orientation quaternion in XYZW order.

| Method and path | Behavior |
| --- | --- |
| `GET /api/service/teaching` | Returns the current mapping manifest, whether the draft is editable, and capture readiness. |
| `POST /api/service/teaching/capture` | Accepts `calibration_id` and returns a pending synchronized capture, its reference JPEG URL, and an unambiguous location-marker ID when available. |
| `POST /api/service/teaching/save` | Accepts `calibration_id`, `capture_id`, `revision`, `storage_location_id`, and optional `description`. Replacement also requires the existing `record_id` and `confirm: true`. |
| `POST /api/service/teaching/rename` | Accepts `calibration_id`, `record_id`, `revision`, and `storage_location_id`. Preserves the pose and photo. |
| `POST /api/service/teaching/delete` | Accepts `calibration_id`, `record_id`, `revision`, and `confirm: true`. Changes the active draft manifest. |
| `GET /api/service/mapping/{calibration_id}/locations.json` | Downloads the approved location list for a completed map. The manifest names its PLY and result files and links the individual reference images. |

Authentication failures return `401`. Ineligible flight state, a changed draft, or a conflicting location ID can return `409`. The pending photo is bound to the Service session that requested it. Client requests provide identifiers and confirmation only. The Mock SAP observation routes keep their existing payload and behavior.

## Local route review

Route operations use the same authenticated Service cookie. Read archived routes by mapping ID. Review, validation, planning, and approval require the current completed session and verified physical docking. Requests submit a calibration ID and, after review, the exact `route_sha256` of the proposal.

| Method and path | Behavior |
| --- | --- |
| `GET /api/service/route/{calibration_id}` | Returns the recorded positions, location records, route status, and matching validation if available. A changed source manifest yields `stale`. |
| `POST /api/service/route/review` | Generates the directed graph from the timestamped captures and returns the proposal with its hash. |
| `POST /api/service/route/validate` | Checks the proposal against the measured source, the approved flight envelope, and the simulated energy budget. The response specifies `historical_envelope` and `live_clearance: required`. |
| `POST /api/service/route/plan` | Accepts nonempty `record_ids` from the proposal and returns the measured sequence of directed waypoints and the forecast for the selected stops. |
| `POST /api/service/route/approve` | Requires `confirm: true` and the current validated proposal. Records approval in the calibration archive. |
| `GET /api/service/mapping/{calibration_id}/{filename}` | Downloads `trajectory.jsonl`, `route.json`, or `route-validation.json` once available. |

The calibration journal uses ROS time, recorded XYZ in metres, and XYZW orientation in `rackonaut_odom`. Approval applies to the exact archive revision. Runtime clearance and flight dispatch remain separate operations.

## Learned warehouse activation and dispatch

Service authentication is required for configuration management. Route sealing and activation require an idle aircraft at the verified physical dock. The existing local dispatch endpoint checks the selected active configuration, its integrity and the matching learned-map localization state.

| Method and path | Behavior |
| --- | --- |
| `GET /api/service/warehouses` | Lists saved configurations and the localizer's active and loaded IDs. |
| `POST /api/service/warehouses/seal` | Takes `calibration_id` for the current completed calibration and snapshots the approved route, measured maps and evidence. |
| `POST /api/service/warehouses/verify` | Takes `configuration_id` and verifies the archive, approved sources and current sensor and Safety profile. |
| `POST /api/service/warehouses/activate` | Takes `configuration_id` and `confirm: true`. Saves a selection after verification. Localization readiness follows from a separate dock match. |
| `POST /api/plan` and `POST /api/start` | In `mode: learned` accept the active `configuration_id`, `revision` and nonempty `record_ids`. Use the original sequence of approved directed edges and stop only at the selected learned locations. |

The existing Mock SAP API receives current camera observations and the existing report exporter reads those observations by inspection ID. Calibration references remain in the warehouse archive.

## Control Center warehouse visualization

Read-only JSON for Warehouse Digital Twin in the existing loopback Control Center.

| Method and path | Behavior |
| --- | --- |
| `GET /api/visualization/active` | Returns the visualization for the selected learned configuration. |
| `GET /api/visualization/run/{inspection_id}` | Resolves the learned configuration and revision recorded for that inspection. Uses the dispatch record or archived mission evidence. |
| `GET /api/service/visualization/warehouse/{configuration_id}` | Previews any verified saved configuration with the existing Service session. |
| `GET /api/service/visualization/calibration/{calibration_id}` | Previews a completed measured calibration with the existing Service session. |

A ready response contains `binding` (configuration ID, calibration ID, revision, and input hashes), `name`, the original Float32 little-endian XYZ payload in `points_f32le`, `point_count`, and `enhanced` (template parameters, layout and location projections). The public responses omit calibration photographs and archived route edges. The protected previews include them. Live approved route and flown positions continue to use the existing mission telemetry.

Requests return `202` with `status: preparing` and `Retry-After: 2` during background work, `304` with a matching `If-None-Match`, and `404` for a missing model association or input. Service follows the existing origin and authentication checks. Visualization failure reports a read error and leaves the archive and dispatch permissions independent.

The exporter writes `visualization.json` beside the calibration or sealed configuration with an atomic replacement. Its binding tracks source hashes and revision. The verified localization manifest, approved routes, stored inspection poses and robot commands use their existing paths and formats.
