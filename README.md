# Rackonaut

[![Contract tests](https://github.com/Adiksoon/rackonaut/actions/workflows/contract-tests.yml/badge.svg?branch=main)](https://github.com/Adiksoon/rackonaut/actions/workflows/contract-tests.yml)

Rackonaut is a RobotHack 2026 prototype for inspecting warehouse shelves with a drone. It uses camera images to check which storage locations are occupied, read pallet labels, and flag visible carton damage.

![Reference drone flying beside labeled storage racks in the Gazebo warehouse](docs/images/gazebo-drone-in-aisle.png)

*Reference drone during an inspection flight in Gazebo.*

## Project status

- **Development baseline (`main`)** provides the ROS 2 workspace, a Gazebo camera feed, synthetic test data, and a mock inventory REST API. See the [baseline test results](docs/TEST_RESULTS.md).
- **Simulation demo (`demo-complete`)** runs a browser-launched inspection with the reference drone and a mock inventory API. The recorded full run visited 11 locations and produced an inspection report. The demo also supports reinspection of selected locations. See the [demo guide and run evidence](https://github.com/Adiksoon/rackonaut/blob/demo-complete/docs/DEMO_COMPLETE.md).

## Start here

Joining the project? See [team onboarding](#team-onboarding) for your role and branch.

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

### Run the contract tests locally

After installing the backend dependencies above, run the same contract tests as GitHub Actions from the repository root. They use fixtures and run without starting Gazebo or the API server.

On Ubuntu or WSL:

```bash
.venv-backend/bin/python -m unittest discover -s tests -v
```

On Windows PowerShell:

```powershell
& .\.venv-backend\Scripts\python.exe -m unittest discover -s tests -v
```

## Team onboarding

| Role | Guide | AI starter prompt | Suggested branch |
|---|---|---|---|
| Warehouse and computer vision | [Adrian](docs/onboarding/ADRIAN.md) | [Warehouse prompt](docs/onboarding/AI_PROMPT_WAREHOUSE.md) | `feature/warehouse`, then `feature/perception` |
| Drone and camera | [Michał](docs/onboarding/MICHAL.md) | [Drone prompt](docs/onboarding/AI_PROMPT_DRONE.md) | `feature/drone` |
| Warehouse backend | [Backend](docs/onboarding/BACKEND.md) | [Backend prompt](docs/onboarding/AI_PROMPT_BACKEND.md) | `feature/backend` |
| Dashboard | [Dashboard](docs/onboarding/DASHBOARD.md) | [Dashboard prompt](docs/onboarding/AI_PROMPT_DASHBOARD.md) | `feature/dashboard` |

## Project references

- [Architecture](docs/ARCHITECTURE.md) and [interface index](docs/INTERFACES.md)
- [Team responsibilities and Git workflow](docs/TEAM_TASKS.md)
- [Integration sequence](docs/INTEGRATION.md) and [technical decisions](docs/DECISIONS.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md) and [agent instructions](AGENTS.md)
