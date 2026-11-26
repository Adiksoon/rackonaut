# Integrating Rackonaut

Use the [main README](../README.md#start-here) for the integrated demonstrator. Build from a fresh checkout and run each demo separately with its own data directory. Record the commit, software versions, launcher, route, ROS domain, inspection ID and outcome.

| Gate | Check |
| --- | --- |
| Build and contracts | Run the prerequisite check, install the locked backend environment, build the ten ROS packages and run the [ROS and HTTP tests](../README.md#tests). |
| Business Demo | Run the short adaptive warehouse with Mock SAP. Verify the three selected locations, camera observations, comparisons and report. |
| Full Robotics Demo | Start the aerial profile with virtual Safety presence. Verify sensor localization, reservations, both low-level stops, dock contact and the result in Mock SAP. |
| Engineering Showcase | Open a single live viewer or replay the saved Evidence bag in a separate ROS domain. Check that 2D Control Center is available on the same live stack. |

## Route and operator constraints

- Use **A-01-01 and A-01-03** for the aerial profile. In AUDIT 01, this route reached physical dock contact in Gazebo and released the Safety reservations. It ran with virtual ground-zone presence, active onboard LiDAR and simulated dock contact.
- The aerial transition from the higher **A-01-02** to **A-01-03** repeatedly triggered `ROUTE_BLOCKED`. Measured LiDAR returns aligned with `steel_35`, a rendered crossbar in shaft A. The stop in the audit reproduced the previous estimated stop within about 5 mm. Recovery was authorized, stopped after 7.7 s, and retained D and A reservations. The tests cover this route, not other combinations of levels. [Archived Showcase failure](engineering-evidence/recovery-blocked.json)
- The refreshed Control Center shows raw video. The start latch resets on each dispatch and is set on receipt of an annotated image after the job has status. The latch has no age check. Use the Engineering Showcase Vision view for annotated frames during flight. [Engineering Showcase](ENGINEERING_SHOWCASE.md)
- The benchmark on WSL2 found substantial render cost with laser Safety and optional RViz. The full live demo uses virtual presence. The laser profile's fixed A, B and T fields are optional. Safety, flight dynamics and docking are simulated, and the backend's expected inventory and product catalog are synthetic. [Performance evidence](engineering-evidence/laser-performance.json) · [Safety sensor scope](../ros2_ws/src/rackonaut_safety/docs/SENSOR_SAFETY.md)

## Stable reference demo from GOAL 04B

The historical [`demo-baseline` tag](https://github.com/Adiksoon/rackonaut/tree/demo-baseline) pins `6d10e45a49d5034dd6577b187d27f7bf49f1b9c5`. It contains the warehouse, reference drone, perception, a five-stop autonomous route and the fixture API. The audited setup was Ubuntu 22.04.5 on WSL2, ROS 2 Humble, Fortress 6.16.0 with llvmpipe and system Python 3.10.12.

For historical reproduction, use a checkout of that tag and its four-package workspace. The separate `demo-complete` tag documents a later 11-location run.

```bash
git clone --branch demo-baseline https://github.com/Adiksoon/rackonaut.git rackonaut-demo
cd rackonaut-demo
python3.10 scripts/api/setup.py
scripts/robotics/build
source scripts/robotics/activate.bash
ros2 launch rackonaut_mission showcase.launch.py gazebo_gui:=false view:=false
```

On 25 November 2026 the tagged headless run `INS-04B-BASELINE` finished in 75.1 s, confirmed A-01-01 through A-01-05, and touched down. Its fixture API stored ten valid live camera events and reported five pending comparisons and three uninspected locations. Ctrl+C released the launcher processes and mock port. These are GOAL 04B observations from the tag. [GOAL 04A/04B verification](../ros2_ws/src/rackonaut_mission/docs/VERIFICATION.md) · [11-location demo](DEMO_COMPLETE.md) · [Original integration PR](https://github.com/Adiksoon/rackonaut/pull/1)

## Acceptance gates for independent modules

Before changing shared interfaces, review the [ROS contract](../contracts/ros.md), the [HTTP contract](../contracts/http.md) and the [team register](TEAM_TASKS.md). Keep one simulator clock, one publisher for the selected camera and one flight-command owner for the test domain.

| Boundary | Evidence for acceptance |
| --- | --- |
| Warehouse and drone | Record model, license, SDF version, spawn, model resources, physics and collisions. Verify bounded body-frame motion and zero-command hover or stop before enabling autonomous control. |
| Camera and ROS transport | Match image and camera-info calibration, dimensions, timestamps, optical frame and QoS. Verify visible ArUco framing at both shelf heights, canonical odometry and a single TF owner per edge. Retain a live camera observation accepted by the API. |
| Aerial profile | Check rotor and collision envelopes in the shaft and tunnel, LiDAR and IMU timing, docking contact, reservations and a complete dock-to-dock run before evaluating Recovery. [Drone checklist](onboarding/MICHAL.md) · [Aerial geometry](AERIAL_INFRASTRUCTURE.md) |
| Backend | Replay known observations under a new inspection ID. Exercise first POST (201), exact replay (200), conflicting event identity (409), out-of-order observations and isolation between inspections. Then ingest a real camera event. [GOAL 04A observation sample](../ros2_ws/src/rackonaut_mission/docs/evidence/api_observations.json) |
| Dashboard | Compare the same inspection with the HTTP summary and discrepancies. Verify empty, pending, uncertain, completed and unavailable states. Record the URL, command, inspection ID and evidence. |
| End to end | Archive a run with a traceable correct reading and discrepancy, then confirm the operator can inspect the evidence and open the report. |

The tests and replay gates from GOAL 04B remain useful for accepting an independently supplied module. The separate backend proposal from that period predates the integrated Mock SAP delivered in GOAL 17. [Mock SAP comparisons and replay](SAP_BUSINESS_INTELLIGENCE.md)
