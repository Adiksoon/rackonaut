# Rackonaut Warehouse Safety

The safety showcase adds an independent ROS 2 interlock, two three-segment towers per functional aisle, a tower at the shared transfer apron, and a simulated worker in a high-visibility vest. The Control Center keeps the original planner, camera, flight controller and inspection report. The safety variant adds live access status, a fixed overview camera from Gazebo, event history and labeled Simulation Controls.

## Launch

Use the project's Ubuntu 22.04 or WSL2 environment with ROS 2 Humble and Gazebo Fortress. The infrastructure adapter builds against the Fortress development packages `libignition-transport11-dev` and `libignition-msgs8-dev`. From the repository root:

```bash
python3.10 scripts/api/setup.py
scripts/robotics/build
source scripts/robotics/activate.bash
ros2 launch rackonaut_control control.launch.py safety:=true
```

Open [Rackonaut Control Center](http://127.0.0.1:8765). To see the Gazebo desktop view as well, add `gazebo_gui:=true`. The browser's **Warehouse Safety** panel includes the live overview when using the headless simulator. The existing launch without `safety:=true` remains the independent Control Center demo.

With the worker outside, leave **Aisle A** selected and use **Start Inspection**. Watch the three-second warning and red reservation on the map and in the overview. For an occupied-start demonstration, use **Enter aisle A** and wait for **Worker present** before sending a start request. Use **Move outside**, confirm the field is clear, and send a new request. To demonstrate an intrusion, start an inspection with the worker outside, wait for the drone to enter A, then use **Enter aisle A**. The alarm and event history stay visible after Abort. Restart the reference stack to reset a recovery hold. With the default archive, the event log persists at `ros2_ws/log/ros/control/safety-events.jsonl`.

## Presence and access

The **simulated presence sensor** consumes the actual Gazebo pose of the named worker, published by Fortress PosePublisher and bridged to a dedicated ROS 2 topic. Controlled motion advances the visible model through the warehouse with incremental Gazebo `set_pose` commands. The interlock uses independently received, advancing samples and rectangular ground-plane fields with a 28 cm margin for the modeled worker. Unchanged or missing sample timestamps time out after 0.75 s of wall time. The overview displays the simulated worker on camera. The map shows monitored fields and access states.

The initial rectangles cover aisle A, aisle B and the transfer apron including the pad. Intersections between the actual route segments and these rectangles determine the reserved set, including the return route. C is unmonitored. Green means personnel access is open. The panel separately reports worker occupancy, so an open unreserved aisle can legitimately show a worker present while a different aisle is reserved.

On a clear request, the Manager triggers the three-second amber warning. It requires advancing presence and odometry, at least 0.8 s of clear samples, a stationary drone at the pad, and acknowledgment of the red visual updates from Gazebo before issuing a run-specific permit. Mission Manager checks for that permit itself. An occupied or unverified request is rejected and requires a fresh operator action even after the field clears. No browser code publishes velocity. A normal mission releases after Mission Manager reports landing and current odometry agrees. Red stays on in the reserved fields until release.

During a reservation, intrusion is latched as a flashing red alarm. Presence, odometry or command-infrastructure faults also restrict access. Safety Manager calls the existing ROS Abort service and records first in-field sample receipt, dispatch and Mission Manager confirmation. The drone stops and holds in the simulation. An airborne interruption keeps the required fields restricted and prevents another dispatch. Recovery for this demo uses a simulator restart.

## Implementation and limits

The simulation uses the existing Fortress UserCommands services and its PosePublisher. GPU LiDAR and the Humble `LaserScan` bridge are available. Complete scanner coverage of the rack occlusions and the crossed apron, plus self-filtering the drone at low altitude, would require extra sensors and calibration. Coverage in this variant is limited to the named worker inside the defined simulator fields. The included worker was made from native SDF geometry. [Fortress sensors](https://gazebosim.org/docs/fortress/sensors/) · [Fortress UserCommands](https://gazebosim.org/api/gazebo/6/classignition_1_1gazebo_1_1systems_1_1UserCommands.html) · [ROS–Gazebo bridge](https://github.com/gazebosim/ros_gz/tree/humble/ros_gz_bridge)

Before physical deployment, the team would need a site-specific risk assessment, validated sensor coverage and stopping distances, suitable interlocks and access barriers, an independent stop chain, an approved airborne recovery procedure, and validation with the actual aircraft, payload and warehouse. The demonstration's wall-clock response measures only the simulator and ROS stop path from the first sensor sample to the Mission Manager acknowledgment.

## Demonstration results

The scenarios ran on 25 November 2026 with Ubuntu 22.04.5 WSL2, ROS 2 Humble, Gazebo Fortress 6.16.0, llvmpipe and Chrome 158.0.8127.88. Playwright operated the actual browser controls. The overview and onboard camera frames were captured from the live simulator.

| Test | Observed result | Evidence |
| --- | --- | --- |
| A · Normal inspection | Amber warning, acknowledged red reservation, departure, 8/8 confirmed stops, 2 linked damage findings, landing after 114.8 s, and return to green | [Browser after landing](docs/evidence/05-landed-released.png) · [HTML report](docs/evidence/inspection-a/index.html) · [State](docs/evidence/telemetry/test-a-completed.json) |
| B · Worker before start | Worker moved into A through Simulation Controls. The system rejected Start at the pad. After the model left, the operator sent a separate request. | [Blocked request](docs/evidence/02-blocked-by-worker.png) · [State](docs/evidence/telemetry/test-b-blocked.json) |
| C · Intrusion in flight | Worker entered A during transit. The red tower flashed, ROS reported Abort, and the drone held at about 0.79 m. A and the apron stayed restricted, with B open. A second dispatch returned HTTP 409. | [Browser alarm](docs/evidence/09-intrusion-aborted.png) · [Overview and history](docs/evidence/08-intrusion-gazebo-panel.png) · [State](docs/evidence/telemetry/test-c-abort.json) |
| D · Independent aisles | A and the transfer apron were reserved during A's flight. The worker was in B, and B's green access signal remained available. | [Gazebo red A and green B](docs/evidence/04-gazebo-red-b-green.jpg) · [State](docs/evidence/telemetry/test-d-independent.json) |
| E · Missing presence data | The dedicated presence bridge was temporarily paused while Gazebo, odometry and the light adapter kept running. Start was rejected with stale data, and restoring the bridge left the rejected request stopped. A separate pause during takeoff triggered Abort and held access restrictions after the feed returned. | [Browser with stale sensor](docs/evidence/07-stale-sensor.png) · [Start denied](docs/evidence/telemetry/test-e-fault.json) · [Feed restored](docs/evidence/telemetry/test-e-restored.json) · [In-flight loss](docs/evidence/telemetry/active-sensor-loss.json) |

The intrusion run was `INS-CONTROL-20261125-103742-9F3C811E`. On that run, the first in-field ROS pose sample reached Safety Manager **6.34 ms** before the intrusion event, **56.58 ms** before dispatch of the Abort service call, and **256.35 ms** before Safety Manager received Mission Manager's `ABORTED` state. On the separate in-flight fault trial, the interval from pausing the bridge to receipt of `ABORTED` was **1.00 s**. These are single-run wall-clock measurements. During the intrusion mission's preparation window, a direct ROS Start service call returned failure before the interlock issued a permit. [Event log](docs/evidence/telemetry/safety-events.jsonl) · [Direct ROS probe](docs/evidence/telemetry/interlock-probe.json)

[28-second browser recording](docs/evidence/warehouse-safety-demo.mp4) · [Green towers](docs/evidence/01-green.jpg) · [Amber preparation](docs/evidence/03-gazebo-yellow.jpg) · [Reservation map](docs/evidence/04-flying-reserved.png) · [Intrusion lamp off phase](docs/evidence/09-gazebo-intrusion-second.jpg) · [Intrusion lamp on phase](docs/evidence/10-gazebo-intrusion-third.jpg)

The default Control Center launch also completed the original full B route in 83.0 s with three scoped observations, one damage finding and confirmed touchdown. The browser checked its Full and Custom previews before dispatch. The API contract and robotics suites passed 20 tests. The safety SDF validated, and the generated Goal 06 world, layout and markers matched byte for byte. [Fallback B ROS and API snapshot](docs/evidence/inspection-b-fallback/run.json)
