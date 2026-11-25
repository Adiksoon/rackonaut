# Baseline test results

The tests distinguish environment checks, synthetic fixtures, reference simulator output, and integration of the team's future modules. Use the exact commands in the role guides to repeat the relevant profile.

## Test host

The integration host uses Windows 11 Education with WSL2 Ubuntu 22.04.5. Robotics uses ROS 2 Humble, Gazebo Fortress 6.16.0, system CPython 3.10.12, OpenCV 4.5.4, NumPy 1.21.5, `cv_bridge` 3.2.1, `ros_gz` 0.244.23, and colcon-core 0.20.1. Native Windows backend checks use CPython 3.13.15. The API uses FastAPI 0.162.5, Uvicorn 0.54.0, and JSON Schema 4.26.0. Backend dependencies are pinned in [`requirements.txt`](../backend/requirements.txt).

The tested baseline is `50ec5e81f58de8072130d645b34edc601cb896fa` on 25 November 2026. The WSL test used a new local clone with `--no-local` and ran the robotics profile, fixture API, and dependency plan. Native Windows used an authenticated GitHub clone of that same revision with its own clean virtual environment. Both checkouts stayed clean after running the profiles. Team machines and a fresh OS installation are outside this evidence.

## Environment, fixtures, and reference simulation

| ID | Procedure | Expected result | Status and observed evidence |
|---|---|---|---|
| ENV-01 | `source scripts/robotics/activate.bash` | Activate the Humble underlay and project discovery settings | **PASS**. ROS domain 62, localhost discovery, `rmw_fastrtps_cpp`, and project resource path. |
| ENV-02 | Activate with deliberately injected AMENT, colcon, Python and Gazebo paths | Discard foreign overlays and preserve project-owned paths | **PASS**. All five injected path values were absent after activation. The clean pre-build clone reported only `/opt/ros/humble` in `AMENT_PREFIX_PATH`. |
| ENV-03 | `scripts/robotics/check` and each venv's `python -m pip check` | Use the intended runtimes and import compatible dependencies | **PASS**. System Python `3.10.12` with OpenCV `4.5.4`, NumPy `1.21.5` and a `cv_bridge` round-trip. Python `3.13.15` on Windows. Both venvs reported no broken requirements. |
| ROS-01 | `scripts/robotics/build` | Build the minimum ROS workspace from sources | **PASS**. One package, `rackonaut_reference`, built in the clean clone before any `build/` or `install/` existed. |
| ROS-02 | `scripts/robotics/smoke --mock` or the mock phase of `scripts/robotics/smoke` | Pair a synthetic frame and camera calibration over ROS 2 | **PASS**. `640×360 rgb8` and matching `CameraInfo` on the canonical optical frame. |
| SIM-01 | Reference phase of `scripts/robotics/smoke` | Receive advancing simulator time | **PASS**. `/clock` advanced from `1.224` to `1.228` s in the clean-clone probe. The warehouse-only runner was exercised separately. |
| SIM-02 | Same reference probe | Spawn the separately loaded drone and observe odometry | **PASS**. Received `rackonaut_odom` → `rackonaut_base_link`. A separate run verified dynamic `/tf` and late-subscriber `/tf_static` delivery. |
| SIM-03 | Same reference probe | Move the reference drone upward by at least `0.15 m` via a ROS command | **PASS**. Command `+0.25 m/s` moved the model from `0.048` to `0.239 m`. The probe sends zero commands before shutdown. |
| CAM-01 | Same reference probe, with the image mock inactive | Receive a real Gazebo RGB frame with matching calibration over ROS 2 | **PASS**. `320×240 rgb8`, `rackonaut_camera_optical_frame`, matching stamp `1.224 s`. |
| CV-01 | Convert the CAM-01 frame using the system Python and `cv_bridge` | Produce a nonuniform OpenCV BGR image | **PASS**. Shape `(240, 320, 3)` and grayscale standard deviation `49.0`. |
| API-01 | `<venv-python> scripts/api/smoke.py` | Accept an observation, handle identical retries, reject invalid input and conflicts | **PASS** on WSL and Windows. Real loopback HTTP POST `201`, identical retry `200`, conflicting payload `409`, plus validation failures. |
| API-02 | Same HTTP smoke | Read contract-compatible results independently of ROS | **PASS** on WSL and Windows. Inventory, observations, discrepancies, summary, OpenAPI and loopback CORS worked. Eight fixture scenarios and eight unique event rows were checked. |
| CONTRACT-01 | `<venv-python> -m unittest discover -s tests -v` | Validate fixture inputs, response schemas, and ordering rules | **PASS**. Four test groups on each platform, including all eight scenarios. |
| CLEAN-01 | Finish the robotics and API smoke scripts | Release the launched reference processes and API listener | **PASS**. The robotics harness reported its owned process groups exited. The API harness reported the owned Uvicorn server stopped on both platforms. |

