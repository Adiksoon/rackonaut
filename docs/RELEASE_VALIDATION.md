# RobotHack 2026 release validation

This page records verification of the RobotHack release tree and points to the original flight trials. The release builds on the full-calibration revision `bacf4c9`, which includes Full System Integration `dc9813c` and the prior `main` at `6e04fcf`. Use the GitHub Actions run for the commit being reviewed to confirm the hosted check. [Contract tests workflow](https://github.com/Adiksoon/rackonaut/actions/workflows/contract-tests.yml)

## Release checks

Local checks used a clean Ubuntu 22.04.5 WSL2 worktree with ROS 2 Humble, Gazebo Fortress 6.16.0 and Python 3.10.12.

| Check | Result | Reproduction |
| --- | --- | --- |
| Environment | PASS · ROS, Fortress, rosdep dependencies and OpenCV/cv_bridge round-trip | `scripts/robotics/check` and `rosdep check --from-paths ros2_ws/src --ignore-src --rosdistro humble --skip-keys=ament_python` after activation and rosdep update |
| ROS build | PASS · 11 packages from a clean checkout | `scripts/robotics/build` |
| ROS tests | PASS · 89 tests | `source scripts/robotics/activate.bash` and `/usr/bin/python3 -m pytest -q ros2_ws/src` |
| Backend, contracts and importer | PASS · 62 tests, including 54 importer tests | `.venv-backend/bin/python -m unittest discover -s tests` |
| HTTP smoke | PASS · fixture API startup, idempotency, conflict handling, eight representative scenarios and process shutdown, plus HTTP 200 for functional Mock SAP inventory, products and OpenAPI | `.venv-backend/bin/python scripts/api/smoke.py` |
| World generation and X3 asset preparation | PASS · four installed localization worlds and two integrated X3 SDF profiles; released warehouse JSON configuration parses; fresh Fuel v4 download passes asset hashes | `ign sdf -k` after the ROS build and `ros2_ws/src/rackonaut_drone/scripts/prepare_model` with both `--integrated` settings |
| Published reference archive | PASS · 25 file hashes, model and world compatibility, 480 LiDAR keyframes and 94,194 PLY points | Extract the archive into a fresh directory and use the [warehouse archive verifier](../ros2_ws/src/rackonaut_localization/rackonaut_localization/warehouse_config.py) and [LiDAR readers](../ros2_ws/src/rackonaut_localization/rackonaut_localization/learned_map.py) |
| Pinned environment library | PASS · generation of all three SDFs, geometry and fixture validator, and `ign sdf -k` for each world | Use the offline commands in the [pinned companion report](https://github.com/Adiksoon/rackonaut/blob/6b9ebfaba39bd5e091d5de5f7d23301a9ec35115/docs/MULTI_WAREHOUSE_ENVIRONMENTS.md#generowanie-i-uruchomienie) |
| Launch and CI configuration | PASS · ROS launch arguments load, six launch action graphs assemble offline, critical Bash scripts parse and the workflow passes actionlint | `scripts/robotics/checkpoint live --show-args`, `bash -n` and `actionlint` |
| Documentation links | PASS · local paths, images, Markdown anchors and pinned source references across repository Markdown | Check tracked Markdown and pinned Git targets |
| Live Gazebo startup and flight | NOT RUN on the release revision | The release check left the simulator available for video production. Original flight telemetry is linked below. |
| New multi-sortie calibration campaign | NOT RUN on the release revision | Use the published archive and original survey evidence. |

## Original flight trials

| Trial | Evidence revision | Source |
| --- | --- | --- |
| Multi-sortie survey and two learned replays, reference drone, open-aisle | `bacf4c9` | [Survey and restart report](FULL_WAREHOUSE_CALIBRATION.md) |
| Open-aisle one-location flight and separate X3 startup check | `dc9813c` | [Open-aisle report](OPEN_AISLE_DESCENT.md) |
| 11-location known-map inventory with X3 and automatic charging | `cd3f3b3` | [Full System Integration](FULL_SYSTEM_INTEGRATION.md#c--x3-na-znanej-mapie) |
| Warehouse in Motion moving-cart response and 3/3 inventory | `af38561` | [Original telemetry and results](FINAL_BRANCH_AUDIT.md#walidacja) |
| Additional halls, static validation and dock startup | `6b9ebfa` | [Companion environment report](https://github.com/Adiksoon/rackonaut/blob/6b9ebfaba39bd5e091d5de5f7d23301a9ec35115/docs/MULTI_WAREHOUSE_ENVIRONMENTS.md) |

## Repository provenance

| Reference | Purpose |
| --- | --- |
| `main`, `release/robothack-2026` | Contest publication and release preparation, respectively. |
| `integration/competition-main` at `5e3696d` | Historical baseline merged into the previous `main` at `6e04fcf`. |
| `integration/full-system` at `dc9813c` | Earlier integrated Control Center, X3, reference drone, open-aisle warehouse and scenario acceptance. |
| `feature/full-warehouse-calibration` at `bacf4c9` | Release source for the multi-sortie calibration, sealed archive, measured model and learned replay. |
| `feature/multi-warehouse-environments` at `6b9ebfa` | Companion profile for the three larger scenes. It branches from the same `dc9813c` base and changes overlapping launcher, configuration and Control Center behavior. Its revision keeps its generated assets, data and validation together. |
| `demo-baseline`, `demo-complete`, `demo-quality` | Historical stable demonstrations with their own tagged code and evidence. |
| Other `feature/*`, `codex/*` and integration branches | Earlier module work, intermediate integrations, exploratory trials and evidence. [Earlier branch audit](FINAL_BRANCH_AUDIT.md#inwentarz-branchy) |

The X3 contribution in [PR #7](https://github.com/Adiksoon/rackonaut/pull/7) was adapted through the seven source-attributed cherry-picks and the integrated X3 merge `7dfcd3f`. The shared X3 model preparation, camera bridge, localization and mission path are in the release tree. The CSV importer in [PR #8](https://github.com/Adiksoon/rackonaut/pull/8) keeps Vahid Abdullayev's original commit `0efb6b0` through merge `3f42ff7`. The PRs remain links to the original submissions. [Contribution register](TEAM_TASKS.md) · [X3 source mapping](FINAL_BRANCH_AUDIT.md#featuredrone)

The pre-release audit counted 51 remote branches. Git history retains the original commits, stable tags, test evidence and earlier attempts. The release inventory checked tracked build artifacts, caches, private configuration, database and media paths. The largest tracked file is the verified calibration archive. A redacted Gitleaks check covered the release history and fetched remote heads and tags. It reported no matches. [Published archive](full-warehouse-calibration-evidence/verified-survey/warehouse-configuration.tar.gz)
