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
set(control_world "${CMAKE_CURRENT_BINARY_DIR}/control_showcase.sdf")
set(control_layout "${CMAKE_CURRENT_BINARY_DIR}/control_layout.json")
set(control_markers "${CMAKE_CURRENT_BINARY_DIR}/control_markers.json")
add_custom_command(OUTPUT "${control_world}" "${control_layout}" "${control_markers}"
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
    --quality --control --output "${control_world}" --layout "${control_layout}" --marker-map "${control_markers}"
  DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
  VERBATIM)
add_custom_target(control_showcase ALL DEPENDS "${control_world}" "${control_layout}" "${control_markers}")

set(safety_world "${CMAKE_CURRENT_BINARY_DIR}/safety_showcase.sdf")
set(safety_fields "${CMAKE_CURRENT_BINARY_DIR}/safety_fields.json")
add_custom_command(OUTPUT "${safety_world}" "${safety_fields}"
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
    --control --quality --safety --output "${safety_world}" --layout "${safety_fields}"
  DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
  VERBATIM)
add_custom_target(safety_showcase ALL DEPENDS "${safety_world}" "${safety_fields}")

set(laser_world "${CMAKE_CURRENT_BINARY_DIR}/laser_safety_showcase.sdf")
set(laser_fields "${CMAKE_CURRENT_BINARY_DIR}/laser_fields.json")
add_custom_command(OUTPUT "${laser_world}" "${laser_fields}"
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
    --control --quality --safety --laser "${laser_fields}" --output "${laser_world}"
  DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
  VERBATIM)
add_custom_target(laser_safety_showcase ALL DEPENDS "${laser_world}" "${laser_fields}")

install(DIRECTORY worlds meshes materials ground_truth docs
  DESTINATION share/${PROJECT_NAME})
install(FILES "${quality_world}" "${control_world}" DESTINATION share/${PROJECT_NAME}/worlds)
install(FILES "${control_layout}" "${control_markers}" DESTINATION share/${PROJECT_NAME}/config)
install(FILES "${safety_world}" DESTINATION share/${PROJECT_NAME}/worlds)
install(FILES "${safety_fields}" DESTINATION share/${PROJECT_NAME}/config)
install(FILES "${laser_world}" DESTINATION share/${PROJECT_NAME}/worlds)
install(FILES "${laser_fields}" DESTINATION share/${PROJECT_NAME}/config)
install(FILES README.md DESTINATION share/${PROJECT_NAME})
ament_package()
