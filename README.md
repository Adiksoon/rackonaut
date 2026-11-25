# Rackonaut

Rackonaut is a RobotHack 2026 prototype for inspecting warehouse storage locations. A teleoperated drone in Gazebo supplies camera data to ROS 2. Computer vision will turn that data into observations. A backend will compare them with simulated SAP inventory, and a dashboard will present the results.

This baseline gives the team a shared ROS workspace, reference simulation, synthetic camera data, a fixture-backed REST API, and contracts. See [test results](docs/TEST_RESULTS.md) for the scope of the available evidence.

## Start here

The [Warehouse Control Center](ros2_ws/src/rackonaut_control/README.md) lets an operator select an inspection in the browser, follow the reference drone and open the resulting HTML report.

The [Warehouse Safety showcase](ros2_ws/src/rackonaut_safety/README.md) adds aisle reservations, live signal towers and a simulated worker to the Control Center.

The [sensor-based safety showcase](ros2_ws/src/rackonaut_safety/docs/SENSOR_SAFETY.md) adds live GPU LiDAR returns, calibrated fields and movable obstacles.

The [protected aerial infrastructure demo](docs/AERIAL_INFRASTRUCTURE.md) adds an overhead flight corridor, monitored descents and a wall-side charging dock.

The [onboard obstacle avoidance demo](docs/OBSTACLE_AVOIDANCE.md) adds a spatial LiDAR, measured local bypasses and operator recovery for blocked airways.

The [sensor-based localization demo](docs/SENSOR_LOCALIZATION.md) adds LiDAR/IMU navigation and a measured warehouse point cloud with optional reference validation.

The [complete demo guide](docs/DEMO_COMPLETE.md) covers the `demo-complete` tag, launch, full inventory, reinspection and team handoff.

| Role | Guide | AI starter prompt | Suggested branch |
|---|---|---|---|
| Warehouse and computer vision | [Adrian](docs/onboarding/ADRIAN.md) | [Warehouse prompt](docs/onboarding/AI_PROMPT_WAREHOUSE.md) | `feature/warehouse`, then `feature/perception` |
| Drone and camera | [Michał](docs/onboarding/MICHAL.md) | [Drone prompt](docs/onboarding/AI_PROMPT_DRONE.md) | `feature/drone` |
| Warehouse backend | [Backend](docs/onboarding/BACKEND.md) | [Backend prompt](docs/onboarding/AI_PROMPT_BACKEND.md) | `feature/backend` |
| Dashboard | [Dashboard](docs/onboarding/DASHBOARD.md) | [Dashboard prompt](docs/onboarding/AI_PROMPT_DASHBOARD.md) | `feature/dashboard` |

Accept the private GitHub invitation before cloning. In WSL, clone under your Linux home directory. For the native Windows backend or dashboard profile, clone in a regular Windows directory.

```sh
git clone https://github.com/Adiksoon/rackonaut.git
cd rackonaut
```

Robotics uses Ubuntu 22.04 or WSL2 Ubuntu 22.04, ROS 2 Humble, Gazebo Fortress, and system Python 3.10. Fortress is the provisional team baseline. Run the commands below from the repository root in a fresh Bash shell.

```bash
source scripts/robotics/activate.bash
scripts/robotics/check
scripts/robotics/build
scripts/robotics/world
```

Backend and dashboard can start with native Windows or Linux and a Python virtual environment. Use the commands below on Ubuntu or WSL.

```bash
python3.10 -m venv .venv-backend
.venv-backend/bin/python -m pip install -r backend/requirements.txt
.venv-backend/bin/python -m uvicorn backend.mock_api:app --host 127.0.0.1 --port 8000
```

Use Python 3.13 in Windows PowerShell.

```powershell
python -m venv .venv-backend
& .\.venv-backend\Scripts\python.exe -m pip install -r backend/requirements.txt
& .\.venv-backend\Scripts\python.exe -m uvicorn backend.mock_api:app --host 127.0.0.1 --port 8000
```

Open the mock API at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). Run the role-specific smoke check before reporting readiness. Press Ctrl+C in the terminal that started the world or API to stop it.

On the integration host, set up both profiles. With manually started reference processes stopped, run `scripts/smoke-baseline` to check the local API and robotics baseline. The individual robotics checks are `scripts/robotics/smoke --mock` and `scripts/robotics/smoke --reference`.

## Project references

- [Architecture](docs/ARCHITECTURE.md) and [interface index](docs/INTERFACES.md)
- [Team responsibilities and Git workflow](docs/TEAM_TASKS.md)
- [Integration sequence](docs/INTEGRATION.md) and [technical decisions](docs/DECISIONS.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md) and [agent instructions](AGENTS.md)
