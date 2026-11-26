# Adrian · warehouse and computer vision

Build a warehouse world that can accept an independently spawned drone. Then build vision against the camera and observation contracts. Use the existing reference world and synthetic images to check your setup first.

## Set up in Ubuntu 22.04 or WSL2

Use Git, Bash, ROS 2 Humble, Gazebo Fortress, colcon, rosdep, and the system Python 3.10 packages for cv_bridge, OpenCV, and NumPy. The repository should live on the Linux filesystem. If system packages are missing, use the linked installation instructions and coordinate any simulator generation change before installing it. System package installation requires administrator privileges. [ROS 2 Humble installation](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html) · [Fortress and ROS 2](https://gazebosim.org/docs/fortress/ros_installation/)

For a fresh clone, run the Git commands below. If you already have a clone, start at its root and create the role branch from `main`.

```bash
cd ~
git clone https://github.com/Adiksoon/rackonaut.git
cd rackonaut
git switch -c feature/warehouse
source scripts/robotics/activate.bash
```

If the robotics dependencies are already installed, continue to the check below. To resolve missing packages, refresh the project-local rosdep cache and review the install plan in the activated shell. The workspace declares `ament_python` as a build tool in its Python package manifests. Colcon handles that build type. Skip the unresolved rosdep key when generating the plan.

```bash
rosdep update --rosdistro humble
rosdep install --simulate --from-paths ros2_ws/src --ignore-src --rosdistro humble --skip-keys=ament_python
```

If the plan shows missing ROS dependencies, install them explicitly with `rosdep install --from-paths ros2_ws/src --ignore-src --rosdistro humble --skip-keys=ament_python`. System installs may prompt for administrator privileges. Initial system setup can require `sudo rosdep init` if `/etc/ros/rosdep/sources.list.d/` has no configured sources. See the Humble installation guide for that case.

```bash
scripts/robotics/check
scripts/robotics/build
scripts/robotics/world
```

The world starts headless. Add `--gui` for a visual check on a machine with a display. Stop it with Ctrl+C in its own terminal. Run `scripts/robotics/smoke --mock` to check both the synthetic publisher and a real ROS subscriber. For independent vision work, start `scripts/robotics/mock`. The reference [fixtures](../../ros2_ws/src/rackonaut_reference/fixtures/) contain the rack, slot label, and pallet label images. Stop the mock before switching to the simulator camera.

## Your first change

- Put the warehouse in `ros2_ws/src/rackonaut_warehouse/`. Keep it compatible with a separately spawned model and record asset sources and licenses.
- Use `feature/perception` for vision and put its code in `ros2_ws/src/rackonaut_perception/`. Begin with the synthetic camera input and JSON fixtures. Keep the backend environment separate from the ROS Python environment.
- Follow the [world and camera contract](../../contracts/ros.md) and [HTTP contract](../../contracts/http.md). Plan an observable association between a rack location identifier and the camera observation.
- Run your own world with the robotics environment. Capture the world name and simulator version, verify the spawn pose and rack collisions, and document its launch command. For vision, test the camera and confirm that an observation validates against the contract. Record whether inputs were fixtures or simulator frames.
- Commit your paths and open a PR to `main` with the command and result. Follow the [Git workflow](../TEAM_TASKS.md#git-workflow). If using an AI agent, start with the [warehouse prompt](AI_PROMPT_WAREHOUSE.md).

## Confirm readiness

Check off each item and send your commit, operating system, and smoke result to the team.

- [ ] Repository cloned.
- [ ] Correct branch created.
- [ ] Dependencies installed.
- [ ] Mock or reference component started.
- [ ] Smoke test passed.
- [ ] Ready for development.

## Warehouse backend

From GOAL 17, Adrian owns Mock SAP inventory comparison and warehouse recommendations. The [integration guide](../SAP_BUSINESS_INTELLIGENCE.md) describes the functional profile and the fixture fallback.
