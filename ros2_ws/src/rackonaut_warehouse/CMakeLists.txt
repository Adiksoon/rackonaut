cmake_minimum_required(VERSION 3.8)
project(rackonaut_warehouse)

find_package(ament_cmake REQUIRED)
install(DIRECTORY worlds meshes materials ground_truth docs
  DESTINATION share/${PROJECT_NAME})
install(FILES README.md DESTINATION share/${PROJECT_NAME})
ament_package()
