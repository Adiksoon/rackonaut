# Mission verification

Ran on 25 November 2026 under Ubuntu 22.04 on WSL2, ROS 2 Humble and Gazebo Fortress 6.16.0. Gazebo used llvmpipe. The warehouse and perception ancestors are `d9b1d3d` and `4d971fc`. All live runs used the repository mock API with a fresh ID in each isolated simulator and ROS domain.

## Uninterrupted five-stop flight

```bash
scripts/robotics/build
source scripts/robotics/activate.bash
ros2 launch rackonaut_mission showcase.launch.py rviz:=true \
  autostart:=false inspection_id:=INS-MISSION-G04-LIVE \
  mock_port:=18085 backend_url:=http://127.0.0.1:18085
ros2 service call /rackonaut/mission/start std_srvs/srv/Trigger '{}'
```

The service was called once from a second activated terminal after the camera and ROS recorder were ready. Mission Manager was the sole command publisher. Starting on the marked pad, the drone climbed to the first inspection height, flew to the first bay, turned towards the rack, and visited all five viewpoints. The only pose used for control was its continuous simulator-derived odometry. Gazebo's GUI camera was repositioned for the screenshot while the drone continued on the waypoint route.

| Slot | Occupancy | Label | Pallet accepted by the mock |
| --- | --- | --- | --- |
| A-01-01 | occupied | readable | P001 |
| A-01-02 | occupied | readable | P003 |
| A-01-03 | empty | not_applicable | — |
| A-01-04 | occupied | readable | P999 |
| A-01-05 | occupied | unreadable | — |

The mission reached `COMPLETE` with **5 visited, 5 API-confirmed, 0 misses** and `landed: true` in **75.3 s**. It returned to `(0.0, 0.0, 0.05)` m. The ROS bag supplied 1,868 odometry messages, a 29.60 m sampled path, a 2.895 m maximum altitude and a largest adjacent position change of 0.0297 m. [Mission status](evidence/mission_status.json) · [Odometry statistics and transitions](evidence/flight_telemetry.json)

All 11 raw observations served by the mock passed the OpenAPI `Observation` schema. The five specific observations used to advance the mission are nested in the mission status. The extra observations were captured when the camera was already seeing labels during approach or after rearm at another point. For example, P999 was posted during transit at A-01-04, and the mission advanced only after a second observation for that slot, captured after the scan began. The mock accepts custom observations with comparison status `pending`. [Raw API response](evidence/api_observations.json)

## Recovery and handoff checks

- The one-command demo `ros2 launch rackonaut_mission showcase.launch.py rviz:=true` generated a fresh shared ID, started automatically and repeated all five confirmations with landing in 75.2 s. [Automatic start result](evidence/autostart_status.json)
- With a temporary two-stop route and automatic start, the first viewpoint deliberately faced away from the requested slot. After 8 seconds the mission marked A-01-01 as missed, continued to A-01-03, confirmed the empty shelf via the real camera and mock API, then landed with `COMPLETE_WITH_MISSES`. [Final status](evidence/missed_stop_status.json)
- The start service rejected an existing command publisher. After that publisher left, the mission accepted start and climbed. The abort service stopped the flight at about 0.79 m. Subsequent odometry confirmed hover, and the command topic had zero publishers, allowing operator handoff. [Abort and ownership check](evidence/abort_check.json)
- Three mission unit tests and five perception tests passed. They cover body-frame rotation, limits and wraparound, route parsing, timestamp and identity filtering, and the existing perception regressions.

```bash
source scripts/robotics/activate.bash
/usr/bin/python3 -m unittest discover -s ros2_ws/src/rackonaut_mission/test -v
/usr/bin/python3 -m unittest discover -s ros2_ws/src/rackonaut_perception/test -v
```

## Original captures

- [Drone in the aisle](evidence/01_drone_in_aisle.png) is the live Gazebo viewport during return.
- [A-01-03 through perception](evidence/02_vision_empty.png) shows the actual empty shelf and HTTP 201 receipt during the flight.
- [Flight route](evidence/03_mission_route.png) shows the planned path, actual odometry and final status in RViz from the automatic start run.
- [Uninterrupted 26-second excerpt](evidence/04_continuous_inspection.mp4) comes from 257 consecutive annotated camera frames, recorded during the first three inspection approaches and encoded at the measured 9.89 frames/s.

Integration with Michał's drone and Vahid's backend remains to be validated. See the [launch and handoff guide](../README.md).

