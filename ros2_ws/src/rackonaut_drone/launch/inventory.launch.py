"""Run the inventory demonstrator with X3 and virtual warehouse safety."""
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
import xml.etree.ElementTree as xml

from ament_index_python.packages import get_package_share_path
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, ExecuteProcess, IncludeLaunchDescription
from launch.actions import OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def challenging_world(source, destination):
    """Vary lighting and tag gloss in a local copy of the virtual Safety world."""
    tree = xml.parse(source)
    world = tree.find("world")

    def scale_color(element, factor):
        red, green, blue, alpha = map(float, element.text.split())
        element.text = f"{red * factor:.4f} {green * factor:.4f} {blue * factor:.4f} {alpha:g}"

    scale_color(world.find("scene/ambient"), 0.62)
    for name, factor in (("diffuse_roof_light", 0.72), ("high_bay_0", 0.62),
                         ("high_bay_1", 0.40), ("high_bay_2", 0.90)):
        scale_color(world.find(f"light[@name='{name}']/diffuse"), factor)

    glossy_tag = world.find(".//visual[@name='slot_08']/material")
    glossy_tag.find("specular").text = "0.24 0.24 0.24 1"
    glossy_tag.find("pbr/metal/roughness").text = "0.27"
    world.append(xml.fromstring("""<light name="x3_aisle_b_spot" type="spot">
      <pose>5.3 -4.75 2.7 0 0 0</pose>
      <direction>-0.19 0.47 -0.86</direction>
      <cast_shadows>false</cast_shadows>
      <diffuse>0.85 0.82 0.74 1</diffuse>
      <specular>0.5 0.5 0.5 1</specular>
      <attenuation><range>5</range><constant>0.85</constant><linear>0.08</linear><quadratic>0.04</quadratic></attenuation>
      <spot><inner_angle>0.18</inner_angle><outer_angle>0.47</outer_angle><falloff>1</falloff></spot>
    </light>"""))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
        draft = Path(temporary.name)
    try:
        tree.write(draft, encoding="utf-8", xml_declaration=True)
        draft.replace(destination)
    finally:
        draft.unlink(missing_ok=True)


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
    world = warehouse / "worlds/safety_showcase.sdf"
    drone_arguments = {"world_path": str(world), "gui": arg("gazebo_gui")}
    if arg("camera_profile") == "challenging":
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        model = cache / "rackonaut_drone/x3-challenging.sdf"
        if not model.is_file():
            raise FileNotFoundError("Run ros2 run rackonaut_drone prepare_model --camera-profile challenging.")
        lighting = data / "x3-challenging-world.sdf"
        challenging_world(world, lighting)
        drone_arguments.update(world_path=str(lighting), model_path=str(model))
    drone = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(drone_launch)), launch_arguments=drone_arguments.items(),
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
        DeclareLaunchArgument("camera_profile", default_value="standard",
                              choices=["standard", "challenging"], description="Camera and warehouse lighting"),
        OpaqueFunction(function=setup),
    ])
