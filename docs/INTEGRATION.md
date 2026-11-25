# Integrating Rackonaut

## Stable reference demo

The [`demo-baseline` tag](https://github.com/Adiksoon/rackonaut/tree/demo-baseline) pins commit `6d10e45a49d5034dd6577b187d27f7bf49f1b9c5`. It contains the showcase warehouse, reference drone, perception, five-stop autonomous mission and fixture API. The tested stack is Ubuntu 22.04.5 under WSL2, ROS 2 Humble, Gazebo Fortress 6.16.0 with llvmpipe, system Python 3.10.12 and OpenCV 4.5.4. Use a separate Python virtualenv for the fixture API. See the [environment setup](onboarding/ADRIAN.md#set-up-in-ubuntu-2204-or-wsl2) and [backend setup](onboarding/BACKEND.md#ubuntu-or-wsl).

The launch file uses the [showcase world](../ros2_ws/src/rackonaut_warehouse/worlds/showcase.sdf), [five-stop route](../ros2_ws/src/rackonaut_mission/config/showcase.json) and [marker dictionary](../ros2_ws/src/rackonaut_perception/config/markers.json). The drone leaves the central pad, checks A-01-01 through A-01-05 and lands on the pad. Live observations come from RGB frames. Use the [Mock SAP inventory](../test_data/expected_inventory.json) for expected stock and the [warehouse ground truth](../ros2_ws/src/rackonaut_warehouse/ground_truth/showcase.json) to verify the setup.

### A. Reference drone and mock API · verified

Clone the tag, install the locked mock requirements in a local virtualenv, build the four ROS packages and launch.

```bash
git clone --branch demo-baseline https://github.com/Adiksoon/rackonaut.git rackonaut-demo
cd rackonaut-demo
python3.10 scripts/api/setup.py
scripts/robotics/build
source scripts/robotics/activate.bash
ros2 launch rackonaut_mission showcase.launch.py rviz:=true
```

The launcher starts the mock on `127.0.0.1:8000`, the warehouse and reference drone, perception, preview and Mission Manager. It gives perception and Mission Manager one fresh inspection ID. Add `gazebo_gui:=false view:=false` and omit `rviz:=true` for a headless run. Ctrl+C in the launch terminal stops the processes it owns.

For a separately started mock, run `.venv-backend/bin/python -m uvicorn backend.mock_api:app --host 127.0.0.1 --port 8000` from the repo root and pass `mock:=false backend_url:=http://127.0.0.1:8000` to the launcher. In an activated second terminal, inspect progress with `ros2 topic echo /rackonaut/mission/status --qos-durability transient_local --full-length`. See the [GOAL 04A flight evidence](../ros2_ws/src/rackonaut_mission/docs/VERIFICATION.md).

On 25 November 2026 a clean clone of the GitHub tag built all four packages. Five perception tests, three mission tests and the existing fixture API smoke passed. A headless launch completed inspection `INS-04B-BASELINE` in **75.1 s** with **5/5 API-confirmed stops**, zero misses and touchdown at `(0.0, 0.0, 0.05)` m. The API stored 10 schema-valid camera events for five distinct slots. It reported five pending comparisons and three uninspected locations. Ctrl+C stopped the simulator, ROS bridge, TF, perception, mission and mock processes, and the mock port was released.

```bash
.venv-backend/bin/python scripts/api/smoke.py
/usr/bin/python3 -m unittest discover -s ros2_ws/src/rackonaut_perception/test -v
/usr/bin/python3 -m unittest discover -s ros2_ws/src/rackonaut_mission/test -v
```

### B. Reference drone, team backend and dashboard · blocked

Start Vahid's backend with the Mock SAP inventory and run the replay acceptance below. Launch the reference inspection stack with that backend's base URL. Start Tharindu's dashboard with the same base URL and inspection ID.

```bash
ros2 launch rackonaut_mission showcase.launch.py mock:=false \
  backend_url:=http://127.0.0.1:8000 inspection_id:=INS-TEAM-B-001 rviz:=true
```

Use a fresh ID for each run. The backend and dashboard owners provide their launch commands with their branches. The acceptance gate is a live flight with API-accepted camera events and a dashboard showing the backend's results for that inspection.

### C. Team drone, team backend and dashboard · blocked

Build and activate the combined ROS workspace. Use Michał's launch procedure to start the existing `rackonaut` world and spawn his drone independently on the pad. Resolve the file with `ros2 pkg prefix --share rackonaut_warehouse` and use `worlds/showcase.sdf` within that directory. Use one Gazebo world and clock, one camera source and one command publisher. After the drone and backend acceptance checks, launch perception and Mission Manager separately, using the same fresh ID and URL in both activated terminals.

```bash
ros2 run rackonaut_perception inspect --ros-args -p use_sim_time:=true \
  -p inspection_id:=INS-TEAM-C-001 -p backend_url:=http://127.0.0.1:8000
ros2 run rackonaut_mission run_mission --ros-args -p use_sim_time:=true \
  -p inspection_id:=INS-TEAM-C-001 -p backend_url:=http://127.0.0.1:8000
```

The standalone mission waits for `ros2 service call /rackonaut/mission/start std_srvs/srv/Trigger '{}'`. Start the dashboard with the same ID and API URL. Use the [mission guide](../ros2_ws/src/rackonaut_mission/README.md) for the separate vision viewer, abort, route override and manual fallback. Variant A provides the reference-drone fallback.

## Team module acceptance

### Michał · drone and camera

1. Confirm Fortress and SDFormat 1.8, the model license, the launch command and the independent spawn. Start at world XY `(0, 0)` and yaw zero on the marked pad. Check model clearance and record the resting altitude of its controller origin.
2. Verify `/rackonaut/camera/image_raw` and `/rackonaut/camera/camera_info` have matching stamps, dimensions and `rackonaut_camera_optical_frame`. Check valid intrinsics, `rgb8` or `bgr8`, sensor-compatible QoS and about 10 Hz. The reference uses 320×240. Check live ArUco framing at both shelf heights with the candidate camera.
3. Verify `/rackonaut/drone/odom`, the `rackonaut_odom` → `rackonaut_base_link` TF and the static camera optical transform. Confirm consistent transforms, advancing simulator stamps, metres and radians, and odometry aligned with the route. The warehouse uses +X along the aisle, +Y towards the inspected rack and +Z up. Adjust the route and pad Z to the candidate's odometry origin and camera geometry if needed.
4. With Mission Manager idle, send bounded teleop commands through `/rackonaut/drone/cmd_vel`. Verify body-frame +X forward, +Y left, +Z up and positive yaw. Confirm hover or stop at zero command and record behavior on stale commands. Stop teleop before arming the mission. Verify return and touchdown first, or set the mission's ROS parameter `land:=false` for the first hover-only trial.
5. Run one actual camera inspection before the complete route. Retain the model commit, SDF and launch instructions, ROS topic and frame evidence, and observation accepted by the API. See the [ROS contract](../contracts/ros.md).

### Vahid · backend and comparison

Use the [11 observations recorded in GOAL 04A](../ros2_ws/src/rackonaut_mission/docs/evidence/api_observations.json) on a development backend loaded with the checked-in [Mock SAP inventory](../test_data/expected_inventory.json).

1. Choose an unused `INS-...` ID. Query its observations, discrepancies and summary before posting. Expect zero events, zero inspected slots and all eight slots uninspected.
2. POST the 11 JSON objects individually to `/api/observations`, changing only `inspection_id` to the fresh replay ID. Preserve each real `observation_id` and UTC capture `timestamp`. Each first submission should return HTTP 201 with the accepted event. Replay one identical object and expect HTTP 200 and unchanged event count. Reuse the same identity with a different valid timestamp and expect HTTP 409. For a slot with two events, send the newer event before the older one and verify the newer capture remains the summary result.
3. Read the three GET routes with the replay ID. Expect 11 distinct events in UTC capture order, five observed slots, eight total slots and four discrepancies. Check the latest per-slot event IDs and values. Equal timestamps use the lexicographically greatest observation ID, and the summary stays scoped to the requested inspection.
4. Check the outcomes below and repeat the empty GET checks with another unused inspection ID. Then confirm one live camera event in variant B before accepting a full flight. The fixture API returns `pending` for new observations. The team backend must perform the comparison.

```bash
# Save one observation object with the replay ID as event.json.
curl -i -H 'Content-Type: application/json' --data-binary @event.json "$BACKEND/api/observations"
curl -fsS "$BACKEND/api/observations?inspection_id=$RUN"
curl -fsS "$BACKEND/api/discrepancies?inspection_id=$RUN"
curl -fsS "$BACKEND/api/summary?inspection_id=$RUN"
```

Set `BACKEND` to the base URL and `RUN` to the chosen replay ID. See the [HTTP contract](../contracts/http.md) and [OpenAPI schema](../contracts/openapi.json).

| Slot | Expected outcome |
| --- | --- |
| A-01-01 | `match` |
| A-01-02 | `wrong_pallet` |
| A-01-03 | `missing_pallet` |
| A-01-04 | `unexpected_pallet` |
| A-01-05 | `unreadable_label` |
| A-01-06 to A-01-08 | `uninspected` |

### Tharindu · dashboard

Configure the base URL and let the operator select the current inspection ID. Refresh that inspection's summary and discrepancies during flight, display inspected slots separately from event history, and show match, discrepancy, unreadable, uncertain, pending and uninspected states from backend data. Render the final counts and per-slot results after landing. Check an unused ID, a live run, a repeated event at one slot and an unavailable API. Share the launch command, browser access URL and screenshots or request evidence for the same inspection. Use the existing fixture API for development and the replay above to accept the full backend connection.

## Integration gates

Run these gates in order on one integration host. Start from a known commit and a fresh Rackonaut shell. Record the commit, Gazebo and ROS versions, command, observed result, and any retained log or sample payload. Confirm changes to shared interfaces with the owners before using them in another gate.

| Gate and prerequisites | Run | Success and first diagnostic |
|---|---|---|
| 1. Warehouse. Robotics smoke passes and the warehouse package supplies a world. | Run `scripts/robotics/world` for the reference first, then the warehouse branch's documented world command. Run the world by itself. | Clock advances and the rack geometry and collisions are in the expected position. Inspect the simulator log for missing resources and confirm the world name and generation. |
| 2. Drone. A working reference world and a candidate drone are available. | Run `scripts/robotics/smoke --reference`, then spawn the candidate using its documented launcher in the reference world. Use one teleop publisher. Inspect ROS camera and calibration endpoints while the model moves. | The model responds to a bounded command, camera frames arrive, calibration and frames agree, and stop or hover is observable. Inspect simulator topics, bridge mapping and ROS endpoint QoS in that order. |
| 3. Warehouse and drone. Both stand-alone gates pass. | Run the warehouse launcher. Spawn the same drone at the contract pose. Exercise a short manual pass between racks. | Spawn succeeds, gravity and collisions are credible, and control and images continue. Check spawn pose, model resource paths and the world's sensor/physics systems. |
| 4. Computer vision. The camera contract passes and vision can read the synthetic fixture. | Point the vision node at the real simulated image stream. Use a labeled, known slot and retain the image and its observation. | Vision emits a valid observation attributable to the image. Compare separately against ground truth. Check encoding, calibration, topic QoS, simulation timestamps and slot association. |
| 5. Backend. Fixture API checks pass and the actual backend can ingest the fixtures. | Start the backend on the integration host. Post the same fixture used in the HTTP smoke test, then send one real vision observation and query the same inspection. | The actual backend reports the expected comparison and handles observation replay consistently. Check input validation, selected inspection and expected inventory. |
| 6. Dashboard. Dashboard views work against the mock and the backend exposes the contract. | Change the dashboard API base URL to the actual backend and load the same inspection. | Summary and discrepancy rows agree with the backend responses, including pending or uncertain states. Check network URL, response status, browser console and CORS. |
| 7. End-to-end. All previous gates pass on the same baseline. | Use the branch-provided launch commands in order. Teleoperate to a known slot, then verify the evidence through camera, CV, API and dashboard. | One planned match and one planned discrepancy appear with traceable observations. Retain that run's commit and evidence. If a gate fails, check the last working boundary first. |

Until component owners supply their launch commands, use the [role guides](../README.md#start-here) for reference runs. Keep only the intended publisher active for the camera or command topic being tested, and stop processes from the terminal that started them.
