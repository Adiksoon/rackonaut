# Baseline test results

The tests distinguish environment checks, synthetic fixtures, reference simulator output, and integration of the team's future modules. Use the exact commands in the role guides to repeat the relevant profile.

## Test host

The integration host uses Windows 11 Education with WSL2 Ubuntu 22.04.5. Robotics uses ROS 2 Humble, Gazebo Fortress 6.16.0, system CPython 3.10.12, OpenCV 4.5.4, NumPy 1.21.5, and `cv_bridge` 3.2.1. Native Windows backend checks use CPython 3.13.15. Backend dependencies are pinned in [`requirements.txt`](../backend/requirements.txt).
