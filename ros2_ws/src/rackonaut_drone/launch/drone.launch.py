"""Start an isolated simulation of the Rackonaut X3 candidate."""
from math import isfinite
import os
from pathlib import Path
import re

from ament_index_python.packages import get_package_prefix, get_package_share_path
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, ExecuteProcess, OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def launch_drone(context):
    def value(name):
        return LaunchConfiguration(name).perform(context)

    world = value("world_name")
    if not re.fullmatch(r"[A-Za-z0-9_]+", world):
        raise ValueError("world_name must contain only letters, digits or underscores")
    world_file = Path(value("world_path")).expanduser().resolve(strict=True)
    model_file = Path(value("model_path")).expanduser().resolve()
    if not model_file.is_file():
        raise FileNotFoundError(f"X3 SDF is missing: {model_file}. Run ros2 run rackonaut_drone prepare_model.")
    pose = [value(axis) for axis in ("x", "y", "z", "roll", "pitch", "yaw")]
    if not all(isfinite(float(component)) for component in pose):
        raise ValueError("spawn pose values must be finite")

    gui = value("gui") == "true"
    renderer = [] if gui else ["-s", "--headless-rendering"]
    gazebo = ExecuteProcess(cmd=["ign", "gazebo", "-r", *renderer, "-v", "3", str(world_file)],
                            additional_env={"LIBGL_ALWAYS_SOFTWARE": "1", "GALLIUM_DRIVER": "llvmpipe"},
                            name="x3_gazebo", output="screen")
    spawn_executable = Path(get_package_prefix("rackonaut_drone")) / "lib/rackonaut_drone/spawn"
    spawn = ExecuteProcess(cmd=[str(spawn_executable), world, str(model_file), *pose],
                           name="x3_spawn", output="screen")
    gz_clock = f"/world/{world}/clock"
    bridge_remappings = []
    if value("navigation_odometry") == "sensor_based":
        bridge_remappings = [("/rackonaut/drone/odom", "/rackonaut/validation/ground_truth"),
                             ("/tf", "/rackonaut_drone/simulator/tf")]
    bridge = Node(package="ros_gz_bridge", executable="parameter_bridge", name="x3_bridge",
                  remappings=bridge_remappings,
                  parameters=[{"config_file": str(get_package_share_path("rackonaut_drone") / "config/bridge.yaml")}],
                  output="screen")
    clock = Node(package="ros_gz_bridge", executable="parameter_bridge", name="x3_clock_bridge",
                 arguments=[f"{gz_clock}@rosgraph_msgs/msg/Clock[gz.msgs.Clock"],
                 remappings=[(gz_clock, "/clock")], output="screen")
    tf = Node(package="tf2_ros", executable="static_transform_publisher", name="x3_camera_tf",
              arguments=["--x", "0.27", "--z", "0.04", "--roll", "-1.57079632679", "--yaw", "-1.57079632679",
                         "--frame-id", "rackonaut_base_link", "--child-frame-id", "rackonaut_camera_optical_frame"],
              parameters=[{"use_sim_time": True}], output="screen")
    guard = Node(package="rackonaut_drone", executable="velocity_guard", output="screen",
                 parameters=[{"dock_power": value("navigation_odometry") == "sensor_based"}])
    workers = [bridge, clock, tf, guard]

    def after_spawn(event, _):
        if event.returncode:
            return [EmitEvent(event=Shutdown(reason="X3 spawn failed"))]
        return workers

    monitors = [RegisterEventHandler(OnProcessExit(target_action=process,
                  on_exit=[EmitEvent(event=Shutdown(reason=f"{name} exited"))]))
                for process, name in [(gazebo, "Gazebo"), (bridge, "ROS bridge"), (clock, "Clock bridge"),
                                      (tf, "Camera TF"), (guard, "Velocity guard")]]
    return [*monitors, RegisterEventHandler(OnProcessExit(target_action=spawn, on_exit=after_spawn)), gazebo, spawn]


def generate_launch_description():
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    defaults = {"world_name": "rackonaut",
                "world_path": str(get_package_share_path("rackonaut_reference") / "worlds/reference.sdf"),
                "model_path": str(cache / "rackonaut_drone/x3.sdf"),
                "x": "0", "y": "0", "z": "0.12", "roll": "0", "pitch": "0", "yaw": "0"}
    arguments = [DeclareLaunchArgument(name, default_value=value) for name, value in defaults.items()]
    return LaunchDescription([*arguments,
                              DeclareLaunchArgument("navigation_odometry", default_value="gazebo",
                                                    choices=["gazebo", "sensor_based"]),
                              DeclareLaunchArgument("gui", default_value="false",
                              choices=["true", "false"]), OpaqueFunction(function=launch_drone)])
