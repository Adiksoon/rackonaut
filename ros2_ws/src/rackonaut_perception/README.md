# Rackonaut live perception

The node reads paired RGB and camera calibration, detects ArUco placards, associates pallets with locations in image coordinates, and evaluates the near shelf edge when no pallet label can be decoded. It publishes a `1200×684` live overlay and posts stable v1 observations to a configured REST backend. It has no runtime dependency on the simulator's models, ground truth, or SAP inventory.

## Run the showcase

From the repository root, build and start the simulator in one terminal.

```bash
scripts/robotics/build
scripts/robotics/reference --world ros2_ws/src/rackonaut_warehouse/worlds/showcase.sdf
```

Use `--gui` for the Gazebo viewport. For the optional mock API, follow the [backend onboarding](../../../docs/onboarding/BACKEND.md) to prepare its separate virtualenv, then run this in another terminal.

```bash
.venv-backend/bin/python -m uvicorn backend.mock_api:app --host 127.0.0.1 --port 8000
```

Start the inspection in an activated ROS terminal. Use a fresh `inspection_id` for each run. Omit `backend_url` for local-only preview and detection. Supply the real backend's base URL when it is available.

```bash
source scripts/robotics/activate.bash
ros2 run rackonaut_perception inspect --ros-args \
  -p use_sim_time:=true -p inspection_id:=INS-DEMO-001 \
  -p backend_url:=http://127.0.0.1:8000
```

View the annotated stream and drive using separate activated terminals.

```bash
ros2 run image_view image_view --ros-args -r image:=/rackonaut/perception/annotated
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/rackonaut/drone/cmd_vel
```

Aim across aisle A toward the placards at `+Y`. Start about `1.7 m` from the shelf, facing it squarely. At the correct angle, both tags and the shelf band fit into the view. The default gate records a consistent result after four consecutive frames and suppresses identical readings for the same slot. A changed stable result gets a new ID. An explicitly rearmed scan also gets a new ID, while HTTP retries keep the original body and ID.

```bash
ros2 service call /rackonaut_perception/rearm std_srvs/srv/Trigger '{}'
```

Rearm clears the local stability gate and duplicate suppression. It leaves server history intact. Hold the intended slot in view for a new reading. Restart with a new `inspection_id` to start a new inspection. The overlay's `SENT` status means the API accepted the event. Green denotes a usable visual reading and gives no indication of a SAP match.

## Camera and backend handoff

The default input topics are `/rackonaut/camera/image_raw` and `/rackonaut/camera/camera_info`. Override them with `-p image_topic:=…` and `-p camera_info_topic:=…`. Exact stamp synchronization and matching optical frame, calibration and dimensions are required. Inputs use sensor-data QoS. The preview is reliable with a depth of one and carries the source image header. Use ROS simulation time for the simulator and UTC wall-clock capture time in the [HTTP observation](../../../contracts/http.md). On another drone, check the [ROS contract](../../../contracts/ros.md), field of view and initial framing. `320×240` was sufficient for the reference camera.

The backend receives v1 observations at `POST /api/observations`. Use `GET /api/observations?inspection_id=…` to retrieve the emitted data. The node sends valid JSON without SAP access. The fixture API returns `pending` for custom observations. A single background worker retries temporary failures. Preview and analysis continue during an API interruption. An exhausted retry is shown as `ERROR`. Rearm to record a fresh reading when the backend is reachable.

## Image method and limitations

- The [marker dictionary](config/markers.json) decodes label IDs into names, with independent name spaces for locations and pallets. It has no slot-to-pallet mapping.
- Each slot's ordered corners define a local image plane. Pallet marker centres must lie inside the neighbouring label region with plausible scale. Overlapping assignments or multiple candidates produce `uncertain`.
- Without a readable pallet marker, occupancy comes from a rectified near shelf band. Orange shelf coverage confirms a visible empty surface, while a contiguous wood-coloured skid supports `occupied / unreadable`. Boxes in the rear rows are outside the band. The checks require framing and a visible shelf reference. They are tuned to the showcase geometry, colour and near-frontal passes. An absent location marker never generates an observation.
- Uncertain images are visible in the preview. Automatic recording of uncertainty requires a longer streak with the slot sufficiently framed. After rearming, hold the intended slot in view to meet the same framing and stability checks. Terminal API failures are visible and independent of vision processing.

