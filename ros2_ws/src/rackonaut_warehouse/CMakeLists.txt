cmake_minimum_required(VERSION 3.8)
project(rackonaut_warehouse)

find_package(ament_cmake REQUIRED)
find_package(Python3 REQUIRED COMPONENTS Interpreter)

set(quality_world "${CMAKE_CURRENT_BINARY_DIR}/quality_showcase.sdf")
add_custom_command(OUTPUT "${quality_world}"
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
    --quality --output "${quality_world}"
  DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
  VERBATIM)
add_custom_target(quality_showcase ALL DEPENDS "${quality_world}")

install(DIRECTORY worlds meshes materials ground_truth docs
  DESTINATION share/${PROJECT_NAME})
install(FILES "${quality_world}" DESTINATION share/${PROJECT_NAME}/worlds)
install(FILES README.md DESTINATION share/${PROJECT_NAME})
ament_package()
