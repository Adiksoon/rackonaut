# Showcase acceptance and captures

Run on 25 November 2026 on the WSL2 integration host with Ubuntu 22.04, ROS 2 Humble and Gazebo Fortress 6.16.0. The runtime files were verified at `4b7a0395e7af66249789b5efdd8febf412925c80`. Both GUI rendering and the separate headless probe used llvmpipe.

| Check | Result | Evidence |
|---|---|---|
| World and assets | **PASS** | `ign sdf -k` validated the pilot, showcase and procedural fallback SDF. The tevy shell, dimensions, floor and textures on placards were visible in the showroom. The fallback was syntax-checked only. |
| GUI | **PASS** | Gazebo displayed the tevy interior and all three aisles. The `/gui/move_to/pose` service moved the viewport among the saved viewpoints and `/gui/screenshot` generated the original PNGs. GUI frame rate was not instrumented. |
| Independent spawn and flight | **PASS** | `scripts/robotics/reference --gui --world …/showcase.sdf` spawned the unchanged reference drone. ROS commands on `/rackonaut/drone/cmd_vel` took it from `(0, 0, 0.050)` to `(4.192, 0.006, 1.456)` m in one takeoff and forward pass. The forward command was `0.9 m/s`, followed by zero. |
| Live RGB and calibration | **PASS** | `image_view image_saver` stored 96 frames from `/rackonaut/camera/image_raw` in the GUI run. The standard headless reference probe paired a real `320×240 rgb8` frame and matching `CameraInfo` on `rackonaut_camera_optical_frame`. |
| Marker proof | **PASS** | OpenCV 4.5.4 decoded location tag `0` and pallet tag `20` in one native frame. Both were printed in the scene and observed approximately `1.7 m` from the optical centre, with measured marker edges about `41` and `36` pixels. Two other native frames independently decoded only the location tag at the empty and unreadable-label slots. These are marker reads. Occupancy and full observation generation are future perception work. |
| Inventory fixture | **PASS** | Generated ground truth matches the eight expected backend slot IDs and expected pallet values. The actual staged stock encodes the five priority physical cases. The uninspected, uncertain and repeated-observation semantics are documented in the [handoff](../README.md#inventory-and-marker-handoff). |
| Pilot versus showcase | **PASS for demo** | Pilot headless sample `0.9876` real-time factor and approximately `10 Hz` RGB. Full GUI flight received `9.87 Hz` over 96 frames. Eight full GUI world-stat samples ranged `0.945–1.010` with median `0.977`. The viewport remained responsive for separate view changes. The sample compares different modes and does not isolate GUI cost. |
| Clean checkout and assets | **PASS** | An independent no-local clone of the runtime commit built both ROS packages, resolved the package shell and plate texture, and passed `SIM-01`, `SIM-02`, `SIM-03`, `CAM-01` and `CV-01` with the existing probe. Runtime assets were resolved from the checkout. The owned simulator, bridge and TF processes were stopped. |

## Original captures

| File | Source |
|---|---|
| [01 · Warehouse overview](evidence/01_overview.png) | Gazebo viewport. All three aisles with the marked drone pad. |
| [02 · Main aisle](evidence/02_main_aisle.png) | Gazebo viewport. The warehouse's long inspection corridor. |
| [03 · Racks and loads](evidence/03_racks_and_loads.png) | Gazebo viewport. The inspection-facing racks, pallets and markings. |
| [04 · Reference drone](evidence/04_reference_drone.png) | Gazebo viewport. The live reference drone next to the staged inventory. |
| [05 · Drone RGB](evidence/05_drone_rgb.png) | Original ROS camera frame during the commanded forward pass. |
| [06 · Location and pallet placards](evidence/06_placards.png) | Gazebo viewport close-up at the first inspection bay. |
| [07 · Native marker proof](evidence/07_drone_aruco.png) | ROS camera frame. Location `A-01-01` and pallet `P001`, decoded IDs `0` and `20`. |
| [08 · Native empty-slot frame](evidence/08_drone_empty_slot.png) | ROS camera frame. Visible location `A-01-03`, decoded ID `2`, with an empty deck. |
| [09 · Native unreadable-label frame](evidence/09_drone_unreadable_pallet.png) | ROS camera frame. Visible location `A-01-05`, decoded ID `4`, with a load and deliberately unreadable pallet plate. |
| [10 · Onboard flight clip](evidence/10_reference_flight.mp4) | 96 original ROS RGB frames encoded at `10 fps`. Runs 9.6 seconds and shows the first part of the aisle. |

The three native detection frames were captured at staged camera poses after the flight test, for repeatable framing. They can be used to repeat the marker probe without runtime simulation.

```bash
source scripts/robotics/activate.bash
/usr/bin/python3 - <<'PY'
from pathlib import Path
import cv2

evidence = Path('ros2_ws/src/rackonaut_warehouse/docs/evidence')
dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
for path in sorted(evidence.glob('0[789]_drone_*.png')):
    image = cv2.imread(str(path))
    _, markers, _ = cv2.aruco.detectMarkers(image, dictionary)
    print(path.name, sorted(markers.ravel().tolist()) if markers is not None else [])
PY
```

Assessed scope is the reference drone, one live camera and one host. The production drone, integrated vision and backend, hardware rendering and a full-length manual traversal are outside these test results.
