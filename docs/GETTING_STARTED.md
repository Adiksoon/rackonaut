# Run Rackonaut

## Clean checkout

Use Ubuntu 22.04 or WSL2 Ubuntu 22.04 on the Linux filesystem. Install ROS 2 Humble and the Gazebo Fortress integration for Humble. The ROS workspace uses system Python 3.10. The backend has a separate repository-local virtual environment. Use a WebGL2 browser for 3D views. The simulator runs headless by default. To open Gazebo or RViz on WSL2, use a working WSLg display. [ROS 2 Humble installation](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html) · [Fortress and ROS 2](https://gazebosim.org/docs/fortress/ros_installation/)

After configuring the ROS and Gazebo package sources and installing Humble and Fortress, prepare the checkout. The repository requires authenticated GitHub access.

```bash
sudo apt install git python3-colcon-common-extensions python3-rosdep python3.10-venv python3-pytest
git clone https://github.com/Adiksoon/rackonaut.git
cd rackonaut
source scripts/robotics/activate.bash
```

If the system has no rosdep sources configured, run `sudo rosdep init` once. Then install workspace dependencies, including the ROS bridge, OpenCV and cv_bridge, before building. Colcon handles the `ament_python` build type.

```bash
rosdep update --rosdistro humble
rosdep install --from-paths ros2_ws/src --ignore-src --rosdistro humble --skip-keys=ament_python
scripts/robotics/check
python3.10 scripts/api/setup.py
scripts/robotics/build
```

Run launch commands from the repository root. Run one simulator at a time and shut it down with Ctrl+C in its launch terminal before switching profiles. The launchers start Control Center at [port 8765](http://127.0.0.1:8765/) and Mock SAP at [port 8000](http://127.0.0.1:8000/docs). Use `http_port:=` and `mock_port:=` to choose other ports. Set `data_dir:=` to a dedicated absolute path for an independent database and mission archive. [Control Center launch options](../ros2_ws/src/rackonaut_control/README.md)

## Demo profiles

### Open-aisle reference inspection

```bash
scripts/robotics/checkpoint live warehouse_variant:=open-aisle drone_model:=reference
```

1. Open [Control Center](http://127.0.0.1:8765/). Wait for **Mock SAP online**, a fresh image, localization **TRACKING** and verified dock contact.
2. Choose **Selected locations**, select **A-01-01** and start. In **Live flight**, watch the overhead approach, descent, photo capture and return.
3. After docking, open **Results**. Inspect the location's image and stock comparison, then export the HTML report.

This profile uses the known open-aisle reference map and virtual ground-zone presence. Onboard LiDAR and simulated dock contact are active. Add `gazebo_gui:=true` to watch in Gazebo. In Digital Twin, use **Aerial infrastructure** for the suspended structure and **Flight corridor** for the flight envelope. [Recorded one-location flight](open-aisle-evidence/reference-flight.json)

### X3 on a known map

Download **Fuel revision 4** once. The preparation tool verifies the SHA-256 of the SDF, the meshes and the X3 texture before use. The default asset lives in the Fuel cache under `~/.ignition`. For an alternate trusted local copy, provide `x3_source:=/absolute/path/to/model-directory` on launch. [X3 asset and model notes](X3_FULL_ROBOTICS_INTEGRATION.md)

```bash
source scripts/robotics/activate.bash
ign fuel download -u 'https://fuel.gazebosim.org/1.0/OpenRobotics/models/X3%20UAV/4'
scripts/robotics/checkpoint live warehouse_variant:=historical drone_model:=x3 \
  full_route_slam:=false data_dir:="$PWD/.rackonaut-data/x3-known"
```

Use **Full inventory** to reproduce the verified known-map profile with automatic charging and resumption. This takes longer than the one-location reference demo. Add `warehouse_variant:=open-aisle` in place of `warehouse_variant:=historical` to view X3 with open portals. The recorded open-aisle X3 check covered dock startup, camera and localization. [Known-map mission](full-system-evidence/x3-known-inventory.json) · [Open-aisle X3 startup](open-aisle-evidence/x3-startup.json)

### Business comparison and Warehouse in Motion

- **Business Demo.** Run `scripts/robotics/checkpoint business drone_model:=x3`. Select **A-01-01** through **A-01-04** and enable **Check for package damage** and **Retry difficult readings**. Review the difference between expected and observed stock in **Results**. [Recorded Business Demo](FULL_SYSTEM_INTEGRATION.md#d--business-demo)
- **Warehouse in Motion.** Run `scripts/robotics/warehouse-in-motion --keep-open` after preparing Fuel. Open [scenario Control Center](http://127.0.0.1:18770/). The scenario dispatches a three-location inspection and moves the cart. After completion, review the original camera images and report. Add `--gui` to see the cart in Gazebo. [Scenario instructions and evidence](WAREHOUSE_IN_MOTION.md)

### Restore the verified open-aisle calibration

The published archive is for the **reference drone** and the **open-aisle** world. Use a new data directory so Control Center can store the local activation and run results.

```bash
mkdir -p .rackonaut-data
survey_dir="$(mktemp -d "$PWD/.rackonaut-data/open-aisle-survey.XXXXXXXX")"
tar -xzf docs/full-warehouse-calibration-evidence/verified-survey/warehouse-configuration.tar.gz \
  -C "$survey_dir"
read -rsp 'Choose a local Service code: ' RACKONAUT_SERVICE_CODE
printf '\n'
export RACKONAUT_SERVICE_CODE
scripts/robotics/checkpoint live warehouse_variant:=open-aisle drone_model:=reference \
  learned_warehouse:=true data_dir:="$survey_dir"
```

At the verified dock, unlock **Service** with the code you chose. Open **Warehouse Configuration** and select `WH-D11FA03D45502B0ECE140FB6C611E072`. Verify the archive, activate it, and wait for **TRACKING**. In **Plan inspection**, view all 11 taught locations and the four sortie budgets. Select **A-01-08** or **B-02-01** for the verified one-location replay. Dispatch those sorties separately. [Restart proof and archive](FULL_WAREHOUSE_CALIBRATION.md#restart-i-odtworzenie)

For a new full survey, start with an empty data directory and follow the calibration workflow. It involves multiple operator-dispatched flights, charging at the dock, location teaching and route approval. [Full calibration procedure](FULL_WAREHOUSE_CALIBRATION.md#uruchomienie)

### Additional warehouses

The companion environment profile is pinned at `6b9ebfaba39bd5e091d5de5f7d23301a9ec35115`. Use a separate checkout and build so its warehouse settings, Mock SAP fixtures and archives match that revision. Its launch blocks production dispatch while it starts in mapping mode. Prior validation covers generated geometry, fixtures and dock startup. [Environment report and telemetry](https://github.com/Adiksoon/rackonaut/blob/6b9ebfaba39bd5e091d5de5f7d23301a9ec35115/docs/MULTI_WAREHOUSE_ENVIRONMENTS.md)

```bash
git worktree add --detach ../rackonaut-warehouse-library 6b9ebfaba39bd5e091d5de5f7d23301a9ec35115
cd ../rackonaut-warehouse-library
scripts/robotics/check
python3.10 scripts/api/setup.py
scripts/robotics/build
scripts/robotics/checkpoint live warehouse_variant:=distribution-center
```

Choose `high-bay` or `logistics-hub` for the other halls. The default drone is `reference`. The pinned profile also accepts `drone_model:=x3` with the Fuel asset and recorded dock startup for that combination in High-Bay. [Gallery](GALLERY.md#additional-warehouses)

## Engineering views

Use `scripts/robotics/checkpoint tools` to open RViz Navigation beside the live demo. The launcher also supports dedicated Vision, Safety, ROS graph and telemetry views. For review without the simulator, the evidence launcher can play an existing ROS bag on a separate ROS domain. [Engineering views and recorded replay](ENGINEERING_SHOWCASE.md) · [Troubleshooting](TROUBLESHOOTING.md)
