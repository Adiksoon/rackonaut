# Source from Bash. Project changes affect this shell only.
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    printf 'Run source scripts/robotics/activate.bash from a Bash shell.\n' >&2
    exit 2
fi

if [[ ! -r /opt/ros/humble/setup.bash ]]; then
    printf 'ROS 2 Humble base is missing at /opt/ros/humble.\n' >&2
    return 1
fi

export RACKONAUT_ROOT
RACKONAUT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
export RACKONAUT_WS="$RACKONAUT_ROOT/ros2_ws"
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/usr/local/sbin"
export PYTHONNOUSERSITE=1
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH COLCON_CURRENT_PREFIX CMAKE_PREFIX_PATH
unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH LD_PRELOAD VIRTUAL_ENV CONDA_PREFIX
unset ROS_DISTRO ROS_VERSION ROS_PYTHON_VERSION ROS_DISCOVERY_SERVER
unset FASTRTPS_DEFAULT_PROFILES_FILE FASTDDS_DEFAULT_PROFILES_FILE CYCLONEDDS_URI
unset GAZEBO_MODEL_PATH GAZEBO_RESOURCE_PATH GAZEBO_PLUGIN_PATH GAZEBO_MASTER_URI
unset IGN_GAZEBO_RESOURCE_PATH GZ_SIM_RESOURCE_PATH IGN_GAZEBO_SYSTEM_PLUGIN_PATH GZ_SIM_SYSTEM_PLUGIN_PATH
unset IGN_GAZEBO_PHYSICS_ENGINE_PATH IGN_GAZEBO_RENDER_ENGINE_PATH IGN_PLUGIN_PATH
unset IGN_GAZEBO_SERVER_CONFIG_PATH GZ_SIM_SERVER_CONFIG_PATH
unset IGN_FUEL_CACHE_PATH GZ_FUEL_CACHE_PATH IGN_FUEL_CONFIG_PATH GZ_FUEL_CONFIG_PATH
unset IGN_RENDER_ENGINE GZ_RENDER_ENGINE GALLIUM_DRIVER MESA_LOADER_DRIVER_OVERRIDE
unset MESA_D3D12_DEFAULT_ADAPTER_NAME MESA_EXTENSION_OVERRIDE MESA_GL_VERSION_OVERRIDE
unset MESA_GLSL_VERSION_OVERRIDE QT_QPA_PLATFORM QT_QPA_PLATFORMTHEME
unset LIBGL_ALWAYS_SOFTWARE vblank_mode

# ROS-generated setup files expect unset variables to expand to empty.
case $- in *u*) set +u; _rackonaut_restore_nounset=1 ;; esac
source /opt/ros/humble/setup.bash
if [[ -r "$RACKONAUT_WS/install/local_setup.bash" ]]; then
    source "$RACKONAUT_WS/install/local_setup.bash"
fi
if [[ ${_rackonaut_restore_nounset:-0} == 1 ]]; then
    unset _rackonaut_restore_nounset
    set -u
fi

export ROS_DOMAIN_ID="${RACKONAUT_ROS_DOMAIN_ID:-62}" ROS_LOCALHOST_ONLY=1
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export IGN_PARTITION="${RACKONAUT_GZ_PARTITION:-rackonaut-$UID}" GZ_PARTITION="${RACKONAUT_GZ_PARTITION:-rackonaut-$UID}"
export IGN_GAZEBO_RESOURCE_PATH="$RACKONAUT_WS/src"
export GZ_SIM_RESOURCE_PATH="$IGN_GAZEBO_RESOURCE_PATH"
export ROS_LOG_DIR="$RACKONAUT_WS/log/ros"
export XDG_CACHE_HOME="$RACKONAUT_WS/.cache"
export ROS_HOME="$RACKONAUT_WS/.ros"
unset GAZEBO_MODEL_PATH GAZEBO_RESOURCE_PATH GAZEBO_PLUGIN_PATH GAZEBO_MASTER_URI
