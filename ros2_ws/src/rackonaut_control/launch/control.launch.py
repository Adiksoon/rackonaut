"""Start a local Control Center with the reference simulator and an optional fixture API."""

import json
import os
from pathlib import Path

from ament_index_python.packages import get_package_share_path
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, ExecuteProcess, OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def setup(context):
    def arg(name):
        return LaunchConfiguration(name).perform(context)

    def enabled(name):
        value = arg(name).lower()
        if value not in ("true", "false"):
            raise ValueError(f"{name} expects true or false")
        return value == "true"

    root = Path(os.environ["RACKONAUT_ROOT"])
    warehouse = get_package_share_path("rackonaut_warehouse")
    safety = enabled("safety")
    mode = arg("safety_sensor")
    if mode not in {"virtual", "laser"} or (mode == "laser" and not safety):
        raise ValueError("safety_sensor must be virtual or laser. Laser mode requires safety:=true.")
    laser = mode == "laser"
    if enabled("laser_rviz") and not laser:
        raise ValueError("laser_rviz requires safety_sensor:=laser.")
    world = "laser_safety_showcase.sdf" if laser else "safety_showcase.sdf" if safety else "control_showcase.sdf"
    localization = arg("localization")
    if localization not in {"ground_truth", "shadow", "sensor_based"}:
        raise ValueError("Select ground_truth, shadow or sensor_based localization.")
    localizer = localization != "ground_truth"
    diagnostics = enabled("localization_diagnostics")
    recovery = enabled("recovery")
    learned_warehouse = enabled("learned_warehouse")
    mapping_only = enabled("mapping_only") or learned_warehouse
    full_route_slam = enabled("full_route_slam") or learned_warehouse
    if recovery and localization != "sensor_based":
        raise ValueError("recovery:=true requires localization:=sensor_based.")
    if mapping_only and not recovery:
        raise ValueError("mapping_only:=true requires the Full Robotics profile with Recovery.")
    if full_route_slam and not recovery:
        raise ValueError("full_route_slam:=true requires the Full Robotics profile with Recovery.")
    if diagnostics and not localizer:
        raise ValueError("Localization diagnostics require the localizer.")
    avoidance = enabled("avoidance") or localizer
    aerial = enabled("aerial") or avoidance
    if aerial and not safety:
        raise ValueError("aerial:=true requires safety:=true.")
    energy = enabled("energy") or aerial
    adaptive = enabled("adaptive_world") or energy
    if adaptive:
        if not safety:
            raise ValueError("adaptive_world requires safety:=true.")
        world = "adaptive_laser_showcase.sdf" if laser else "adaptive_showcase.sdf"
    if energy:
        world = "energy_laser_showcase.sdf" if laser else "energy_showcase.sdf"
    if aerial:
        world = "aerial_laser_showcase.sdf" if laser else "aerial_showcase.sdf"
    if avoidance:
        world = "avoidance_laser_showcase.sdf" if laser else "avoidance_showcase.sdf"
    if localizer:
        world = "localization_laser_showcase.sdf" if laser else "localization_showcase.sdf"
    command = [str(root / "scripts/robotics/reference"), "--world", str(warehouse / "worlds" / world)]
    profile = json.loads((warehouse / "config/aerial_layout.json").read_text()) if aerial else None
    props = json.loads((warehouse / "config/avoidance_layout.json").read_text()) if avoidance else {}
    if avoidance:
        command.append("--avoidance")
    if localizer:
        command.extend(["--localization", localization])
    if diagnostics:
        command.append("--localization-validation")
    if full_route_slam:
        command.append("--full-route-slam")
    if profile:
        dock = profile["nodes"]["dock"]
        command.extend(["--spawn", str(dock[0]), str(dock[1]), str(dock[2] + .07), "0"])
    if enabled("gazebo_gui"):
        command.append("--gui")
    processes = [ExecuteProcess(cmd=command, cwd=str(root), output="screen", name="control_simulator")]
    data = arg("data_dir") or str(Path(os.environ["ROS_LOG_DIR"]) / "control")
    api_profile = arg("api_profile")
    if api_profile not in {"fixture", "mock_sap"}:
        raise ValueError("api_profile must be fixture or mock_sap.")
    backend = arg("backend_url") or f"http://127.0.0.1:{arg('mock_port')}"
    if enabled("mock"):
        expected = f"http://127.0.0.1:{arg('mock_port')}"
        if backend.rstrip("/") != expected:
            raise ValueError("Set mock:=false when selecting an external backend.")
        python = root / ".venv-backend/bin/python"
        if not python.is_file():
            raise RuntimeError("Run python3.10 scripts/api/setup.py to prepare the fixture API.")
        api_app = ["backend.sap_api:app", "--factory"] if api_profile == "mock_sap" else ["backend.control_fixture:app"]
        processes.append(ExecuteProcess(
            cmd=[str(python), "-m", "uvicorn", *api_app, "--host", "127.0.0.1", "--port", arg("mock_port")],
            cwd=str(root), name=f"control_{api_profile}", output="screen",
            additional_env={"RACKONAUT_SAP_DB": str(Path(data).expanduser().resolve() / "warehouse.sqlite3")},
        ))
    elif not arg("backend_url"):
        raise ValueError("Provide backend_url when mock:=false.")
    localization_nodes = []
    if localizer:
        localization_nodes.append(Node(package="rackonaut_localization", executable="localize", output="screen",
                              additional_env={"OPENBLAS_NUM_THREADS": "1"},
                              parameters=[{"mode": localization, "data_dir": data, "mapping_only": mapping_only,
                                           "full_route_slam": full_route_slam, "learned_warehouse": learned_warehouse,
                                           **({"dock_xyz": profile["nodes"]["dock"]} if mapping_only else {})}]))
    if recovery:
        localization_nodes.append(Node(
            package="ros_gz_bridge", executable="parameter_bridge", name="rackonaut_flight_enable_bridge", output="screen",
            arguments=["/rackonaut_reference/enable@std_msgs/msg/Bool]ignition.msgs.Boolean"],
            remappings=[("/rackonaut_reference/enable", "/rackonaut/drone/flight_enabled")]))
    if diagnostics:
        localization_nodes.append(Node(package="rackonaut_localization", executable="validate_pose", output="screen",
                              additional_env={"OPENBLAS_NUM_THREADS": "1"}, parameters=[{"data_dir": data}]))
    processes.append(Node(package="rackonaut_control", executable="serve", output="screen", parameters=[{
        "http_port": int(arg("http_port")),
        "backend_url": backend,
        "data_dir": data,
        "safety_enabled": safety,
        "safety_sensor": mode,
        "adaptive_world": adaptive,
        "energy_enabled": energy,
        "aerial_enabled": aerial,
        "avoidance_enabled": avoidance,
        "localization_mode": localization,
        "localization_diagnostics": diagnostics,
        "autonomous_recovery": recovery,
        "mapping_only": mapping_only,
        "full_route_slam": full_route_slam,
        "learned_warehouse": learned_warehouse,
    }]))
    if energy:
        initial = arg("battery_initial")
        level = (100. if aerial else 64.) if initial == "auto" else float(initial)
        processes.append(Node(package="rackonaut_energy", executable="manage", output="screen", parameters=[{
            "initial_percent": level,
            "charge": float(arg("charge_rate")),
            "events_file": str(Path(data) / "charge-cycles.jsonl"),
            "aerial": aerial,
            "sensor_localization": localization == "sensor_based",
            "autonomous_recovery": recovery,
            **({"hover": .26, "movement": .19, "climb": .52} if aerial else {}),
        }]))
    on_exit = [RegisterEventHandler(OnProcessExit(
        target_action=process, on_exit=[EmitEvent(event=Shutdown(reason="A Control Center service stopped"))],
    )) for process in processes]
    safety_nodes = []
    if safety:
        config = get_package_share_path("rackonaut_safety") / "config"
        safety_nodes = [
            Node(package="rackonaut_safety", executable="manage", output="screen",
                 parameters=[{"events_file": str(Path(data) / "safety-events.jsonl"), "sensor_mode": mode,
                              "aerial": aerial, "autonomous_recovery": recovery}]),
            Node(package="rackonaut_safety", executable="infrastructure", output="screen",
                 parameters=[{"laser_props": laser, "energy_dock": energy, "aerial": aerial,
                              **({f"descent_{zone}": profile["nodes"][f"foot_{zone}"][:2] for zone in ("A", "B")}
                                 if profile else {}),
                              **({"avoidance_props": list(props),
                                  **{f"prop_{key}": [*row["park"], *row["location"]] for key, row in props.items()}}
                                 if props else {})}]),
            *(Node(package="ros_gz_bridge", executable="parameter_bridge", name=f"safety_{name}_bridge",
                   parameters=[{"config_file": str(config / f"{name}_bridge.yaml")}], output="screen")
              for name in (("laser", "presence", "overview") if laser and aerial
                           else ("laser" if laser else "presence", "overview"))),
        ]
        if laser:
            scanners = json.loads((warehouse / "config/laser_fields.json").read_text())
            for zone, scanner in scanners.items():
                x, y, z, yaw = map(str, scanner["pose"])
                safety_nodes.append(Node(package="tf2_ros", executable="static_transform_publisher",
                    name=f"safety_scan_tf_{zone.lower()}", arguments=[
                        "--x", x, "--y", y, "--z", z, "--yaw", yaw,
                        "--frame-id", "rackonaut_odom", "--child-frame-id", scanner["frame"],
                    ]))
            if enabled("laser_rviz"):
                safety_nodes.append(Node(package="rviz2", executable="rviz2", output="screen",
                                         arguments=["-d", str(config / "laser_safety.rviz")]))
    return [*on_exit, *processes, *localization_nodes, *safety_nodes]


def generate_launch_description():
    defaults = {"http_port": "8765", "mock": "true", "mock_port": "8000", "backend_url": "", "api_profile": "fixture",
                "gazebo_gui": "false", "data_dir": "", "safety": "false",
                "safety_sensor": "virtual", "laser_rviz": "false", "adaptive_world": "false",
                "energy": "false", "aerial": "false", "avoidance": "false",
                "localization": "ground_truth", "localization_diagnostics": "false",
                "recovery": "false", "mapping_only": "false", "full_route_slam": "false", "learned_warehouse": "false",
                "battery_initial": "auto", "charge_rate": "6.0"}
    return LaunchDescription([
        *(DeclareLaunchArgument(name, default_value=value) for name, value in defaults.items()),
        OpaqueFunction(function=setup),
    ])
