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

## Opt-in obstacle avoidance showcase

The `avoidance:=true` reference profile publishes an organized `sensor_msgs/msg/PointCloud2` on `/rackonaut/drone/lidar/points`. The cloud carries simulator acquisition time, a 192 × 37 layout and Cartesian coordinates in meters with a nominal cadence of 6 Hz in simulation time. The fixed TF from `rackonaut_base_link` to `rackonaut_reference_drone/base_link/local_lidar` translates 0.09 m along +Z with identity rotation. The companion RGB camera and existing motion bridge retain their interfaces. Mission status carries the optional `avoidance` diagnostics. [Profile and validation](../docs/OBSTACLE_AVOIDANCE.md)

## Opt-in sensor localization showcase

The `localization:=sensor_based` profile makes `rackonaut_localization` the owner of `/rackonaut/drone/odom` and of the dynamic TF from `rackonaut_odom` to `rackonaut_base_link`. The `shadow` profile exposes estimates while retaining the Gazebo source for control.

| Topic | Type | Meaning |
|---|---|---|
| `/rackonaut/drone/imu` | `sensor_msgs/msg/Imu` | Body angular rates and specific force, 50 Hz nominal, frame `rackonaut_reference_drone/base_link/local_imu` at the body origin |
| `/rackonaut/localization/estimate` | `nav_msgs/msg/Odometry` | Registered pose at the exact acquisition stamp of the corresponding LiDAR cloud |
| `/rackonaut/localization/measured_map` | `sensor_msgs/msg/PointCloud2` | Accumulated observed endpoints in `rackonaut_odom` |
| `/rackonaut/localization/state` | `std_msgs/msg/String` | Localization status, quality metrics and reduced display layers |
| `/rackonaut/dock/contacts` | `ros_gz_interfaces/msg/Contacts` | Physical collision contact with the dock switch |
| `/rackonaut/validation/ground_truth` | `nav_msgs/msg/Odometry` | Optional independent validator input, enabled by `localization_diagnostics:=true` |

The estimator uses the IMU rates and specific force. In sensor mode the avoidance module uses the registered pose at the cloud stamp. The Energy Manager uses the active estimated odometry and independently checks the dock contact. [Profile and validation](../docs/SENSOR_LOCALIZATION.md)

## Opt-in autonomous recovery

`recovery:=true` requires `localization:=sensor_based`, the protected aerial scene and Safety. The loopback Control Center publishes evaluate, authorize and abort requests as `std_msgs/msg/String` on `/rackonaut/recovery/operator`. The request targets the interrupted inspection. Approval must also match the current recovery ID and proposal token. The Mission Manager rechecks prerequisites and retains ownership of the motion topic.

The `recovery` field of `/rackonaut/mission/status` carries the recovery procedure ID, parent inspection, proposed path, result and permit request. `/rackonaut/safety/state` reports the separately verified recovery permit for that ID. The original mission stage and result remain terminal throughout the procedure. Safety releases the reservation after the permitted recovery completes with stable position and physical dock contact. `/rackonaut/energy/state` reports whether the budget has been accounted for and the energy charged for odometry gaps in this profile. [Recovery profile](../docs/AUTONOMOUS_RECOVERY.md)

In this profile, Mission Manager owns the `std_msgs/msg/Bool` command on `/rackonaut/drone/flight_enabled`. A profile-local bridge forwards it to the existing simulated flight controller. At touchdown Recovery disables thrust, then checks physical dock contact before completion.

## Warehouse calibration initialization

In Full Robotics, Control Center sends a volatile, reliable `std_msgs/msg/String` on `/rackonaut/calibration/request` with `inspection_id` and `calibration_id`. Mission Manager accepts only the request for its current inspection and latches the ID. Control Center retries until the same ID appears in `/rackonaut/mission/status`. Delivery and motion supervision continue independently of the browser session.

The status includes `motion_owned` and, after accepting a calibration request, `calibration_id` and `termination_reason: CALIBRATION_REQUESTED`. A successful interruption ends at `INTERRUPTED_FOR_CALIBRATION` with `landed: true`, the publisher released, and measurements retained. Safety independently verifies physical dock contact and position before releasing the reservation. Energy allows charging at the dock while the inspection stays terminal. Faults and manual Abort retain the existing `ABORTED` result and operator-approved Recovery. The public Start and Abort service types stay the same. [Service Center](../ros2_ws/src/rackonaut_control/README.md#service-center)

## Protected manual flight

In Full Robotics, Control Center publishes `std_msgs/msg/String` on `/rackonaut/manual/request` with reliable, volatile, keep-last depth 1. The payload includes `inspection_id`, an increasing integer `sequence`, `sent` in host monotonic seconds, and `action` (`movement` or `return`). Movement includes four normalized `axes` in body forward, left, up and positive yaw order plus a normalized `speed` of 0.20–1.00. Control Center and Mission Manager run on the same host and check freshness independently. Mission Manager discards expired, repeated and unrelated requests. Its 0.55 s operator watchdog commands zero and retains the flight reservation when input expires airborne.

Mission Manager is the sole `/rackonaut/drone/cmd_vel` publisher in this profile. Its optional `manual` status includes `state`, `detail`, `requested`, `permitted` (body m/s and yaw rad/s), and `clearance` (m or null). Movement progresses through `MANUAL_FLIGHT`. A verified physical dock return finishes at `COMPLETE` with `manual.state` equal to `DOCKED`. Faults use the existing `ABORTED` and Recovery workflow. [Protected manual flight](../docs/PROTECTED_MANUAL_FLIGHT.md)

## Warehouse mapping session

Control Center sends `begin`, `arm`, `finish` and `close` with `mapping_id` on the reliable, volatile `std_msgs/msg/String` topic `/rackonaut/localization/mapping_command`. Localization reports `source`, `mapping_id`, `mapping_phase` and its beginning timestamp on the existing `/rackonaut/localization/state`. The ID binds the manual Mission Manager to its active SLAM session. The localizer verifies physical dock contact and absence of a motion publisher for session changes at the dock.

The map of a mapping session is a packed XYZ `sensor_msgs/msg/PointCloud2` on `/rackonaut/localization/slam_map`, sensor QoS, in the same dock-anchored `rackonaut_odom` frame as the existing estimator. The frame and types of the estimate, live odometry and TF stay the same. The protected flight envelope remains a separate Mission and Safety configuration. [Warehouse mapping](../docs/UNKNOWN_WAREHOUSE_MAPPING.md)