Run the same processor on a stored frame without listening to ROS topics or posting to a backend.

```bash
source scripts/robotics/activate.bash
ros2 run rackonaut_perception inspect_frame \
  ros2_ws/src/rackonaut_warehouse/docs/evidence/07_drone_aruco.png \
  --annotated /tmp/rackonaut-inspection.png
```

See [acceptance and original captures](docs/VERIFICATION.md).

## Package quality demo

From the repository root, prepare the mock API environment as above, build the packages and enable the quality variant. The same launcher with its default arguments starts the original inventory demo.

```bash
scripts/robotics/build
source scripts/robotics/activate.bash
ros2 launch rackonaut_mission showcase.launch.py quality:=true rviz:=true
```

The build generates a separate `quality_showcase.sdf` with the same stock, labels, route and collision envelope. It stages an intact kraft carton, a jagged opening with a recessed cavity and a crushed corner with folded surfaces. The original `showcase.sdf` remains the default. For a different camera source, start perception with `-p quality_enabled:=true` and the usual camera parameters. Quality also works in local-only mode.

The upper face above the pallet placard is rectified from the observed location tag. OpenCV measures kraft-colour support and local brightness, then finds connected regions consistent with a dark surface break or a missing piece of the top contour. The observed slot and pallet IDs label the result. Classification uses the image pixels. `OK` means the visible face meets the intact checks. `DAMAGED` means a visible structural defect was detected. `UNCERTAIN` covers an incomplete, poorly supported or ambiguous view. Empty locations display `NO CARTON`. An unreadable pallet label leaves `pallet_id` null.

The ROI and thresholds are tuned to the showcase's kraft carton, near-frontal framing and lighting. This demo checks large tear and crush cues at 320×240. The rear, underside, subtle defects, other materials and physical warehouse conditions require separate validation. Generic object detection provides object categories. PatchCore supplies localization maps but requires a bank of representative normal images and a model runtime. These trade-offs favoured the existing Humble OpenCV stack and local segmentation for the demo. [COCO model classes](https://docs.ultralytics.com/datasets/detect/coco/) · [PatchCore workflow](https://anomalib.readthedocs.io/en/latest/markdown/guides/reference/models/image/patchcore.html)

### Evidence and integration proposal

The panel outlines the carton in green for `OK`, marks the detected region in red for `DAMAGED`, and shows `UNCERTAIN` in amber. The damage count represents distinct slot and pallet pairs with stable damaged captures. A capture requires seven consecutive agreeing frames and a matching local inventory observation. Each stable `OK` or `DAMAGED` result is stored once per slot and pallet within the running inspection. Uncertain views remain visible in the panel.

The default evidence directory is `ros2_ws/log/ros/quality` in an activated Rackonaut shell. Override it with `quality_dir:=/path/to/captures` on the launcher or `-p quality_dir:=/path/to/captures` on the node. Each bundle is stored under `<inspection_id>/<quality_id>/` and contains:

- `camera.png` with the unannotated native-resolution camera frame and `annotated.png` with the corresponding live overlay.
- `report.json` with the quality version and ID, inspection ID, linked local inventory observation ID and timestamp, slot ID, nullable pallet ID, verdict, UTC capture time, ROS frame and stamp, and the defect polygon in native image pixels when present.

For agreement with Vahid and Tharindu, the proposed integration is an independent `POST /api/quality-observations` with the sidecar fields and uploaded image references. Use `(inspection_id, quality_id)` as the idempotency key and `(inspection_id, observation_id)` for the inventory join. The dashboard could query quality by inspection ID and show the verdict and photos next to its inventory result. The currently implemented interface is the local bundle. Inventory POSTs continue to follow HTTP v1.0. See the [quality verification](docs/VERIFICATION.md#package-quality).