## Demonstration package

On 25 November 2026, the quality showcase ran under Ubuntu 22.04 WSL2, ROS 2 Humble and Gazebo Fortress 6.16.0. Inspection `INS-MISSION-20261125-093207-0F98` took **75.8 s**, confirmed **5/5 stops**, found **two damaged cartons**, and landed on the launch pad at `(0.0, 0.0, 0.05)` m. The mock stored ten inventory events across five locations. It returned five pending comparisons and three uninspected locations. The four photo bundles all linked to accepted inventory events.

The presentation stills, three-view recording, report and snapshots below come from that single uninterrupted flight. The external Gazebo camera was repositioned while the drone flew its route. The three views were recorded in parallel and aligned using the host wall-clock times at which the frame files were written. See the [media manifest](demo/media-index.json) for the run ID, timing and alignment data.

| Moment | Original source or export |
| --- | --- |
| Warehouse and pad | [Gazebo view](demo/media/01-warehouse.png) |
| Takeoff | [Gazebo view](demo/media/02-takeoff.png) |
| Autonomous flight in the aisle | [Gazebo view](demo/media/03-autonomous-flight.png) |
| Correct pallet and intact carton | [A-01-01 / P001](demo/quality/Q-95F31DACF9364E9283DF2519D5272D8A/annotated.png) |
| Empty slot | [A-01-03](demo/media/04-empty-slot.png) |
| Unreadable pallet label | [A-01-05](demo/quality/Q-1C6780676A5342E79ED4F528F53EEFE8/annotated.png) |
| Tear | [A-01-02 / P003](demo/quality/Q-ED449E8885264C4EA432B63553567A88/annotated.png) |
| Crushed corner | [A-01-04 / P999](demo/quality/Q-8A8C125575EE4937925658A9BCDE5FBE/annotated.png) |
| Planned and flown route | [Final RViz view](demo/media/05-route-complete.png) |
| Return, landing and touchdown | [Return](demo/media/06-return.png) · [Landing](demo/media/07-landing.png) · [Touchdown](demo/media/08-touchdown.png) |
| Parallel recording, 1920×1080 | [Gazebo, perception and RViz](demo/media/09-continuous-views.mp4) |
| Report and raw results | [Standalone HTML](demo/index.html) · [Report preview](demo/media/10-report-preview.png) · [ROS and API snapshot](demo/run.json) |

The live exporter ran after landing and returned four quality captures with four verified links. For example, the torn-carton inventory observation was captured at `09:33:15.855Z` and its quality photo at `09:33:15.948Z`. The HTML rendered all eight embedded images and its four counters in Chrome at desktop and mobile widths. Offline regeneration after Ctrl+C produced byte-identical HTML. The launch process groups stopped and the mock port closed. A separate restart with the same evidence root produced a fresh ID, empty API history and no inherited captures. See the [export and launch instructions](../README.md#presentation-and-report-export).

### Quality evidence handoff

The [real torn-carton sidecar](demo/quality/Q-ED449E8885264C4EA432B63553567A88/report.json) links a quality event to inventory via `(inspection_id, observation_id)`. The sidecar includes its own `quality_id`, slot, nullable pallet, verdict, reason, linked observation timestamp, separate photo timestamp, ROS camera stamp and native-pixel defect polygon. Its two files are the [original image](demo/quality/Q-ED449E8885264C4EA432B63553567A88/camera.png) and [annotated image](demo/quality/Q-ED449E8885264C4EA432B63553567A88/annotated.png).

The proposed addition for Vahid is `POST /api/quality-observations` with three multipart parts, the JSON sidecar and two PNGs. The server can store the images with that quality record and return its JSON plus two retrievable URLs. Use `(inspection_id, quality_id)` for idempotency. An identical retry returns the existing record. A reused identity with changed metadata or images returns a conflict. If the inventory event has not arrived yet, retain a pending link until the exact event becomes available. The join verifies the slot, pallet and observation timestamp.

Tharindu can request `GET /api/quality-observations?inspection_id=...` and show the independent carton verdict and photo links beside inventory. `OK` and `DAMAGED` are persisted stable verdicts. `UNCERTAIN` indicates inadequate evidence and currently appears in the live preview only. Distinguish a missing quality record from an intact carton and keep quality totals separate from SAP comparisons. The existing [HTTP v1 inventory contract](../../../../contracts/http.md) continues to govern inventory. These quality routes are a proposal for team review.
