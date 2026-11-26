"""Keep the shared mission stack; replace its simulator with the X3 sensor model for this trial."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from ament_index_python.packages import get_package_share_path
from launch.actions import ExecuteProcess
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    source = get_package_share_path("rackonaut_control") / "launch/control.launch.py"
    spec = spec_from_file_location("shared_control_for_x3_trial", source)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    def process(*args, **kwargs):
        if kwargs.get("name") == "control_simulator":
            command = kwargs["cmd"]
            if (Path(command[2]).name != "localization_showcase.sdf"
                    or "--localization-validation" not in command or "sensor_based" not in command):
                raise RuntimeError("Trial expects headless sensor-based localization with diagnostics.")
            kwargs["cmd"] = [
                "ros2", "launch", "rackonaut_drone", "localization.launch.py", "localization_mode:=sensor_based",
                "start_estimator:=false", ["data_dir:=", LaunchConfiguration("data_dir")],
            ]
        return ExecuteProcess(*args, **kwargs)

    def worker(*args, **kwargs):
        if kwargs.get("package") == "rackonaut_control" and kwargs.get("executable") == "serve":
            kwargs.update(package="rackonaut_drone", executable="serve_x3")
        if kwargs.get("package") == "rackonaut_localization" and kwargs.get("executable") == "localize":
            kwargs.update(package="rackonaut_drone", executable="localize_x3")
        return Node(*args, **kwargs)

    module.ExecuteProcess = process
    module.Node = worker
    return module.generate_launch_description()
