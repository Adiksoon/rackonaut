# Technical decisions

| Decision | Status and reason |
|---|---|
| Ubuntu 22.04, ROS 2 Humble, system Python 3.10, Gazebo Fortress | **Provisional robotics baseline.** The integration host already has this combination and Fortress is the standard pairing for Humble. Michał should verify the reference run on the environment he will use. Warehouse and drone must use the same simulator generation. If a generation change is needed, agree it together and repeat world, motion, camera, and bridge checks. |
| Headless reference rendering | **Integration host default.** The Fortress reference launcher uses Mesa llvmpipe in software for the camera check. Use GUI and display rendering only for an additional diagnostic where the host supports them. |
| Separate ROS workspace and backend virtual environment | **Baseline.** The ROS profile uses system Python and the system cv_bridge/OpenCV/NumPy packages together. The backend has its own dependencies and can work on native Windows. |
| Fixture HTTP API and one shared OpenAPI file | **Baseline.** Lets backend, dashboard, and vision use the same request and response shapes independently. The mock has fixture results, and the backend implementation owns comparison behavior. |
| One integration host, local ROS traffic | **Baseline.** Keeps ROS discovery local and lets developers exchange code, bags when needed, and JSON through the agreed workflow. Container and broker infrastructure can wait for a concrete need. |
| Small reference assets with recorded provenance | **Baseline.** Use assets whose distribution and required dependencies are understood. Register their source, version, and license where they are introduced. |
| Teleoperation and camera before mapping | **Baseline.** Establish motion, image, time, and transport as independent checks before evaluating mapping. |

[Gazebo compatibility reference](https://gazebosim.org/docs/fortress/ros_installation/) · [Recorded baseline tests](TEST_RESULTS.md)
