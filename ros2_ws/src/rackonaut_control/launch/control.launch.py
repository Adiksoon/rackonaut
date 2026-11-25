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
    energy = enabled("energy")
    adaptive = enabled("adaptive_world") or energy
    if adaptive:
        if not safety:
            raise ValueError("adaptive_world requires safety:=true.")
        world = "adaptive_laser_showcase.sdf" if laser else "adaptive_showcase.sdf"
    if energy:
        world = "energy_laser_showcase.sdf" if laser else "energy_showcase.sdf"
    command = [str(root / "scripts/robotics/reference"), "--world", str(warehouse / "worlds" / world)]
    if enabled("gazebo_gui"):
        command.append("--gui")
    processes = [ExecuteProcess(cmd=command, cwd=str(root), output="screen", name="control_simulator")]
    backend = arg("backend_url") or f"http://127.0.0.1:{arg('mock_port')}"
    if enabled("mock"):
        expected = f"http://127.0.0.1:{arg('mock_port')}"
        if backend.rstrip("/") != expected:
            raise ValueError("Set mock:=false when selecting an external backend.")
        python = root / ".venv-backend/bin/python"
        if not python.is_file():
            raise RuntimeError("Run python3.10 scripts/api/setup.py to prepare the fixture API.")
        processes.append(ExecuteProcess(
            cmd=[str(python), "-m", "uvicorn", "backend.control_fixture:app", "--host", "127.0.0.1",
                 "--port", arg("mock_port")], cwd=str(root), name="control_fixture", output="screen",
        ))
    elif not arg("backend_url"):
        raise ValueError("Provide backend_url when mock:=false.")
    data = arg("data_dir") or str(Path(os.environ["ROS_LOG_DIR"]) / "control")
    processes.append(Node(package="rackonaut_control", executable="serve", output="screen", parameters=[{
        "http_port": int(arg("http_port")),
        "backend_url": backend,
        "data_dir": data,
        "safety_enabled": safety,
        "safety_sensor": mode,
        "adaptive_world": adaptive,
        "energy_enabled": energy,
    }]))
    if energy:
        processes.append(Node(package="rackonaut_energy", executable="manage", output="screen", parameters=[{
            "initial_percent": float(arg("battery_initial")),
            "charge": float(arg("charge_rate")),
            "events_file": str(Path(data) / "charge-cycles.jsonl"),
        }]))
    on_exit = [RegisterEventHandler(OnProcessExit(
        target_action=process, on_exit=[EmitEvent(event=Shutdown(reason="A Control Center service stopped"))],
    )) for process in processes]
    safety_nodes = []
    if safety:
        config = get_package_share_path("rackonaut_safety") / "config"
        safety_nodes = [
            Node(package="rackonaut_safety", executable="manage", output="screen",
                 parameters=[{"events_file": str(Path(data) / "safety-events.jsonl"), "sensor_mode": mode}]),
            Node(package="rackonaut_safety", executable="infrastructure", output="screen",
                 parameters=[{"laser_props": laser, "energy_dock": energy}]),
            *(Node(package="ros_gz_bridge", executable="parameter_bridge", name=f"safety_{name}_bridge",
                   parameters=[{"config_file": str(config / f"{name}_bridge.yaml")}], output="screen")
              for name in ("laser" if laser else "presence", "overview")),
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
    return [*on_exit, *processes, *safety_nodes]


def generate_launch_description():
    defaults = {"http_port": "8765", "mock": "true", "mock_port": "8000", "backend_url": "",
                "gazebo_gui": "false", "data_dir": "", "safety": "false",
                "safety_sensor": "virtual", "laser_rviz": "false", "adaptive_world": "false",
                "energy": "false", "battery_initial": "64.0", "charge_rate": "6.0"}
    return LaunchDescription([
        *(DeclareLaunchArgument(name, default_value=value) for name, value in defaults.items()),
        OpaqueFunction(function=setup),
    ])
