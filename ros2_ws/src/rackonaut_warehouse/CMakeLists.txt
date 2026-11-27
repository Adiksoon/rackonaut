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

set(adaptive_world "${CMAKE_CURRENT_BINARY_DIR}/adaptive_showcase.sdf")
set(adaptive_laser_world "${CMAKE_CURRENT_BINARY_DIR}/adaptive_laser_showcase.sdf")
set(adaptive_laser_fields "${CMAKE_CURRENT_BINARY_DIR}/adaptive_laser_fields.json")
add_custom_command(OUTPUT "${adaptive_world}" "${adaptive_laser_world}" "${adaptive_laser_fields}"
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
    --control --quality --safety --adaptive --output "${adaptive_world}"
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
    --control --quality --safety --adaptive --laser "${adaptive_laser_fields}" --output "${adaptive_laser_world}"
  DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
  VERBATIM)
add_custom_target(adaptive_showcase ALL DEPENDS "${adaptive_world}" "${adaptive_laser_world}" "${adaptive_laser_fields}")

set(energy_world "${CMAKE_CURRENT_BINARY_DIR}/energy_showcase.sdf")
set(energy_laser_world "${CMAKE_CURRENT_BINARY_DIR}/energy_laser_showcase.sdf")
set(energy_laser_fields "${CMAKE_CURRENT_BINARY_DIR}/energy_laser_fields.json")
set(dock_layout "${CMAKE_CURRENT_BINARY_DIR}/dock_layout.json")
add_custom_command(OUTPUT "${energy_world}" "${energy_laser_world}" "${energy_laser_fields}" "${dock_layout}"
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
    --control --quality --safety --adaptive --energy --dock-layout "${dock_layout}" --output "${energy_world}"
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
    --control --quality --safety --adaptive --energy --laser "${energy_laser_fields}" --output "${energy_laser_world}"
  DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
  VERBATIM)
add_custom_target(energy_showcase ALL DEPENDS "${energy_world}" "${energy_laser_world}" "${energy_laser_fields}" "${dock_layout}")

set(aerial_world "${CMAKE_CURRENT_BINARY_DIR}/aerial_showcase.sdf")
set(aerial_laser_world "${CMAKE_CURRENT_BINARY_DIR}/aerial_laser_showcase.sdf")
set(aerial_laser_fields "${CMAKE_CURRENT_BINARY_DIR}/aerial_laser_fields.json")
set(aerial_layout "${CMAKE_CURRENT_BINARY_DIR}/aerial_layout.json")
add_custom_command(OUTPUT "${aerial_world}" "${aerial_laser_world}" "${aerial_laser_fields}" "${aerial_layout}"
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
    --control --quality --safety --adaptive --energy --aerial --aerial-layout "${aerial_layout}" --output "${aerial_world}"
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
    --control --quality --safety --adaptive --energy --aerial --laser "${aerial_laser_fields}" --output "${aerial_laser_world}"
  DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
  VERBATIM)
add_custom_target(aerial_showcase ALL DEPENDS "${aerial_world}" "${aerial_laser_world}" "${aerial_laser_fields}" "${aerial_layout}")

set(avoidance_world "${CMAKE_CURRENT_BINARY_DIR}/avoidance_showcase.sdf")
set(avoidance_laser_world "${CMAKE_CURRENT_BINARY_DIR}/avoidance_laser_showcase.sdf")
set(avoidance_laser_fields "${CMAKE_CURRENT_BINARY_DIR}/avoidance_laser_fields.json")
set(avoidance_layout "${CMAKE_CURRENT_BINARY_DIR}/avoidance_layout.json")
add_custom_command(OUTPUT "${avoidance_world}" "${avoidance_laser_world}" "${avoidance_laser_fields}" "${avoidance_layout}"
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
    --control --quality --safety --adaptive --energy --aerial --avoidance --avoidance-layout "${avoidance_layout}"
    --output "${avoidance_world}"
  COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
    --control --quality --safety --adaptive --energy --aerial --avoidance --laser "${avoidance_laser_fields}"
    --output "${avoidance_laser_world}"
  DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
  VERBATIM)
