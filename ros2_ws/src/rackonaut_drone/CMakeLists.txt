cmake_minimum_required(VERSION 3.8)
project(rackonaut_drone)

find_package(ament_cmake REQUIRED)
install(DIRECTORY config launch DESTINATION share/${PROJECT_NAME})
install(PROGRAMS scripts/prepare_model scripts/spawn scripts/velocity_guard scripts/sensor_frames scripts/serve_x3 scripts/localize_x3 scripts/run_mission DESTINATION lib/${PROJECT_NAME})
ament_package()
