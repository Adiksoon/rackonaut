# Michał · drone and camera

Select a compatible drone, attach a camera, and provide teleoperation and ROS 2 sensor output. Use the reference world to test the model independently of the warehouse branch.

## Set up in Ubuntu 22.04 or WSL2

Use Git, Bash, ROS 2 Humble, Gazebo Fortress, colcon, rosdep, and system Python 3.10. Clone on the Linux filesystem. If system dependencies are missing, use the official installation instructions and report the exact packages required. System package installation requires administrator privileges. Tell Adrian if your candidate needs a different simulator generation before committing to it. [ROS 2 Humble installation](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html) · [Fortress and ROS 2](https://gazebosim.org/docs/fortress/ros_installation/)

For a fresh clone, run the Git commands below. If you already have a clone, start at its root and create the role branch from `main`.

```bash
cd ~
git clone https://github.com/Adiksoon/rackonaut.git
cd rackonaut
git switch -c feature/drone
source scripts/robotics/activate.bash
```

If the robotics dependencies are already installed, continue to the check below. To resolve missing packages, refresh the project-local rosdep cache and review the install plan in the activated shell.

```bash
rosdep update --rosdistro humble
scripts/robotics/dependencies
```

If the plan shows missing ROS dependencies, install them explicitly with `rosdep install --from-paths ros2_ws/src --ignore-src --rosdistro humble`. System installs may prompt for administrator privileges. Initial system setup can require `sudo rosdep init` if `/etc/ros/rosdep/sources.list.d/` has no configured sources. See the Humble installation guide for that case.

```bash
scripts/robotics/check
scripts/robotics/build
scripts/robotics/world
```

The world starts headless by default. Stop it in its own terminal with Ctrl+C. Run `scripts/robotics/smoke --reference` to check the reference simulator path. Use the default headless reference on the integration host. After stopping the standalone world, `scripts/robotics/reference --gui` is an optional diagnostic on hosts with compatible graphics. The synthetic publisher `scripts/robotics/mock` is available for checking camera consumers separately. Stop it before running the simulator camera.

## Your first change

- Put drone-specific files and its spawn or teleop launcher in `ros2_ws/src/rackonaut_drone/`. Record the model source, version, license, dependencies, and tested generation.
- Work from the [simulation and ROS contract](../../contracts/ros.md). List the model's observed endpoints and any remappings needed for canonical topics. Supply a launch path for a compatible world and the agreed spawn pose.
- Check a short teleop command and the resulting motion and stop or hover. Confirm actual camera frames, compatible QoS and matching calibration, plus valid frames and sim-time stamps. Test optional depth and odometry if provided.
- Send your OS, versions and smoke result to Adrian to confirm the provisional Fortress baseline. Commit your paths and open a PR with the launch and results. Follow the [Git workflow](../TEAM_TASKS.md#git-workflow) and use the [drone agent prompt](AI_PROMPT_DRONE.md) if helpful.

## Confirm readiness

- [ ] Repository cloned.
- [ ] Correct branch created.
- [ ] Dependencies installed.
- [ ] Mock or reference component started.
- [ ] Smoke test passed.
- [ ] Ready for development.
