"""Launch the existing robotics stack and run a fresh inspection."""

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ament_index_python.packages import get_package_share_path
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, ExecuteProcess, OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def setup(context):
    def arg(key):
        return LaunchConfiguration(key).perform(context)

    def enabled(key):
        value = arg(key).lower()
        if value not in ("true", "false"):
            raise ValueError(f"{key} expects true or false")
        return value == "true"

    root_dir = os.environ.get("RACKONAUT_ROOT")
    if not root_dir:
        raise RuntimeError("Activate scripts/robotics/activate.bash from the Rackonaut checkout.")
    root = Path(root_dir)
    share = get_package_share_path("rackonaut_mission")
    backend, run = arg("backend_url"), arg("inspection_id")
    sim = [str(root / "scripts/robotics/reference"), "--world", arg("world")]
    if enabled("gazebo_gui"):
        sim.append("--gui")
    world = ExecuteProcess(cmd=sim, cwd=str(root), name="warehouse_and_reference_drone", output="screen")
    shared = {"use_sim_time": True, "inspection_id": run, "backend_url": backend}
    vision = Node(package="rackonaut_perception", executable="inspect", output="screen", parameters=[shared])
    mission = Node(package="rackonaut_mission", executable="run_mission", output="screen", parameters=[
        shared,
        {"route_file": arg("route"), "autostart": enabled("autostart"), "land": enabled("land")},
    ])
    required = [world, vision, mission]
    if enabled("mock"):
        python = root / ".venv-backend/bin/python"
        if not python.is_file():
            raise RuntimeError("Set up the mock API virtualenv as described in docs/onboarding/BACKEND.md.")
        port = arg("mock_port")
        if backend.rstrip("/") != f"http://127.0.0.1:{port}":
            raise ValueError("With mock:=true, set backend_url and mock_port to the same loopback port.")
        required.insert(0, ExecuteProcess(
            cmd=[str(python), "-m", "uvicorn", "backend.mock_api:app", "--host", "127.0.0.1", "--port", port],
            cwd=str(root), name="mock_api", output="screen",
        ))
    handlers = [
        RegisterEventHandler(OnProcessExit(
            target_action=process, on_exit=[EmitEvent(event=Shutdown(reason="A required demo process exited"))],
        ))
        for process in required
    ]
    optional = []
    if enabled("view"):
        optional.append(Node(
            package="image_view", executable="image_view", name="rackonaut_vision_view", output="screen",
            remappings=[("image", "/rackonaut/perception/annotated")],
        ))
    if enabled("rviz"):
        optional.append(Node(package="rviz2", executable="rviz2", name="rackonaut_route_view", output="screen",
                             arguments=["-d", str(share / "config/showcase.rviz")], parameters=[{"use_sim_time": True}]))
    return [*handlers, *required, *optional]


def generate_launch_description():
    share = get_package_share_path("rackonaut_mission")
    warehouse = get_package_share_path("rackonaut_warehouse")
    now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    arguments = {
        "inspection_id": f"INS-MISSION-{now}-{uuid4().hex[:4].upper()}",
        "backend_url": "http://127.0.0.1:8000",
        "mock_port": "8000",
        "mock": "true",
        "gazebo_gui": "true",
        "view": "true",
        "rviz": "false",
        "autostart": "true",
        "land": "true",
        "route": str(share / "config/showcase.json"),
        "world": str(warehouse / "worlds/showcase.sdf"),
    }
    return LaunchDescription([
        *(DeclareLaunchArgument(name, default_value=value) for name, value in arguments.items()),
        OpaqueFunction(function=setup),
    ])
