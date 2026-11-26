# Rackonaut showcase warehouse

`worlds/showcase.sdf` is the presentation scene. It uses the tevy hall, three aisles, four static rack rows, a shipping area and a marked takeoff pad. `worlds/pilot.sdf` has one aisle and retains the same inspection fixture. Both use the Fortress 6 / SDFormat 1.8 contract and the world name `rackonaut`.

See [verification and simulator captures](docs/VERIFICATION.md) for the demo run and native ROS image samples.

## Run in Fortress

Run these commands from the repository root on Ubuntu 22.04 or WSL2.

```bash
scripts/robotics/build
scripts/robotics/reference --gui --world ros2_ws/src/rackonaut_warehouse/worlds/showcase.sdf
```

Omit `--gui` for the headless camera run. The launcher uses software rendering by default. It spawns the reference drone separately at `(0, 0, 0.12)` m, yaw `0`, adds the bridge and starts the optical transform. The world itself contains no drone. Use Ctrl+C in the launcher terminal to stop its processes.

In a second terminal, activate the project and start one command publisher.

```bash
source scripts/robotics/activate.bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/rackonaut/drone/cmd_vel
```

Use the keyboard driver's printed controls. Take off before moving along the aisle. The live camera and calibration are `/rackonaut/camera/image_raw` and `/rackonaut/camera/camera_info`. The native camera size is `320 × 240`. Use the actual simulator stream for vision work.

## Layout and drone handoff

The approximately `40 × 25 m` hall is centred at `X=13 m`. The floor is at `Z=0` and the entrance faces `+X`. The three aisles are `4.8 m` wide between rack faces. Aisle A runs along `Y=0`. Its inspection face is the north row (`+Y`), with fronts at about `Y=2.4 m`. The four inspection bay centres are `X=5.5`, `8.3`, `11.1` and `13.9 m`.

For the first lower slot, start with the drone facing `+Y` around `(5.46, 0.45, 0.79)` m and adjust the framing in the actual camera. In this pose the reference optical centre is about `1.7 m` from the labels. The marker centres are visibly separated in the same field of view. Keep this target composition when substituting Michał's model, then check its field of view and actual camera offset. Match the [ROS contract](../../../contracts/ros.md) and use a single teleop publisher.

## Inventory and marker handoff

Only the eight slots at the first four bays of the north row belong to the inspection fixture. The physical coordinates use four bays with two inspected levels each. The wire IDs intentionally preserve `A-01-01` through `A-01-08` so the existing API and fixtures stay compatible. Future IDs that encode actual bay and level should be agreed and migrated together with the backend.

Location IDs use ArUco `DICT_4X4_50` values `0–7` on permanent blue tabs. Pallet IDs use values `20–24` on orange tabs attached to loads. Resolve them using the [warehouse ground truth](ground_truth/showcase.json). The ground truth describes the authored scene and provides validation reference data. It has no observation timestamps and must stay outside the camera-to-API detection path. Only the inventory slots should emit observations.

| Fixture slot | Expected | Staged | Use |
|---|---|---|---|
| `A-01-01` | `P001` | `P001`, marker 20 | Match |
| `A-01-02` | `P002` | `P003`, marker 21 | Wrong pallet |
| `A-01-03` | `P003` | Empty | Missing pallet |
| `A-01-04` | Empty | `P999`, marker 22 | Unexpected pallet |
| `A-01-05` | `P005` | `P005` with an unreadable plate | Occupied, label unreadable |
| `A-01-06` | `P006` | `P006`, marker 23 | Leave uninspected by withholding observations |
| `A-01-07` | `P007` | `P007` with a partly occluded, unreadable area | Candidate view for an uncertain observation |
| `A-01-08` | `P008` | `P008`, marker 24 | Physical final state for the repeat fixture |

The repeat fixture's earlier `P998` is a historical synthetic event, not a second load in the scene. The status of an uncertain observation depends on image evidence. See the [HTTP contract](../../../contracts/http.md).

## Regeneration

The SDF, placards, Collada file and ground truth are versioned inputs. A clean checkout can start them directly. Use the generator only to change the layout.

```bash
source scripts/robotics/activate.bash
warehouse=ros2_ws/src/rackonaut_warehouse
/usr/bin/python3 "$warehouse/scripts/generate.py" --labels --truth "$warehouse/ground_truth/showcase.json"
/usr/bin/python3 "$warehouse/scripts/generate.py" --profile pilot --output "$warehouse/worlds/pilot.sdf"
```

`--help` shows the aisle, bay, level, height, width, spacing, fill and seed controls. Change the authored scene in the generator, then regenerate the SDF. `--hall procedural` switches to the native SDF fallback. Decorative loads use a fixed seed, simple box visuals, and rack row collisions. The main face uses local post, deck and cargo collisions. The original CC0 source and conversion are recorded in [asset provenance](docs/ASSETS.md).
