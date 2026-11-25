# Rackonaut autonomous inspection mission

This package runs the reference drone from its launch pad through the five P0 inspection viewpoints in the showcase warehouse. It climbs, follows the aisle, points the camera at each location, holds for a new observation confirmed by the API, returns and lands. The observation producer remains the existing perception node.

## Run the showcase

From the repository root in the Rackonaut ROS 2 Humble environment, prepare the existing [mock API virtualenv](../../../docs/onboarding/BACKEND.md), then run:

```bash
scripts/robotics/build
source scripts/robotics/activate.bash
ros2 launch rackonaut_mission showcase.launch.py rviz:=true
```

The launch file starts the mock on `127.0.0.1:8000`, the Fortress warehouse and independently spawned reference drone, perception, its existing camera viewer and the mission. RViz is optional. Each launch generates a fresh inspection ID and gives the same ID and backend URL to perception and mission. Startup waits for odometry, a command receiver and the perception service. The mission remains visible after landing. Press Ctrl+C to stop the demo processes. Use `gazebo_gui:=false view:=false` for a headless run and `--show-args` to list launch options.

Use a different mock port if the default is occupied. Pass both `mock_port:=18085` and `backend_url:=http://127.0.0.1:18085`. To use a running external backend, pass `mock:=false backend_url:=http://host:port`. To select an explicit fresh run ID, add `inspection_id:=INS-MISSION-DEMO-001`.

## Progress and operator controls

The ROS topics below are relative to `/rackonaut/mission` and use reliable, transient-local delivery. The RViz setup shows the planned route in blue, the observed path in green, a heading arrow, the launch pad, and live counts and stage. In RViz, green means the API accepted a usable observation. Amber flags an unreadable label, uncertainty or a missed location. In the existing vision window, the operator can see what the camera actually detected.

| Topic | Type | Content |
| --- | --- | --- |
| `status` | `std_msgs/msg/String` | JSON with stage, target, position and yaw, elapsed wall seconds, visited and missed IDs, confirmed API events and touchdown state |
| `plan` | `nav_msgs/msg/Path` | Configured path in the odometry frame |
| `path` | `nav_msgs/msg/Path` | Positions and yaw sampled from odometry during flight |
| `markers` | `visualization_msgs/msg/MarkerArray` | Waypoint, pad, drone and progress graphics |

```bash
# Launch with autostart:=false to wait for the operator.
ros2 service call /rackonaut/mission/start std_srvs/srv/Trigger '{}'
ros2 service call /rackonaut/mission/abort std_srvs/srv/Trigger '{}'
ros2 topic echo /rackonaut/mission/status --qos-durability transient_local --full-length
```

Use one command publisher. The mission refuses to start while another publisher is present on `/rackonaut/drone/cmd_vel`, and releases its publisher if another appears in the ROS graph. Abort commands zero velocity and releases the publisher when the mission owns that topic. On the reference model, zero commands hover in flight. For manual fallback, abort the mission, wait for the command publisher to be released, then run the existing teleop node in an activated shell:

```bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/rackonaut/drone/cmd_vel
```

## Route, evidence and integration

- `route:=/absolute/path.json` selects a route with a pad pose, a takeoff altitude and an ordered list of distinct storage locations. In the [default route](config/showcase.json), coordinates are metres in `rackonaut_odom`, aligned with the fixed warehouse in this simulation, and yaw is degrees. The approach follows the known clear corridor and assumes the configured rack positions and facing. The poses come from simulator-derived odometry.
- At 10 Hz a proportional regulator transforms horizontal errors into the drone body frame. It caps horizontal, vertical and yaw commands separately, checks pose and speed before scanning, and aborts if motion times out or odometry stops advancing. After returning to the pad it verifies touchdown by pose and speed. Use `land:=false` to finish at hover height.
- At each settled viewpoint the node calls the existing perception rearm service. It accepts a fresh UTC-stamped event for the active inspection and current slot from `GET /api/observations`. It ignores events captured before the scan began and does not filter by expected pallet. Perception can also submit valid frames while moving. Those events remain in the backend history, and the mission reports the exact events that advanced each stop. After eight seconds without confirmation it records a miss and continues.
- To use Michał's drone, use his simulator launch and the existing perception node, then start `ros2 run rackonaut_mission run_mission` with `use_sim_time:=true`, the same `inspection_id` and `backend_url`, and the appropriate `route_file`. Align odometry with the configured route. The mission expects `rackonaut_base_link` as the child frame and the existing body-frame velocity and camera conventions. Confirm controller speed limits, stop behavior, hover height and touchdown before enabling the full route. See the [ROS contract](../../../contracts/ros.md).
- Vahid's backend should publish accepted observations through the existing GET route with their original UTC times and IDs. Start the stack with `mock:=false` or point separately launched nodes at his base URL. The mission confirms persistence, and the backend evaluates discrepancies. See the [HTTP contract](../../../contracts/http.md).

The waypoint sequence uses the existing Fortress velocity controller, ROS launch, `nav_msgs/Path`, RViz and `image_view`. Nav2 Waypoint Follower uses a Nav2 navigation action and was outside this demo's scope. The small mission node supplies the missing flight sequence and confirmation logic. [Fortress controller](https://gazebosim.org/api/gazebo/6/classignition_1_1gazebo_1_1systems_1_1MulticopterVelocityControl.html) · [Nav2 Waypoint Follower](https://docs.nav2.org/configuration_and_development/configuration_guide/core_servers/waypoint_follower/)

This route assumes an unobstructed simulated aisle and a compatible position estimate. It has no obstacle detection, indoor localization stack or real-drone flight approval. The reference model holds zero velocity on abort and does not disarm on touchdown. [Verification and captures](docs/VERIFICATION.md)
