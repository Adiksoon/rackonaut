# Robotics interface v0.1

This contract defines the names that warehouse, drone and perception should target. The provisional integration stack is Ubuntu 22.04 (native or WSL2), ROS 2 Humble, Python 3.10 from Ubuntu and Gazebo Fortress (tested with 6.16.0). Adrian and Michał confirm the same simulator generation on both hosts before committing to asset formats. The reference package is a simulator test fixture.

## Warehouse and drone

- Store editable worlds and models as SDFormat 1.8 for Fortress. The integration world name is `rackonaut`. Worlds do not embed the drone model. Store assets in the owning ROS package and reference portable model URIs or files resolved through the package share.
- Use SI units, radians, and a right-handed world. Use +X down the initial aisle, +Y to the left when looking along +X, and +Z upward. Put the floor at Z = 0 and keep the entrance clear. Publish the location-marker IDs in the warehouse source. The first fixture slot marker is `A-01-01`.
- Use reference spawn position (0, 0, 0.12) m and roll/pitch/yaw (0, 0, 0) rad. The shared integration spawn point is (0, 0, 0) XY/yaw and +X heading. Adjust Z for the actual model's landing gear and origin, and record the final Z here. The reference launch starts the simulator unpaused and spawns the drone as a separate model.
- Keep gravity at `0 0 -9.81` m/s². Include Fortress Physics, UserCommands (for `/world/rackonaut/create`), SceneBroadcaster, and Sensors with a tested rendering engine. Provide floor collision geometry. The reference world uses a 4 ms physics step and starts with an unobstructed line of sight to a primitive rack.
- With a compatible world and the reference model use `scripts/robotics/reference --world <path>`. The production drone package should accept a world name, model path and spawn pose as launch arguments, and should own model-specific controller and bridge settings.

## ROS 2 interface

The project environment defaults to domain **62**, localhost-only discovery and `rmw_fastrtps_cpp`. The simulation publishes `/clock`; simulator time is a local epoch and must be kept separate from UTC observation timestamps used by the HTTP API. Set `use_sim_time:=true` on simulation consumers and keep the timestamp from the acquired frame throughout the perception stage. The image mock works alone and uses the node's wall clock by default. It can use simulator time if a separate clock publisher is present.

Sensor QoS means keep-last depth 5, best-effort and volatile. Receivers should request this profile so they accept best-effort and reliable publishers. A bridge may offer reliable delivery. Listed frequencies are targets for the reference profile, measured in simulation time when running live.

| Topic | Type | Publisher → subscriber | QoS | Frame, time and units | Scope |
|---|---|---|---|---|---|
| `/rackonaut/camera/image_raw` | `sensor_msgs/msg/Image` | drone camera bridge or image mock → perception | Sensor | `rackonaut_camera_optical_frame`; acquisition time; pixel `rgb8` (consumer may also convert `bgr8`) | Required, aim for 10 Hz |
| `/rackonaut/camera/camera_info` | `sensor_msgs/msg/CameraInfo` | same camera source → perception | Sensor | Same optical frame, dimensions and stamp as image; intrinsics in pixels | Required, once per RGB image |
| `/rackonaut/camera/depth/image_raw` | `sensor_msgs/msg/Image` | depth bridge → perception | Sensor | RGB optical frame when registered; aligned stamp; `32FC1` in meters or documented `16UC1` in mm | Optional; match RGB cadence if provided |
| `/rackonaut/drone/odom` | `nav_msgs/msg/Odometry` | model adapter → integration and optional mapping | Sensor-compatible subscriber | pose in `rackonaut_odom`, child `rackonaut_base_link`; sim time, m/rad and m/s/rad/s, quaternion (x,y,z,w) | Required for reference motion check, target 25 Hz |
| `/tf` | `tf2_msgs/msg/TFMessage` | drone pose adapter → TF consumers | TF defaults, volatile | `rackonaut_odom` → `rackonaut_base_link`; same simulated time and transform convention as odometry | Required for pose-dependent features, at odometry cadence |
| `/tf_static` | `tf2_msgs/msg/TFMessage` | drone description → TF consumers | TF static defaults, reliable, transient local | `rackonaut_base_link` → `rackonaut_camera_optical_frame`; fixed extrinsics | Required for pose-dependent CV or mapping |
| `/clock` | `rosgraph_msgs/msg/Clock` | simulation bridge → sim-time nodes | ROS time, best-effort compatible, volatile | simulated seconds/nanoseconds; exactly one source per domain | Required in live simulation |
| `/rackonaut/drone/cmd_vel` | `geometry_msgs/msg/Twist` | single teleop operator → drone controller adapter | Reliable, keep-last 10, volatile | Body frame +X forward, +Y left, +Z up, positive yaw about +Z; linear m/s, angular.z rad/s; forward at 5–10 Hz, send zero on stop | Required; angular.x/y unused |

The optical frame is +X right, +Y down and +Z forward. The drone frame is +X forward, +Y left and +Z up. A final adapter should ensure that each TF edge has a single owner and stale commands return to zero. The reference smoke sends a zero command before it stops. This fixture is for simulation only.

## Reference adapters

The checked-in bridge configuration links Fortress's `/world/rackonaut/clock` to ROS `/clock`. Native fixture channels are `/rackonaut_reference/cmd_vel` (controller input), `/rackonaut_reference/odom` (3D simulation odometry), `/rackonaut_reference/tf` (simulation-derived pose), `/rackonaut_reference/rgb` and `/rackonaut_reference/camera_info`. Production modules use the ROS interface names in the table. The reference fixture uses original primitive geometry and has an RGB camera only. Its simulated odometry is suitable for validation and must be identified as simulator-derived in results.

Before substituting a drone, Michał confirms the model version and license, native transport names, command frame and zeroing behavior, camera encoding and header agreement, pose/TF source, and compatibility with the same warehouse world. Depth, LiDAR, map frames and SLAM require a separate agreement.
