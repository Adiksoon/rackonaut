cmake_minimum_required(VERSION 3.8)
project(rackonaut_reference)

find_package(ament_cmake REQUIRED)
install(DIRECTORY fixtures worlds models config DESTINATION share/${PROJECT_NAME})
install(PROGRAMS scripts/mock_camera DESTINATION lib/${PROJECT_NAME})
ament_package()
