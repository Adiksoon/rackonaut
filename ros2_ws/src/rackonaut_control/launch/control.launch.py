"""Start a local Control Center with the reference simulator and an optional fixture API."""

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
    world = "safety_showcase.sdf" if safety else "control_showcase.sdf"
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
    }]))
    on_exit = [RegisterEventHandler(OnProcessExit(
        target_action=process, on_exit=[EmitEvent(event=Shutdown(reason="A Control Center service stopped"))],
    )) for process in processes]
    safety_nodes = []
    if safety:
        config = get_package_share_path("rackonaut_safety") / "config"
        safety_nodes = [
            Node(package="rackonaut_safety", executable="manage", output="screen",
                 parameters=[{"events_file": str(Path(data) / "safety-events.jsonl")}]),
            Node(package="rackonaut_safety", executable="infrastructure", output="screen"),
            *(Node(package="ros_gz_bridge", executable="parameter_bridge", name=f"safety_{name}_bridge",
                   parameters=[{"config_file": str(config / f"{name}_bridge.yaml")}], output="screen")
              for name in ("presence", "overview")),
        ]
    return [*on_exit, *processes, *safety_nodes]


def generate_launch_description():
    defaults = {"http_port": "8765", "mock": "true", "mock_port": "8000", "backend_url": "",
                "gazebo_gui": "false", "data_dir": "", "safety": "false"}
    return LaunchDescription([
        *(DeclareLaunchArgument(name, default_value=value) for name, value in defaults.items()),
        OpaqueFunction(function=setup),
    ])
