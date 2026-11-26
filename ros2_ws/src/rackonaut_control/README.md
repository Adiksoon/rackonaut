# Rackonaut Warehouse Control Center

The Control Center selects warehouse locations, dispatches an autonomous inspection, shows the live camera and route, and opens the portable HTML report after landing. The browser is served on loopback.

## Launch

Run the [Quick Start](../../../README.md#start-here) on Ubuntu 22.04 or WSL2 with Humble and Fortress. Use [Business Demo](../../../README.md#a-business-demo) for the short adaptive warehouse and Mock SAP. Use [Full Robotics Demo](../../../README.md#b-full-robotics-demo) for aerial corridors, LiDAR–IMU localization, docking and Recovery. Calling `ros2 launch rackonaut_control control.launch.py` with default arguments starts the development fixture profile.

Open [Control Center](http://127.0.0.1:8765). Use `gazebo_gui:=true` to open the simulator window or override ports with `http_port:=8766 mock_port:=18092`. Run one stack in the ROS domain. The environment honors `RACKONAUT_ROS_DOMAIN_ID` and `RACKONAUT_GZ_PARTITION` for isolated runs.

1. Use **By aisle**, **Full inventory** or **Selected locations** in the plan. The warehouse has 11 functional positions in A and B. Aisle C is decorative. For the aerial profile use A-01-01 and A-01-03.
2. In **Inspection options**, select package damage and adaptive retries as desired. Start the mission. **Live flight** shows the raw camera, estimated position and route. Choose **3D view** to view the same plan and telemetry in Digital Twin.
3. Open **Results** for the scoped results and report or reinspection planning. Expand **Inventory comparison** when using Mock SAP. The report and evidence remain available after landing.
4. **Stop inspection** requests a ROS abort. With Recovery enabled, review the proposal in the operator panel and explicitly authorize a safe return. A failed return keeps the active safety reservations. Ctrl+C stops the stack and its workers.

The archive is `ros2_ws/log/ros/control/reports/<inspection_id>/`. It includes HTML and the ROS/API snapshot with stable photo evidence when available. `data_dir:=/absolute/path` sets a separate archive and database root.

## Service Center

Set a local code in the launch shell and use Full Robotics. Enter the same code in the **Service** tab. The code prompt keeps it out of terminal history.

```bash
read -rsp 'Service code: ' RACKONAUT_SERVICE_CODE
printf '\n'
export RACKONAUT_SERVICE_CODE
scripts/robotics/checkpoint live
```

The default service session lasts 15 minutes and can be ended with **Lock Service**. Configure a different duration with `RACKONAUT_SERVICE_SESSION_SECONDS` (1–3600). Five unsuccessful attempts within a minute temporarily block unlocks on this local server. The service session uses an HTTP-only, same-site cookie. Direct access to the state or calibration actions also requires a valid session. The short Business and fixture profiles show calibration as unavailable.

**Start Calibration** locks new dispatches. Mission Manager ends the current inspection early and uses its reserved energy return, guarded by sensor-based localization, onboard LiDAR and Safety. Inspect **Live flight** during the return or **Results** for the interrupted inspection and its retained observations. **Emergency stop** remains available from each tab during flight, including when Service is locked. If the return aborts, use the existing Emergency & Recovery Center and explicitly authorize the proposed return after clearing the hazard.

At the dock, the Gazebo contact switch, stable estimated position, fresh sensors and a released Safety reservation gate the workspace. A docked, idle drone creates a draft without dispatch. **Cancel Calibration** waits for a safe dock before unlocking production. An expired service session leaves the return supervised by the same ROS nodes. After a Control Center restart, a saved draft keeps dispatch locked and must be cancelled after physical dock verification.

The draft in `data_dir/calibration-draft.json` starts with zero storage locations, zero waypoints and no approved measurement map. The production localization map is preconfigured reference geometry. The existing camera and flight telemetry remain available in the workspace. Manual flight, mapping and route recording are unavailable there.

Send the `code` in a JSON `POST /api/service/unlock`. The returned session authorizes `GET /api/service/state` and JSON POSTs to `/api/service/lock`, `/api/service/calibration/start` and `/api/service/calibration/cancel`. Start accepts an optional `warehouse_name`. Lock and cancel take an empty JSON object. [ROS message flow](../../../contracts/ros.md#warehouse-calibration-initialization)

## Warehouse and route

The base `control_showcase.sdf` adds B-01-01, B-01-02 and B-02-01 to the eight A slots. The B cases include torn and intact cartons and an empty slot. The generator publishes shared scene geometry and the marker dictionary. Inventory and visible carton quality are derived from the camera. The short profile uses the front transfer corridor, and the aerial profile follows the overhead infrastructure and reserved descents. [Adaptive warehouse](../../../docs/ADAPTIVE_INSPECTION.md) · [Digital Twin](../../../docs/DIGITAL_TWIN.md) · [Route constraints](../../../docs/INTEGRATION.md#route-and-operator-constraints)

## ROS and team integration

The loopback service subscribes to odometry, mission status, paths, raw images and annotated images. Each dispatch creates a fresh inspection ID and starts Mission Manager and perception. The JPEG endpoint serves the raw stream. An annotated frame latches perception readiness for dispatch, with no frame-age check. Use the [Engineering Showcase Vision view](../../../docs/ENGINEERING_SHOWCASE.md#engineering-live) to see annotations. Mission Manager owns ROS velocity commands. The backend observation contract and existing start and abort services remain the integration interfaces.

Perception stores observations and evidence for the current scoped target. Other visible tags can appear in the camera image. Stable quality captures link to an inventory observation, and the HTML exporter verifies the link. Use `mock:=false backend_url:=http://host:port` for an independent backend that implements the contract and recognizes the selected inventory IDs. The fixture returns `pending` for new observations, while Mock SAP derives comparisons and actions locally. An independent drone model must first pass the [module acceptance gates](../../../docs/INTEGRATION.md#acceptance-gates-for-independent-modules).

## Historical fixture profile verification

On 25 November 2026, two uninterrupted runs were dispatched in Chrome with Playwright through **Start Inspection** on the same launched stack. Both used package quality, headless Gazebo Fortress on Ubuntu 22.04.5 WSL2, ROS 2 Humble and the extended fixture API. The browser received annotated camera frames in both aisles and opened the generated reports. The fixture recorded one actual observation per selected location and returned `pending` for each comparison.

| Scope | Inspection ID | Elapsed | Visited / confirmed | Missed | Stable damage | Report |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| A | `INS-CONTROL-20261125-100908-BA736FC2` | 114.6 s | 8 / 8 | 0 | 2 | [HTML](docs/evidence/aisle-a/index.html) · [ROS and API snapshot](docs/evidence/aisle-a/run.json) |
| B | `INS-CONTROL-20261125-101105-57AB164A` | 83.0 s | 3 / 3 | 0 | 1 | [HTML](docs/evidence/aisle-b/index.html) · [ROS and API snapshot](docs/evidence/aisle-b/run.json) |

Both reports confirmed touchdown. A-01-07 produced an accepted `uncertain` observation. A-01-02, A-01-04 and B-01-01 produced stable damage findings with camera evidence. B-01-02 showed an intact carton, and B-02-01 was empty. Locations from the other aisle were shown as outside scope.

[30-second live browser capture](docs/evidence/mission-from-browser.mp4) · [A planning](docs/evidence/01-plan-a.png) · [A live](docs/evidence/02-live-a.png) · [A results and photos](docs/evidence/04-details-a.png) · [B live](docs/evidence/06-live-b.png) · [B results and photos](docs/evidence/08-details-b.png) · [Custom planning](docs/evidence/09-custom-plan.png)

A third browser dispatch, `INS-CONTROL-20261125-101309-A1BBDE22`, used **Custom inspection** for A-01-01 and B-01-01 with quality off. Odometry showed the transfer corridor in use. The drone landed after 84.5 s with exactly two scoped observations and zero quality captures. The browser also previewed all 11 positions in both **Full inventory** and two-aisle modes. A separate airborne **Abort inspection** test held at about 0.61 m, and the UI disabled a fresh dispatch off the pad. [Cross-aisle results](docs/evidence/10-cross-aisle-results.png) · [ROS and API snapshot](docs/evidence/cross-aisle/run.json) · [Dispatch disabled after abort](docs/evidence/12-abort-dispatch-locked.png)

Replaying the recorded A result in the browser, **Plan reinspection** sent a custom plan for A-01-05 (unreadable label) and A-01-07 (uncertain occupancy) to the running planner. This check ended at plan preview.

The workspace build, 17 contract and robotics unit tests, and Gazebo SDF validation passed. The separate `quality_showcase.sdf` generated byte-for-byte identically to the generator at `demo-quality`.
