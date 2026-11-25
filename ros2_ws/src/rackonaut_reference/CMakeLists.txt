cmake_minimum_required(VERSION 3.8)
project(rackonaut_reference)

find_package(ament_cmake REQUIRED)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
  models/reference_drone.sdf config/avoidance-lidar.sdf.fragment)
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/models/reference_drone.sdf" drone)
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/config/avoidance-lidar.sdf.fragment" lidar)
# Visibility bit 1 is reserved for this sensor and excludes the host aircraft.
string(REPLACE "version=\"1.8\"" "version=\"1.9\"" drone "${drone}")
string(REGEX REPLACE "(<visual name=\"[^\"]+\">)" "\\1<visibility_flags>4294967293</visibility_flags>" drone "${drone}")
string(REPLACE "      <sensor name=\"rgb\"" "${lidar}\n      <sensor name=\"rgb\"" drone "${drone}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/avoidance_drone.sdf" "${drone}")
install(DIRECTORY fixtures worlds models config DESTINATION share/${PROJECT_NAME})
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/avoidance_drone.sdf" DESTINATION share/${PROJECT_NAME}/models)
install(PROGRAMS scripts/mock_camera DESTINATION lib/${PROJECT_NAME})
ament_package()
