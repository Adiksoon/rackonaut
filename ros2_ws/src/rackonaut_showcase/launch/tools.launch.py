from pathlib import Path

from ament_index_python.packages import get_package_share_path
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from rackonaut_showcase.observe import GROUPS, PREFIX


def selected(context):
    arg = lambda name: LaunchConfiguration(name).perform(context)
    view, trace = arg("view"), arg("trace_file")
    tools = []
    if arg("adapter") == "true":
        tools.append(Node(package="rackonaut_showcase", executable="observe", output="screen",
                          parameters=[{"trace_file": trace}]))
    if view in {"navigation", "vision", "safety", "validation"}:
        path = Path(get_package_share_path("rackonaut_showcase")) / "config" / (view+".rviz")
        tools.append(Node(package="rviz2", executable="rviz2", output="screen",
                          arguments=["-d", str(path)], parameters=[{"use_sim_time": True}]))
    elif view == "graph":
        tools.append(Node(package="rqt_graph", executable="rqt_graph", output="screen"))
    elif view.startswith("plot_") and (group := view.removeprefix("plot_")) in GROUPS:
        indexes = {
            "flight": (2, 3, 5), "localization": (2, 4, 5), "energy": (0, 1, 2),
            "avoidance": (0, 1, 2), "validation": (0, 1, 2),
        }
        plots = [PREFIX+f"telemetry/{group}/data[{i}]" for i in indexes[group]]
        tools.append(LogInfo(msg="If rqt_plot opens before DDS discovery, add these fields in Topic:\n"
                             + "\n".join(plots)))
        tools.append(Node(package="rqt_plot", executable="rqt_plot", arguments=plots, output="screen"))
    elif view != "none":
        raise ValueError("Choose navigation, vision, safety, validation, graph, none or plot_<group>.")
    return tools


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument("view", default_value="navigation"),
        DeclareLaunchArgument("adapter", default_value="true", choices=["true", "false"]),
        DeclareLaunchArgument("trace_file", default_value=""),
        OpaqueFunction(function=selected),
    ])
