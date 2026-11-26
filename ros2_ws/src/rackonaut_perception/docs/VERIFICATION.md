# Perception verification

Checked on 25 November 2026 with Ubuntu 22.04 under WSL2, ROS 2 Humble, Gazebo Fortress 6.16.0, OpenCV 4.5.4 and software rendering. The main acceptance runs used the showcase world from warehouse commit `d9b1d3d` and the reference drone's `320×240` RGB camera.

## Archived frames

```bash
scripts/robotics/build
source scripts/robotics/activate.bash
/usr/bin/python3 -m unittest discover -s ros2_ws/src/rackonaut_perception/test -v
```

Five tests passed. They cover the original warehouse camera frames for readable, empty and unreadable cases, two locations in a composite frame, the consecutive-frame gate with rearm and uncertainty, and identical request bytes and observation ID on HTTP retry. The installed `inspect_frame` entry point also decoded A-01-01 and P001 from the archived camera frame.

## Live camera at prepared poses

The reference drone was placed at shelf-facing viewpoints and the node processed the live ROS image and camera information. The repository mock API accepted the observations with HTTP 201.

| Scenario | Measured result | Evidence |
| --- | --- | --- |
| A-01-01 | `occupied / readable`, P001 | [Live capture](evidence/01_readable_live.png) |
| A-01-02 | `occupied / readable`, P003 | [API observations](evidence/observations_live.json) |
| A-01-03 | `empty / not_applicable`, with rear boxes visible | [Live capture](evidence/02_empty_live.png) |
| A-01-04 | `occupied / readable`, P999 | [API observations](evidence/observations_live.json) |
| A-01-05 | `occupied / unreadable`, with no pallet ID | [Live capture](evidence/03_unreadable_live.png) |
| A-01-06 | Left uninspected and absent from the run's observations | [API observations](evidence/observations_live.json) |
| A-01-07 | `uncertain / unknown` from a framed view with an unclear shelf edge, accepted by the API | [Live capture](evidence/06_uncertain_view.png) |
| A-01-08 | P008 recorded once while held in view. Rearming recorded it again with a new observation ID | [API observations](evidence/observations_live.json) |

At A-01-07, a closer view showed enough of the pallet base for `occupied / unreadable`. In the acceptance run the inspection was rearmed at A-01-08, then revisited A-01-01 for an overview capture before moving to A-01-07. This accounts for the two readings of A-01-01. [The full overlay](evidence/04_live_system.png) shows the 1200×684 view published by the node and displayed with ROS `image_view`.

In a temporary copy of the world, the pallets and labels at A-01-01 and A-01-02 were exchanged. The same node and marker dictionary sent A-01-01/P003 and A-01-02/P001 from two prepared viewpoints. [API observations](evidence/observations_swap.json) · [Live capture](evidence/07_swapped_pallets.png)

## Live motion and performance

A short lateral pass started from a prepared pose and used `/rackonaut/drone/cmd_vel`. Reference-drone odometry advanced from x=4.360 m to x=6.603 m. The camera captured the accepted A-01-01/P001 observation at 08:14:55.084 UTC, inside the commanded movement interval of 08:14:52.574–08:14:59.185 UTC. The pass produced 97 annotated frames at about 9.91 Hz. The [9.7-second video](evidence/05_live_inspection_flight.mp4) was encoded from the live overlay, and the [motion observation](evidence/observations_motion.json) was retrieved from the mock API.

Seven short headless Gazebo samples gave a median real-time factor of 0.9898 before perception and 0.9907 with perception running. These runs show similar simulation speeds on this workstation. They are short demo checks rather than a performance benchmark.

All twelve stored observations were validated against the OpenAPI `Observation` schema. When a second live node targeted an unused local port, its API state reached `ERROR` and the annotated topic continued publishing. The mock accepts new observations as `pending`. Michał's drone and Vahid's backend still require an integration run.

## Package quality

The 25 November 2026 tests used ROS 2 Humble, Fortress 6.16.0 and OpenCV 4.5.4 with the same native `320×240` RGB stream. The generated quality world passed `ign sdf -k`. Generating the original world without `--quality` produced a byte-identical copy of the tracked `showcase.sdf`.

| Test | Live result | Evidence |
| --- | --- | --- |
| Intact kraft carton | A-01-01 / P001, `OK` | [Overlay](evidence/quality/01-intact/annotated.png) · [Report](evidence/quality/01-intact/report.json) |
| Visible tear | A-01-02 / P003, `DAMAGED` | [Original RGB](evidence/quality/02-torn/camera.png) · [Overlay](evidence/quality/02-torn/annotated.png) · [Report](evidence/quality/02-torn/report.json) |
| Crushed corner | A-01-04 / P999, `DAMAGED` | [Original RGB](evidence/quality/03-crushed/camera.png) · [Overlay](evidence/quality/03-crushed/annotated.png) · [Report](evidence/quality/03-crushed/report.json) |
| Cropped carton | A-01-01 / P001, `UNCERTAIN` in the live preview | [Original RGB](evidence/quality/04-uncertain-camera.png) · [Overlay](evidence/quality/04-uncertain-live.png) |
| Torn carton moved to a different slot | A-01-01 / P001, `DAMAGED` after the move. A-01-02 / P003 read `OK` with the intact carton. | [Moved carton overlay](evidence/quality/05-moved-tear/annotated.png) · [Report](evidence/quality/05-moved-tear/report.json) |
| Unreadable pallet placard | A-01-05, `OK` on the carton with `pallet_id: null) | [Overlay](evidence/quality/06-unreadable-label/annotated.png) · [Report](evidence/quality/06-unreadable-label/report.json) |

The cropped and moved-carton tests used prepared camera poses. In the second test, only the carton visuals at A-01-01 and A-01-02 were exchanged in a temporary SDF copy. Their location tags, pallet labels, skids and collision entries stayed in place. A separate local-only node saved one torn-carton bundle without a backend, even though the camera continued sending frames.

The five-stop autonomous run `INS-05A-MISSION` completed in **75.6 s**, confirmed all five original inventory cases, and landed at `(0, 0, 0.05)` m without pose resets. It saved four quality bundles, two of them damaged. All four report observation IDs matched API events with the same inspection, slot and pallet. A-01-03 remained explicitly empty and produced no carton report. All 11 API observations passed the existing v1 schema. [Mission status](evidence/quality/mission-status.json) · [API observations](evidence/quality/inventory-observations.json)

The [26-second clip](evidence/quality/07-quality-inspection.mp4) shows 263 consecutive frames from that flight with the intact carton, tear and crushed corner. The annotated stream measured about 9.89 frames/s over the excerpt.

```bash
scripts/robotics/build
source scripts/robotics/activate.bash
ros2 launch rackonaut_mission showcase.launch.py quality:=true gazebo_gui:=false view:=false
# Run in a second activated terminal from the repository root.
/usr/bin/python3 -m unittest discover -s ros2_ws/src/rackonaut_perception/test -v
```
