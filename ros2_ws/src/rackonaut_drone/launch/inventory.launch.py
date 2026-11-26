"""Run the inventory demonstrator with X3 and virtual warehouse safety."""
import os
from pathlib import Path

from ament_index_python.packages import get_package_share_path
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, ExecuteProcess, IncludeLaunchDescription
from launch.actions import OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def setup(context):
    root = Path(os.environ["RACKONAUT_ROOT"])
    python = root / ".venv-backend/bin/python"
    if not python.is_file():
        raise RuntimeError("Run python3.10 scripts/api/setup.py to prepare the inventory API.")

    def arg(name):
        return LaunchConfiguration(name).perform(context)

    data = Path(arg("data_dir")).expanduser().resolve()
    warehouse = get_package_share_path("rackonaut_warehouse")
    safety_config = get_package_share_path("rackonaut_safety") / "config"
    drone_launch = get_package_share_path("rackonaut_drone") / "launch/drone.launch.py"
    drone = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(drone_launch)),
        launch_arguments={
            "world_path": str(warehouse / "worlds/safety_showcase.sdf"),
            "gui": arg("gazebo_gui"),
        }.items(),
    )
    api = ExecuteProcess(
        cmd=[str(python), "-m", "uvicorn", "backend.control_fixture:app",
             "--host", "127.0.0.1", "--port", arg("mock_port")],
        cwd=str(root), name="x3_inventory_api", output="screen",
    )
    control = Node(
        package="rackonaut_control", executable="serve", output="screen",
        parameters=[{"http_port": int(arg("http_port")), "data_dir": str(data),
                     "backend_url": f"http://127.0.0.1:{arg('mock_port')}",
                     "safety_enabled": True, "safety_sensor": "virtual"}],
    )
    safety = Node(
        package="rackonaut_safety", executable="manage", output="screen",
        parameters=[{"events_file": str(data / "safety-events.jsonl"), "sensor_mode": "virtual"}],
    )
    infrastructure = Node(package="rackonaut_safety", executable="infrastructure", output="screen")
    bridges = [
        Node(package="ros_gz_bridge", executable="parameter_bridge", name=f"safety_{name}_bridge",
             parameters=[{"config_file": str(safety_config / f"{name}_bridge.yaml")}], output="screen")
        for name in ("presence", "overview")
    ]

    workers = [api, control, safety, infrastructure, *bridges]
    monitors = [
        RegisterEventHandler(OnProcessExit(target_action=process,
            on_exit=[EmitEvent(event=Shutdown(reason="An X3 inventory service stopped"))]))
        for process in workers
    ]
    return [*monitors, drone, *workers]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("http_port", default_value="8765", description="Control Center port"),
        DeclareLaunchArgument("mock_port", default_value="8000", description="Inventory fixture port"),
        DeclareLaunchArgument("data_dir", default_value=str(Path(os.environ["ROS_LOG_DIR"]) / "x3-inventory"),
                              description="Inspection reports, camera evidence and Safety events"),
        DeclareLaunchArgument("gazebo_gui", default_value="false", choices=["true", "false"],
                              description="Show the Gazebo window"),
        OpaqueFunction(function=setup),
    ])
