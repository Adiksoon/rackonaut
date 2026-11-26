cmake_minimum_required(VERSION 3.8)
project(rackonaut_drone)

find_package(ament_cmake REQUIRED)
install(DIRECTORY config launch DESTINATION share/${PROJECT_NAME})
install(PROGRAMS scripts/prepare_model scripts/spawn scripts/velocity_guard DESTINATION lib/${PROJECT_NAME})
ament_package()