Robotics run logs are created under `ros2_ws/log/` in the tested checkout. The committed [role guides](../README.md#start-here) give the exact environment and launch commands. `scripts/smoke-baseline` runs the API checks and the robotics build and probes from the same WSL checkout.

The earlier hardware-rendered WSL trial **failed** inside OGRE2 at `GL3PlusTextureGpu::copyTo`. The supported reference runner on this host defaults to headless llvmpipe, which passed motion and camera checks. A standalone GUI world was visible in a separate WSLg trial. A full GUI flight, hardware-rendered flight, RGB-D, and the Classic fallback are outside the supported baseline evidence.

## Reproducibility and Git

| ID | Procedure | Status and evidence |
|---|---|---|
| REPRO-01, GIT-01 | `git clone --no-local --branch main <local-repository>` on WSL and `git clone --branch main https://github.com/Adiksoon/rackonaut.git` on Windows | **PASS**. Both resolved the same source revision and initially contained no ROS build output or backend venv. |
| REPRO-02 | Clean WSL clone, `scripts/robotics/check`, `scripts/robotics/build`, `scripts/robotics/smoke` | **PASS**. The reference package built and both robotics smoke phases passed with the system dependencies already installed. Project-local `rosdep update --rosdistro humble` and `scripts/robotics/dependencies` also completed. |
| REPRO-03 | Clean WSL clone, `python3.10 scripts/api/setup.py`, dependency check, unit tests and HTTP smoke | **PASS**. A new isolated venv installed the lock and ran without using a ROS activation step. |
| REPRO-04 | Clean native Windows GitHub clone, `python.exe scripts/api/setup.py`, dependency check, unit tests and HTTP smoke | **PASS**. CPython `3.13.15` installed compatible pinned wheels and served the fixtures on loopback. |
| REPRO-05 | HTTP smoke on both checkouts | **PASS**. A dashboard author can read the fixture results and use a loopback development origin without a team backend. |
| REPRO-06 | Staged path and credential-pattern scan, artifact exclusions, and two separate clone paths | **PASS**. No machine-specific source path or usual credential pattern matched. Both checkouts ran with local artifacts generated from scratch. |
| REPRO-07 | Link and shell syntax validation of the onboarding guides plus the documented profile commands | **PASS**. 61 relative links, 16 Bash snippets, and four PowerShell snippets were checked. Live tests exercised the documented scripts. |
| GIT-02 | Authenticated repository creation and `git ls-remote --symref origin HEAD refs/heads/main`, followed by a native Windows clone | **PASS**. GitHub confirmed private visibility and `main`. Anonymous API lookup returned HTTP `404`. Collaborator access remains pending individually addressed invites. |

**Team module integration — NOT RUN.** These are fixture and reference-simulator results. See the [integration gates](INTEGRATION.md) for the future warehouse, selected drone, perception, backend, and dashboard checks.
