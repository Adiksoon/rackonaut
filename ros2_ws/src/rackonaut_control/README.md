# Rackonaut Warehouse Control Center

The local browser application plans a simulated inspection, dispatches Mission Manager, shows actual odometry and camera detections, and opens the existing portable HTML report after landing. The original [`demo-quality` showcase](../rackonaut_mission/README.md#presentation-and-report-export) remains an independent fallback.

## Launch

From the repository root on Ubuntu 22.04 or WSL2, with ROS 2 Humble and Gazebo Fortress:

```bash
python3.10 scripts/api/setup.py
scripts/robotics/build
source scripts/robotics/activate.bash
ros2 launch rackonaut_control control.launch.py
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). The launcher starts the extended world, the reference drone and its ROS bridge, the Control Center, and the separate inventory fixture on port 8000. Use `gazebo_gui:=true` to open the simulator window as well. Use `http_port:=8766` or `mock_port:=18092` to avoid a port conflict. Run one controller stack in the ROS domain. The shell activation honors `RACKONAUT_ROS_DOMAIN_ID` and `RACKONAUT_GZ_PARTITION` for an isolated run.

1. Select **Aisle inspection** and click A or B on the map or in the scope panel. Select multiple aisles in the same panel. **Full inventory** includes all 11 functional locations, and **Custom inspection** uses only the clicked locations. Aisle C is visibly decorative.
2. Toggle **Package quality** to add carton inspection to any of the three scope modes. Select **Start Inspection**. Live inspection shows the camera, the current target, position, planned and flown paths, visited waypoints, accepted observations, damaged cartons and elapsed time.
3. Open **Inspection results** and the generated HTML report after completion. Reports remain in history. Use **Plan another inspection** to start with a new selection and ID, or **Plan reinspection** to select missed, uncertain, unreadable or backend-flagged locations.
4. **Abort inspection** calls the ROS abort service. The reference drone holds position after the stop. A stopped drone away from the pad prevents another dispatch. Restart the simulator stack to reset an aborted demo. Ctrl+C stops the launcher and its workers.

The default archive is `ros2_ws/log/ros/control/reports/<inspection_id>/`. It includes the HTML, the ROS and API snapshot and any stable photo evidence. `data_dir:=/absolute/path` selects a different archive root.

The [adaptive inspection demonstration](../../../docs/ADAPTIVE_INSPECTION.md) uses a separate warehouse profile and an opt-in checkbox. The guide includes the tested route, browser recording and safety observations.

## Warehouse and route

The variant `control_showcase.sdf` contains the original eight A slots and adds B-01-01, B-01-02 and B-02-01. The additional slots have ArUco IDs 8–10 and the additional pallets use IDs 25 and 26. The physical B cases are a torn carton, an intact carton and an empty slot. The build publishes the SVG geometry inputs and the marker dictionary from the same generator. These configuration files contain viewpoint geometry and marker identities. The runtime derives inventory and carton quality from the camera.

The planner groups selected positions by aisle. Before crossing between aisles, it returns to the front transfer corridor at world X = 2.1 m, ahead of the rack faces. Empty-slot-ID waypoints are transit instructions. The existing positional controller flies them and returns through the corridor. Each planned slot is distinct. The simulated odometry and the two ROS paths drive the top-down map.

## ROS and team integration

The loopback web service subscribes to ROS odometry, mission status, planned and flown paths, and annotated images. It dispatches the existing Mission Manager and perception processes with the chosen route and a fresh ID. The browser polls the service for telemetry and live JPEG frames from those topics. Start and Abort use the existing ROS services. Mission Manager owns velocity commands.

In this launcher, perception only persists observations and quality evidence for the current `INSPECT` target of the matching inspection ID. Other visible tags can appear in the camera image. The table separates planned, visited, confirmed, missed and outside-scope slots. Stable quality captures link to an inventory observation, and the HTML exporter verifies the link.

For a team backend, launch with `mock:=false backend_url:=http://host:port`. The selected IDs must exist in its `GET /api/inventory/expected` response. Align aisle B with Vahid using [the separate fixture extension](../../../test_data/control_inventory_extension.json). The normal mock, its expected inventory and the HTTP v1 contract keep their existing defaults. The enlarged fixture reports `pending` for newly captured events. The comparison and discrepancy fields come from the configured backend. Tharindu can use the same inspection ID and API endpoints for business views and use the existing [quality handoff proposal](../rackonaut_mission/docs/VERIFICATION.md#quality-evidence-handoff) when those endpoints are agreed. Michał's model must satisfy the shared ROS topics, frames, velocity and camera contracts before switching the reference drone.

The prototype binds to loopback for a local simulation and uses fixed, unobstructed corridors. It assumes the published showcase geometry, simulator-derived odometry and the reference camera. The ROS bridge and JPEG serving use the existing rclpy and OpenCV environment. The available workspace does not ship rosbridge or web_video_server. Their upstream documentation covers general ROS WebSocket and image streaming. [rosbridge](https://github.com/RobotWebTools/rosbridge_suite) · [web_video_server](https://github.com/RobotWebTools/web_video_server)

## Verification

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
