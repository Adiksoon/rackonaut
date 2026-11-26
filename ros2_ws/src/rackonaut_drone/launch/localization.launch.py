"""Compare X3 LiDAR/IMU localization to Gazebo in the known-map world."""
import json
import os
from pathlib import Path

from ament_index_python.packages import get_package_share_path
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, IncludeLaunchDescription, OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def setup(context):
    def arg(name):
        return LaunchConfiguration(name).perform(context)

    package = get_package_share_path("rackonaut_drone")
    warehouse = get_package_share_path("rackonaut_warehouse")
    dock = json.loads((warehouse / "config/aerial_layout.json").read_text())["nodes"]["dock"]
    model = Path(arg("shadow_model")).expanduser().resolve()
    if not model.is_file():
        raise FileNotFoundError("Run ros2 run rackonaut_drone prepare_model --localization-shadow.")
    data = Path(arg("data_dir")).expanduser().resolve()
    data.mkdir(parents=True, exist_ok=True)
    mode = arg("localization_mode")
    sensor_navigation = mode == "sensor_based"
    drone = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(package / "launch/drone.launch.py")),
        launch_arguments={
            "world_path": str(warehouse / "worlds/localization_showcase.sdf"),
            "model_path": str(model), "x": str(dock[0]), "y": str(dock[1]),
            "z": str(dock[2] + .07), "gui": arg("gazebo_gui"),
            "navigation_odometry": "sensor_based" if sensor_navigation else "gazebo",
        }.items(),
    )

    transforms = [
        Node(package="tf2_ros", executable="static_transform_publisher", name=f"x3_{name}_tf",
             arguments=["--z", z, "--frame-id", "rackonaut_base_link",
                        "--child-frame-id", f"rackonaut_reference_drone/base_link/local_{name}"],
             parameters=[{"use_sim_time": True}], output="screen")
        for name, z in (("imu", "0"), ("lidar", "0.09"))
    ]
    workers = [
        Node(package="ros_gz_bridge", executable="parameter_bridge", name="x3_shadow_sensor_bridge",
             parameters=[{"config_file": str(package / "config/shadow-bridge.yaml")}], output="screen"),
        Node(package="rackonaut_drone", executable="sensor_frames", output="screen",
             parameters=[{"dock_contact": sensor_navigation}]),
        *transforms,
    ]
    if arg("start_estimator") == "true":
        truth = [] if sensor_navigation else [("/rackonaut/validation/ground_truth", "/rackonaut/drone/odom")]
        workers.extend([
            Node(package="rackonaut_drone" if sensor_navigation else "rackonaut_localization",
                 executable="localize_x3" if sensor_navigation else "localize", output="screen",
                 additional_env={"OPENBLAS_NUM_THREADS": "1"},
                 parameters=[{"mode": mode, "data_dir": str(data)}]),
            Node(package="rackonaut_localization", executable="validate_pose", output="screen",
                 additional_env={"OPENBLAS_NUM_THREADS": "1"}, parameters=[{"data_dir": str(data)}],
                 remappings=truth),
        ])
    monitors = [
        RegisterEventHandler(OnProcessExit(target_action=process,
            on_exit=[EmitEvent(event=Shutdown(reason="An X3 shadow localization service stopped"))]))
        for process in workers
    ]
    return [*monitors, drone, *workers]


def generate_launch_description():
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    log_dir = Path(os.environ["ROS_LOG_DIR"])
    return LaunchDescription([
        DeclareLaunchArgument("shadow_model", default_value=str(cache / "rackonaut_drone/x3-shadow.sdf"),
                              description="X3 SDF built with --localization-shadow"),
        DeclareLaunchArgument("data_dir", default_value=str(log_dir / "x3-shadow"),
                              description="Localization map and comparison logs"),
        DeclareLaunchArgument("gazebo_gui", default_value="false", choices=["true", "false"],
                              description="Show the Gazebo window"),
        DeclareLaunchArgument("localization_mode", default_value="shadow", choices=["shadow", "sensor_based"],
                              description="Source of navigation odometry"),
        DeclareLaunchArgument("start_estimator", default_value="true", choices=["true", "false"],
                              description="Start the estimator and validator unless the caller provides both"),
        OpaqueFunction(function=setup),
    ])