add_custom_target(avoidance_showcase ALL DEPENDS "${avoidance_world}" "${avoidance_laser_world}"
  "${avoidance_laser_fields}" "${avoidance_layout}")

foreach(variant IN ITEMS historical open_aisle)
  set(prefix "")
  set(options "")
  set(layout_output "")
  set(layout_option "")
  if(variant STREQUAL "open_aisle")
    set(prefix "open_aisle_")
    set(options --open-descent)
    set(layout_output "${CMAKE_CURRENT_BINARY_DIR}/open_aisle_aerial_layout.json")
    set(layout_option --aerial-layout "${layout_output}")
  endif()
  set(localization_world "${CMAKE_CURRENT_BINARY_DIR}/${prefix}localization_showcase.sdf")
  set(localization_laser_world "${CMAKE_CURRENT_BINARY_DIR}/${prefix}localization_laser_showcase.sdf")
  set(localization_map "${CMAKE_CURRENT_BINARY_DIR}/${prefix}localization_map.json")
  set(localization_laser_fields "${CMAKE_CURRENT_BINARY_DIR}/${prefix}localization_laser_fields.json")
  set(outputs "${localization_world}" "${localization_laser_world}" "${localization_map}"
    "${localization_laser_fields}" ${layout_output})
  add_custom_command(OUTPUT ${outputs}
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
      --control --quality --safety --adaptive --energy --aerial --avoidance --localization ${options}
      ${layout_option} --localization-map "${localization_map}" --output "${localization_world}"
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py"
      --control --quality --safety --adaptive --energy --aerial --avoidance --localization ${options}
      --laser "${localization_laser_fields}" --output "${localization_laser_world}"
    DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate.py" "${CMAKE_CURRENT_SOURCE_DIR}/meshes/steel_warehouse_lod1.dae"
    VERBATIM)
  add_custom_target(${prefix}localization_showcase ALL DEPENDS ${outputs})
  install(FILES "${localization_world}" "${localization_laser_world}" DESTINATION share/${PROJECT_NAME}/worlds)
  install(FILES "${localization_map}" ${layout_output} DESTINATION share/${PROJECT_NAME}/config)
endforeach()

install(DIRECTORY worlds meshes materials ground_truth docs
  DESTINATION share/${PROJECT_NAME})
install(FILES "${quality_world}" "${control_world}" DESTINATION share/${PROJECT_NAME}/worlds)
install(FILES "${control_layout}" "${control_markers}" DESTINATION share/${PROJECT_NAME}/config)
install(FILES "${safety_world}" DESTINATION share/${PROJECT_NAME}/worlds)
install(FILES "${safety_fields}" DESTINATION share/${PROJECT_NAME}/config)
install(FILES "${laser_world}" DESTINATION share/${PROJECT_NAME}/worlds)
install(FILES "${laser_fields}" DESTINATION share/${PROJECT_NAME}/config)
install(FILES "${adaptive_world}" "${adaptive_laser_world}" DESTINATION share/${PROJECT_NAME}/worlds)
install(FILES "${energy_world}" "${energy_laser_world}" DESTINATION share/${PROJECT_NAME}/worlds)
install(FILES "${dock_layout}" DESTINATION share/${PROJECT_NAME}/config)
install(FILES "${aerial_world}" "${aerial_laser_world}" DESTINATION share/${PROJECT_NAME}/worlds)
install(FILES "${aerial_layout}" DESTINATION share/${PROJECT_NAME}/config)
install(FILES "${avoidance_world}" "${avoidance_laser_world}" DESTINATION share/${PROJECT_NAME}/worlds)
install(FILES "${avoidance_layout}" DESTINATION share/${PROJECT_NAME}/config)
install(FILES README.md DESTINATION share/${PROJECT_NAME})
ament_package()
