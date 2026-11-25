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
